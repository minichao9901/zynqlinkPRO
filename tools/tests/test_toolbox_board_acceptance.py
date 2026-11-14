import contextlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from tools.run_board_acceptance import (BOARDS, BUSINESSES, ENDINGS, FEATURES, Pending,
                                        Report, Unsafe, campaign, plan, review, rotation)


class TestBoardAcceptance(unittest.TestCase):
    def test_hpm_native_flash_configuration_selects_j7_with_the_sdk(self):
        from tools.board_acceptance import BoardAcceptance
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk = root / 'hpm_sdk'
            scripts = sdk / 'boards' / 'openocd'
            scripts.mkdir(parents=True)
            (scripts / 'hpm6800_all_in_one.cfg').touch()
            executable = root / 'tools' / 'openocd' / 'openocd.exe'
            interface = executable.parent / 'tcl' / 'interface'
            interface.mkdir(parents=True)
            (interface / 'cmsis-dap.cfg').touch()
            board = BoardAcceptance(SimpleNamespace(board='hpm6800evk', serial='12345678'), None)
            board.case = {'transport': 'jtag', 'requestedHz': 25000000}
            cfg = board.native_flash_config(executable, scripts)
            self.assertIn('adapter serial {12345678}\n', cfg)
            self.assertIn(f'set HPM_SDK_BASE {{{sdk.as_posix()}}}\n', cfg)
            self.assertIn('set BOARD hpm6800evk\nset PROBE cmsis_dap\nsource [find hpm6800_all_in_one.cfg]', cfg)
            self.assertTrue(cfg.endswith('adapter speed 25000\nreset_config none\n'))

    def test_flash_comparison_uses_sparse_web_sector_ranges(self):
        from tools.board_acceptance import BoardAcceptance
        regions = [{'address': 0x80003000, 'bytes': 45008},
                   {'address': 0x80000400, 'bytes': 3216}]
        ranges = BoardAcceptance.flash_ranges(regions, 0x80000000, 0x8000e000, 0x1000)
        self.assertEqual(ranges, [(0x80000000, 0x80002000), (0x80003000, 0x8000e000)])
        with self.assertRaisesRegex(RuntimeError, 'exceeds'):
            BoardAcceptance.flash_ranges(regions, 0x80000000, 0x8000d000, 0x1000)

    def test_hpm_rtt_downlink_and_scope_do_not_overlap_the_16k_uplink(self):
        from tools.board_acceptance import BoardAcceptance
        board = BoardAcceptance(SimpleNamespace(board='hpm6800evk', serial='12345678'), None)
        base, control, up, down = board.rtt_addresses()
        self.assertLess(control, up)
        self.assertLessEqual(up + 16384, down)
        self.assertLessEqual(down + 64, board.scope_address())
        self.assertLessEqual(board.scope_address() + 32, base + 0x5200)

    def test_plan_uses_one_link_rate_and_two_scope_windows(self):
        for board, (hz, links, _) in BOARDS.items():
            cases = plan(board, None, FEATURES, 14)
            self.assertEqual(len({case['id'] for case in cases}), len(cases))
            for link in links:
                subset = [case for case in cases if case['id'].startswith(link + '-')]
                self.assertTrue(all(case['requestedHz'] == hz for case in subset))
                self.assertEqual([(case['channels'], case['seconds']) for case in subset
                                  if case['feature'] == 'jscope'], [(1, 60), (8, 60)])
                self.assertEqual(len([case for case in subset if case['feature'] == 'stress']), 3)
            self.assertEqual('notApplicable' in cases[-1], board == 'hpm6800evk')

    def test_seeded_disconnects_cover_live_rtt_scope_and_debug(self):
        for seed in range(50):
            rows = rotation(seed)
            self.assertEqual(rows, rotation(seed))
            self.assertEqual(len({tuple(x['business'] for x in row) for row in rows}), 3)
            for row in rows:
                self.assertEqual({x['business'] for x in row}, set(BUSINESSES))
                self.assertEqual({x['ending'] for x in row}, set(ENDINGS))
            for ending in ENDINGS[2:]:
                businesses = {x['business'] for row in rows for x in row if x['ending'] == ending}
                self.assertTrue({'jscope', 'debug'} <= businesses)
                self.assertEqual(len(businesses & {'rtt-viewer', 'rtt-forward'}), 1)

    def run_fake(self, errors, idle_error=False, full=True):
        class Driver:
            def preflight(self):
                return {'fake': True}

            def run(self, case, folder):
                if case['id'] in errors:
                    raise errors[case['id']]
                return {'verified': True}

            def check_idle(self):
                if idle_error:
                    raise RuntimeError('busy')
                return {'idle': True}

            def final_state(self):
                return self.check_idle()
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()) as output:
            folder = Path(temp) / 'report'
            result = campaign([{'id': 'first'}, {'id': 'second'}, {'id': 'third'},
                               {'id': 'absent', 'notApplicable': 'no ETM'}],
                              Driver(), Report(folder, {}), full=full)
            persisted = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
            lines = (folder / 'events.jsonl').read_text(encoding='utf-8').splitlines()
            self.assertEqual(output.getvalue().splitlines(), lines)
            emitted = [json.loads(line) for line in lines]
            self.assertEqual(emitted[-1]['event'], 'summary')
            return result, persisted

    def test_recoverable_failures_continue_and_pending_is_incomplete(self):
        code, report = self.run_fake({'first': ValueError('bad bytes'), 'second': Pending('board feature')})
        self.assertEqual(code, 1)
        self.assertEqual([row['status'] for row in report['results']],
                         ['pass', 'fail', 'pending', 'pass', 'not-applicable', 'pass'])
        self.assertFalse(report['accepted'])
        code, report = self.run_fake({'first': Pending('unavailable')})
        self.assertEqual((code, report['status']), (2, 'incomplete'))

    def test_unsafe_stops_hardware_but_still_emits_remaining_cases(self):
        for errors, idle in [({'first': Unsafe('unconfirmed write')}, False), ({}, True)]:
            code, report = self.run_fake(errors, idle)
            self.assertEqual(code, 1)
            self.assertEqual([row['status'] for row in report['results']],
                             ['pass', 'fail', 'blocked', 'blocked', 'not-applicable', 'blocked'])

    def test_subset_never_claims_full_acceptance(self):
        code, report = self.run_fake({}, full=False)
        self.assertEqual(code, 0)
        self.assertFalse(report['accepted'])
        self.assertEqual(report['scope'], 'selected')

    def test_offline_review_combines_distinct_boards_and_supplemental_etm(self):
        with tempfile.TemporaryDirectory() as temp:
            def evidence(board, only, serial='12345678', suffix='', target='application',
                         etm='trace-application', actual=None, time='00'):
                cases = plan(board, None, only, 7)
                files = {'bit': {'sha256': 'bit'}, 'zynqElf': {'sha256': 'ps'},
                         'targetElf': {'sha256': target}, 'etmElf': {'sha256': etm}}
                path = Path(temp) / (board + suffix + '.json')
                records = [dict(case, status='not-applicable' if 'notApplicable' in case else 'pass',
                                evidence={'targetElf': {'sha256': actual or (etm if case['feature'] == 'etm' else target),
                                                        'verifiedLoadBytes': 16}})
                           for case in cases]
                path.write_text(json.dumps(dict(board=board, revision='abc', probeSerial=serial, files=files,
                    seed=7, finishedAt=f'2026-11-14T10:00:{time}+00:00', status='pass', plan=cases,
                    results=[{'id': 'preflight', 'status': 'pass'}, *records,
                             {'id': 'final-state', 'status': 'pass'}])), encoding='utf-8')
                return path

            first = evidence('f103ze', FEATURES)
            h7 = evidence('h743', set(FEATURES)-{'etm'})
            hpm = evidence('hpm6800evk', FEATURES)
            self.assertEqual(review([first, h7, hpm])['status'], 'incomplete')
            etm = evidence('h743', {'etm'}, suffix='-etm', target='trace-application')
            self.assertTrue(review([first, h7, hpm, etm])['accepted'])
            conflict = evidence('f103ze', {'debug'}, suffix='-conflict', target='other-application', time='01')
            with self.assertRaisesRegex(ValueError, 'Conflicting targetElf'):
                review([first, h7, hpm, etm, conflict])
            full_retest = evidence('f103ze', FEATURES, suffix='-retest', target='new-application', time='01')
            self.assertTrue(review([first, h7, hpm, etm, full_retest])['accepted'])
            wrong_etm = evidence('h743', {'etm'}, suffix='-wrong', actual='other-elf')
            with self.assertRaisesRegex(ValueError, 'mismatched actual target ELF'):
                review([first, h7, hpm, wrong_etm])
            other_etm = evidence('h743', {'etm'}, suffix='-alternate', etm='other-elf', time='01')
            result = review([first, h7, hpm, etm, other_etm])
            trace = next(row for row in result['boards']['h743'] if row['id'] == 'etm')
            self.assertEqual(trace['targetElfSha256'], 'other-elf')
            different_probe = evidence('h743', {'etm'}, serial='other', suffix='-other')
            with self.assertRaisesRegex(ValueError, 'one clean source'):
                review([first, different_probe])

    def test_sequence_and_scope_validate_real_payload_layout(self):
        from tools.board_acceptance import SCOPE_VALUES, jsp_data, sequence
        self.assertEqual(sequence(struct.pack('<3I', 0, 1, 2))['last'], 2)
        with self.assertRaises(RuntimeError):
            sequence(struct.pack('<3I', 0, 2, 2))
        definition = bytearray(512)
        struct.pack_into('<HBBIIHHIIHBBIB', definition, 0, 0x4a53, 2, 1, 0, 0, 0, 1,
                         25_000_000, 240, 0, 1, 1, 0xf0404800, 4)
        data = bytearray(512)
        struct.pack_into('<HBBIIHH2I', data, 0, 0x4a53, 2, 2, 1, 500, 2, 8,
                         SCOPE_VALUES[0], SCOPE_VALUES[0])
        timestamps = []
        self.assertEqual(jsp_data(definition + data, 0xf0404800, 1, 25_000_000, timestamps),
                         (2, 500, 740, 240))
        self.assertEqual(timestamps, [500, 740])
        wrapped = bytearray(data)
        struct.pack_into('<II', data, 4, 1, 0xfffffe00)
        struct.pack_into('<II', wrapped, 4, 2, 32)
        self.assertEqual(jsp_data(definition + data + wrapped, 0xf0404800, 1, 25_000_000)[2],
                         (1 << 32) + 272)
        struct.pack_into('<I', data, 8, 500)
        definition[2] = data[2] = 1
        struct.pack_into('<I', definition, 20, 10)
        self.assertEqual(jsp_data(definition + data, 0xf0404800, 1, 25_000_000),
                         (2, 12000, 12240, 240))
        data[20] ^= 1
        with self.assertRaises(RuntimeError):
            jsp_data(definition + data, 0xf0404800, 1, 25_000_000)

    def test_unknown_browser_write_blocks_further_commands(self):
        from tools.board_acceptance import AcceptanceWeb
        web = AcceptanceWeb.__new__(AcceptanceWeb)
        web.target = SimpleNamespace(uncertain=None)
        web.client = SimpleNamespace(request=None)
        with patch.object(web.client, 'request', side_effect=TimeoutError('操作可能仍在执行')) as request:
            with self.assertRaises(Unsafe):
                web.call({'action': 'write'})
            with self.assertRaises(Unsafe):
                web.call({'action': 'write'})
            request.assert_called_once()

    @staticmethod
    def driver(board='f103ze'):
        from tools.board_acceptance import BoardAcceptance
        return BoardAcceptance(SimpleNamespace(board=board, serial='12345678'), None)

    def test_web_rtt_clock_matches_actual_browser_options_for_all_boards(self):
        from tools.run_board_acceptance import ROOT
        source = (ROOT / 'web/app/hid/view.js').read_text(encoding='utf-8')
        values = set(re.findall(r"\bv: '(\d+)'", source.split('const hex')[0]))
        for board, (hz, transports, _) in BOARDS.items():
            for transport in transports:
                driver = self.driver(board)
                driver.case = {'requestedHz': hz, 'transport': transport}
                driver.web = Mock()
                driver.port = Mock(return_value='COM5')
                driver.invoke = Mock(return_value={'open': True, 'connected': True, 'bytes': 16})
                driver.web.read.return_value = {'options': [{'label': 'CMSIS-DAP (COM5)', 'value': 'j7'}]}
                self.assertEqual(driver.cdc_start(), 'COM5')
                settings = {call.args[1]: call.args[2] for call in driver.web.set.call_args_list}
                self.assertIn(settings['#h-clock'], values)
                self.assertEqual(int(settings['#h-clock']), hz)
                expected = 'riscv' if board == 'hpm6800evk' else 'arm-jtag' if transport == 'jtag' else 'swd'
                self.assertEqual(settings['#h-target'], expected)

    def test_probe_status_unwraps_the_native_service_response(self):
        driver = self.driver()
        driver.web = Mock()
        driver.web.client.native.side_effect = [
            {'ok': True, 'value': [{'productName': 'CMSIS-DAP', 'serialNumber': '12345678'}]},
            {'ok': True, 'value': [{'productName': 'zynqlinkPRO HID', 'serialNumber': '12345678'}]},
            {'ok': True, 'value': {'resources': {'usb': {'owner': 'occupied'}}}},
            {'ok': True, 'value': [{'path': 'COM33', 'serialNumber': '12345678',
                                    'usbVendorId': 0x0d28, 'usbProductId': 0x0204}]},
        ]
        with self.assertRaisesRegex(RuntimeError, 'session is still occupied'):
            driver.check_idle()
        self.assertEqual(driver.port(), 'COM33')

    def test_aborted_flash_proves_backup_before_preserving_original_error(self):
        driver = self.driver()
        driver.check_idle = Mock()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for values, needs_rewrite in [([True], False), ([False, True], True)]:
                matches = Mock(side_effect=values)
                restore = Mock()
                with self.assertRaises(KeyboardInterrupt):
                    with driver.flash_recovery(folder, folder / 'private.bin', matches, restore):
                        raise KeyboardInterrupt
                evidence = json.loads((folder / 'flash-recovery.json').read_text())
                self.assertTrue(evidence['verified'])
                self.assertEqual(restore.call_count, int(needs_rewrite))
                self.assertIsNone(driver.target.uncertain)

    def test_failed_or_uncertain_flash_recovery_cannot_resume_target(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for failure, checks, rewrites in [(KeyboardInterrupt(), 2, 1), (Unsafe('busy'), 0, 0)]:
                driver = self.driver()
                driver.check_idle = Mock()
                matches = Mock(return_value=False)
                restore = Mock()
                with self.assertRaises(Unsafe):
                    with driver.flash_recovery(folder, folder / 'private.bin', matches, restore):
                        raise failure
                evidence = json.loads((folder / 'flash-recovery.json').read_text())
                self.assertFalse(evidence['verified'])
                self.assertEqual((matches.call_count, restore.call_count), (checks, rewrites))
                # All outer fixture exits use the same native link guard.
                with self.assertRaises(Unsafe), driver.target.link():
                    self.fail('target link allowed restoration/resume')

    def test_native_writer_must_reap_before_recovery(self):
        driver = self.driver()
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = subprocess.TimeoutExpired('fake-openocd', 10)
        with self.assertRaises(Unsafe):
            driver.stop_flash_writer(child)
        self.assertEqual([call[0] for call in child.method_calls], ['poll', 'kill', 'wait'])
        self.assertIn('writer exit unconfirmed', driver.target.uncertain)

    def test_native_writer_is_reaped_on_startup_interrupt(self):
        driver = self.driver()
        driver.case = {'transport': 'swd'}
        probe = SimpleNamespace(manufacturer='CherryUSB', product='CMSIS-DAP', serial_number='12345678')
        child = Mock(stdout=io.BytesIO())
        child.poll.side_effect = [None, 1]
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch('usb.core.find', return_value=[probe]), patch('usb.util.dispose_resources') as dispose, \
                 patch('libusb_package.get_libusb1_backend'), \
                 patch('subprocess.Popen', return_value=child) as popen, \
                 patch('threading.Thread.start', side_effect=KeyboardInterrupt):
                actions = Mock()
                actions.attach_mock(dispose, 'dispose')
                actions.attach_mock(popen, 'popen')
                (folder / 'private.bin').write_bytes(bytes(0x800))
                with self.assertRaises(KeyboardInterrupt):
                    driver.native_flash('openocd', folder, folder / 'board.cfg', folder / 'private.bin',
                                        0x08000000, folder / 'writer.log', geometry=(0x08000000, 0x08000800, 0x800))
                self.assertEqual([call[0] for call in actions.mock_calls], ['dispose', 'popen'])
        child.kill.assert_called_once()
        child.wait.assert_called_once_with(timeout=10)

    def test_arm_openocd_handoff_selects_jtag_and_releases_the_serial_bound_probe(self):
        dev = object()
        with patch('tools.dap_pipeline_bench.open_dap', return_value=(dev, 'out', 'in')) as open_dap, \
             patch('tools.dap_pipeline_bench.drain'), patch('usb.util.dispose_resources') as dispose, \
             patch('tools.dap_pipeline_bench.xfer', side_effect=[b'\x02\x02', b'\x11\x00', b'\x12\x00', b'\x03\x00',
                                                                b'\x02\x02', b'\x11\x00', b'\x12\xff', b'\x03\x00']) as transfer:
            self.driver().target.prepare_openocd('swd')
            self.driver('hpm6800evk').target.prepare_openocd('jtag')
            open_dap.assert_not_called()
            self.driver('h743').target.prepare_openocd('jtag')
            with self.assertRaisesRegex(RuntimeError, 'SWD-to-JTAG'):
                self.driver().target.prepare_openocd('jtag')
            self.assertEqual([call.args for call in open_dap.call_args_list], [('12345678',)] * 2)
            self.assertEqual([call.args[2] for call in transfer.call_args_list], [
                [2, 2], [0x11, 0x40, 0x42, 0x0f, 0],
                [0x12, 88] + [0xff] * 8 + [0x3c, 0xe7, 0x1f], [3]] * 2)
            self.assertEqual([call.args for call in dispose.call_args_list], [(dev,)] * 2)

    def test_f103_flash_boot_requires_new_reset_and_releases_nrst_on_error(self):
        from tools.board_acceptance_target import DEMCR, DHCSR, S_RESET_ST
        heartbeat = 0x20005400
        for mode in ('pass', 'stale', 'no-reset', 'assertion-failed', 'release-failed'):
            with self.subTest(mode=mode):
                target = self.driver().target
                mem = Mock()
                target.link = Mock(return_value=contextlib.nullcontext((None, mem, None, {})))
                target.state = Mock(return_value=dict(halted=False, clock={}, ccr='0x0'))
                target.fpb_snapshot = Mock(return_value=bytes(12))
                status = iter([S_RESET_ST if mode == 'stale' else 0, 0 if mode == 'no-reset' else S_RESET_ST])
                ticks = iter([90430, 90441, 5, 327, 612])
                mem.word.side_effect = lambda address: {DHCSR: lambda: next(status), DEMCR: lambda: 0,
                                                         heartbeat: lambda: next(ticks)}[address]()
                mem.transfer.side_effect = [b'\x10\x80', b'\x10\x80' if mode == 'assertion-failed' else b'\x10\x00',
                                            b'\x10\x00' if mode == 'release-failed' else b'\x10\x80']
                with patch('tools.board_acceptance_target.time.sleep'), \
                     patch.dict(sys.modules, {'target_snapshot': SimpleNamespace(same_clock_configuration=lambda a, b: a == b)}):
                    if mode == 'pass':
                        result = target.f103_reset_application(heartbeat)
                        self.assertEqual(result['method'], 'J7 NRST')
                        self.assertEqual(result['heartbeat']['advancing'], [5, 327, 612])
                    else:
                        errors = {'stale': 'previous reset', 'no-reset': 'no fresh core reset',
                                  'assertion-failed': 'did not assert', 'release-failed': 'release unconfirmed'}
                        with self.assertRaisesRegex(Unsafe if mode == 'release-failed' else RuntimeError, errors[mode]):
                            target.f103_reset_application(heartbeat)
                calls = [[0x10, 0, 0, 0, 0, 0, 0]]
                if mode != 'stale':
                    calls += [[0x10, 0, 0x80, 0, 0, 0, 0], [0x10, 0x80, 0x80, 0, 0, 0, 0]]
                self.assertEqual([call.args[0] for call in mem.transfer.call_args_list], calls)
                self.assertEqual(bool(target.uncertain), mode == 'release-failed')

    def test_flash_geometry_parser_uses_actual_erase_sectors(self):
        from tools.board_acceptance import read_flash_sectors
        text = ('#0 : flash (stm32f1x) at 0x08000000, size 0x00080000, buswidth 0\n'
                '  #  0: 0x00000000 (0x800 2kB)\n'
                '  #  1: 0x00000800 (0x800 2kB)\n'
                '#1 : flash (stm32h7x) at 0x08100000, size 0x00100000\n'
                '  #  0: 0x00000000 (0x20000 128kB)\n')
        self.assertEqual(read_flash_sectors(text), [(0x08000000, 0x800), (0x08000800, 0x800), (0x08100000, 0x20000)])

    def test_target_identity_checks_non_executable_load_segments(self):
        from tools.run_board_acceptance import ROOT, digest
        from tools.board_acceptance_target import elf_contents
        driver = self.driver()
        elf = ROOT / BOARDS['f103ze'][2]
        expected = digest(elf)
        _, segments = elf_contents(elf)
        contents = {(at, len(data)): data for at, data, _ in segments}
        memory = SimpleNamespace(read=lambda at, count: contents[at, count])
        self.assertGreater(driver.verify_target_image(memory, elf, expected)['verifiedLoadBytes'], 0)
        at, original, _ = next(row for row in segments if not row[2] & 1)
        contents[at, len(original)] = bytes([original[0] ^ 1]) + original[1:]
        with self.assertRaises(Pending):
            driver.verify_target_image(memory, elf, expected)

    def test_live_debug_keeps_application_progress_without_ram_restore_claim(self):
        driver = self.driver()
        target = driver.target
        state = {'halted': False, 'pc': 0x100}
        target.link = lambda: contextlib.nullcontext((None, object(), None, {}))
        target.state = Mock(side_effect=lambda *_: state.copy())
        target.halt = Mock()
        target.fpb_snapshot = Mock(return_value=b'\0' * 12)
        target.fpb_restore = Mock()
        target.restore_state = Mock(side_effect=lambda _, __, saved: dict(state, halted=saved['halted']))
        target.restore_registers = Mock()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'debug'
            with target.live_debug(folder, Mock()):
                state['pc'] = 0x104
            evidence = json.loads((folder / 'restored.json').read_text())
            self.assertEqual(evidence['state']['pc'], 0x104)
            self.assertIsNone(evidence['ramRestored'])
            self.assertIsNone(evidence['registersRestored'])
            target.fpb_restore.assert_called_once()
            target.restore_registers.assert_not_called()
            target.state.return_value = None
            state['halted'] = True
            count = target.halt.call_count
            with self.assertRaises(Pending), target.live_debug(Path(temp) / 'halted', Mock()):
                self.fail('a paused application was modified')
            self.assertEqual(target.halt.call_count, count)

    def test_hpm_live_debug_restores_only_the_step_bit_before_native_resume(self):
        from tools.board_acceptance_target import RV_DCSR, RV_DCSR_STEP, Target
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as temp:
                target = Target(SimpleNamespace(board='hpm6800evk'))
                registers = {RV_DCSR: 0x4000b743, 0x7b1: 0x80006452}
                writes = []
                def register(number, value=None):
                    if value is not None:
                        writes.append((number, value))
                        registers[number] = value
                    return registers[number]

                chip = SimpleNamespace(register=register)
                state = {'halted': False}
                target.link = lambda: contextlib.nullcontext((None, object(), chip, {}))
                target.state = Mock(return_value=state)
                target.halt = Mock()
                trigger = (0, [(0x21801000, 0)])
                target.trigger_snapshot = Mock(return_value=trigger)
                target.restore_triggers = Mock()
                def resume(_mem, _chip, _saved):
                    self.assertEqual(registers[RV_DCSR], 0x4000b703)
                    self.assertEqual(registers[0x7b1], 0x80006456)
                    return state

                target.restore_state = Mock(side_effect=resume)
                folder = Path(temp) / 'debug'
                context = self.assertRaisesRegex(ValueError, 'injected') if fail else contextlib.nullcontext()
                with context, target.live_debug(folder, Mock()):
                    registers[RV_DCSR] = 0x4000b703 | RV_DCSR_STEP
                    registers[0x7b1] = 0x80006456
                    if fail:
                        raise ValueError('injected')
                self.assertEqual(writes, [(RV_DCSR, 0x4000b703)])
                target.restore_triggers.assert_called_once_with(chip, trigger)
                self.assertTrue(json.loads((folder/'restored.json').read_text())['dcsrStepRestored'])

    def test_probe_identity_checks_live_profile_and_restores_usb_on_wrong_cable(self):
        from tools.board_acceptance import J7_PL_REGISTERS, JTAG_TIMING
        for same_board, matching_pl in [(True, True), (False, True), (True, False)]:
            driver = self.driver()
            driver.cable_serial = 'J7-cable'
            physical_regs = dict(J7_PL_REGISTERS)
            if not matching_pl:
                physical_regs[J7_PL_REGISTERS[0][0]] ^= 1
            usb_timing = [0]
            driver.physical = SimpleNamespace(read_words=lambda address: [
                (usb_timing[0] if same_board else 0) if address == JTAG_TIMING else physical_regs[address]])

            def timing(_tx, _rx, command):
                if command[1] != 255:
                    usb_timing[0] = command[1]
                return bytes([0x89, 0, usb_timing[0]]) + bytes(12)

            fake_dap = SimpleNamespace(open_dap=Mock(return_value=(object(), None, None)),
                                       drain=Mock(), xfer=timing)
            with patch.dict(sys.modules, {'tools.dap_pipeline_bench': fake_dap}), patch('usb.util.dispose_resources'):
                if same_board and matching_pl:
                    result = driver.verify_live_probe()
                    self.assertEqual(result['cableSerial'], 'J7-cable')
                    self.assertTrue(result['restored'])
                else:
                    with self.assertRaises(RuntimeError):
                        driver.verify_live_probe()
                self.assertEqual(usb_timing[0], 0)
                self.assertEqual(fake_dap.open_dap.call_count, int(matching_pl))


if __name__ == '__main__':
    unittest.main()
