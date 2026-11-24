"""Offline regressions for case coverage, identity gates and capture checks."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

from fusion_acceptance import (create_campaign, find_case, load_plan, probe_identity,
                               required_pair, select_target, targets, validate_point,
                               validated_campaign, verify_load_receipt)
from fusion_evidence import compare_pattern, compare_stream, u32_sequence


class FusionAcceptanceTests(unittest.TestCase):
    def test_inventory_covers_all_packaged_images_and_unique_cases(self):
        plan = load_plan()
        case_ids = [row['id'] for row in plan['cases']]
        self.assertEqual(len(case_ids), 46)
        self.assertEqual(len(set(case_ids)), len(case_ids))
        image_manifests = {
            Path(t['manifest']).resolve()
            for case in plan['cases'] for t in targets(case) if t.get('manifest')
        }
        self.assertEqual(image_manifests, set(ROOT.glob('firmware/target/*/images/*/manifest.json')))
        for item in plan['cases']:
            execution = item['execution']
            self.assertIn(execution['mode'], ('scripted-point', 'blocked'))
            self.assertTrue(execution['pending'])
            self.assertTrue((ROOT / execution['script']).is_file())
            if item.get('requiresScopeApproval'):
                self.assertEqual(execution['mode'], 'blocked')

    def test_case_rejects_unlisted_operating_points(self):
        plan = load_plan()
        case = find_case(plan, 'fusion-h743-combo')
        point = argparse.Namespace(transport='swd', rate=50_000_000, tap=16, slot=24, idle=3,
                                   channels=8, group_rate=1000)
        validate_point(case, plan['profiles'], point)
        self.assertEqual(select_target(case, 'performance-dtcm')['image'], 'performance-dtcm')
        with self.assertRaisesRegex(ValueError, '--image'):
            select_target(case, None)
        point.rate = 48_000_000
        with self.assertRaisesRegex(ValueError, '--transport'):
            validate_point(case, plan['profiles'], point)

    def test_hpm_points_require_the_single_tap_profile(self):
        plan = load_plan()
        case = find_case(plan, 'fusion-hpm6800evk-scope')
        point = argparse.Namespace(transport='riscv-jtag', rate=25_000_000, tap=None, slot=None,
                                   idle=None, channels=8, group_rate=1000)
        validate_point(case, plan['profiles'], point)
        point.tap = 16
        with self.assertRaisesRegex(ValueError, 'single-TAP'):
            validate_point(case, plan['profiles'], point)
        combo = find_case(plan, 'fusion-hpm6800evk-combo')
        self.assertEqual(combo['execution']['mode'], 'blocked')

    def test_load_receipt_requires_all_hashes_and_actual_serials(self):
        pair = required_pair()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            campaign = create_campaign(pair, 'USB', out / 'campaign')
            self.assertEqual(campaign['probe'], probe_identity(pair))
            receipt_path = out / 'load.json'
            files = campaign['probe']['files']
            receipt = {'passed': True, 'operation': 'JTAG/RAM', 'cableSerial': 'HS3', 'usbSerial': 'USB',
                       'files': dict(bit=files['probe.bit'], zynq_elf=files['application.elf'],
                                     ps_init=files['ps7_init.tcl'])}
            receipt_path.write_text(json.dumps(receipt), encoding='utf8')
            self.assertEqual(verify_load_receipt(receipt_path, campaign, 'HS3')['path'], str(receipt_path.resolve()))
            with self.assertRaisesRegex(ValueError, 'USB serial'):
                verify_load_receipt(receipt_path, campaign, 'OTHER')
            other = ROOT / 'prebuilt/selectio-spi-pad-filter-v2-20261124/manifest.json'
            other_hashes = json.loads(other.read_text(encoding='utf8'))['hashes']
            self.assertEqual(other_hashes['application.elf'], files['application.elf']['sha256'])
            receipt['files']['bit'] = {'sha256': other_hashes['probe.bit']}
            receipt_path.write_text(json.dumps(receipt), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'probe.bit'):
                verify_load_receipt(receipt_path, campaign, 'HS3')

    def test_fusion_campaign_is_pinned_to_exact_raw4_pair(self):
        pair = required_pair()
        self.assertEqual(pair.name, 'selectio-usb-split-raw4-20261123')
        old = ROOT / 'prebuilt/selectio-spi-pad-filter-v2-20261124'
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'campaign'
            with self.assertRaisesRegex(ValueError, 'requires the RAW4 ABI 2 pair'):
                create_campaign(old, 'USB', out)
            self.assertFalse(out.exists())

            campaign = create_campaign(None, 'USB', out)
            path = out / 'campaign.json'
            self.assertEqual(validated_campaign(path), (campaign, pair))
            path.write_text(json.dumps({**campaign, 'plan': 'fusion-full-acceptance-v1'}), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'Create a new RAW4 ABI 2 campaign'):
                validated_campaign(path)
            campaign['probe']['manifest'] = str(old / 'manifest.json')
            path.write_text(json.dumps(campaign), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'requires the RAW4 ABI 2 pair'):
                validated_campaign(path)

    def test_load_cli_threads_serial_into_both_tools_without_hardware(self):
        pair = required_pair()
        run = subprocess.run([sys.executable, '-X', 'utf8', 'tools/probe_load.py', '--pair', str(pair),
                              '--cable-serial', 'STUB-HS3', '--usb-serial', 'STUB-USB', '--dry-run'],
                             cwd=ROOT, capture_output=True, encoding='utf8', check=True)
        result = json.loads(run.stdout)
        self.assertEqual(result['usbSerial'], 'STUB-USB')
        self.assertEqual(result['commands']['load'][-3], 'STUB-HS3')
        self.assertEqual(result['commands']['verify'][-2:], ['--cable-serial', 'STUB-HS3'])

    def test_etm_releases_enumeration_handles_before_capture(self):
        from fusion_acceptance_run import run_etm

        matching = Mock(manufacturer='CherryUSB', serial_number='USB')
        other = Mock(manufacturer='Other probe')
        case = find_case(load_plan(), 'fusion-f103ze-etm-golden')
        target = select_target(case, None)
        with tempfile.TemporaryDirectory() as directory, \
             patch('usb.core.find', return_value=iter((matching, other))), \
             patch('usb.util.dispose_resources') as dispose, \
             patch('fusion_acceptance_run.run_capture') as capture:
            def check_released(*_):
                self.assertEqual([call.args[0] for call in dispose.call_args_list], [matching, other])

            capture.side_effect = check_released
            result = run_etm(case, required_pair(), Path(directory), target, 'USB')
            self.assertEqual(len(result['captures']), 3)
            self.assertEqual(capture.call_count, 6)

    def test_clock_profile_tolerates_reference_rounding_and_rtt_truncation(self):
        from fusion_evidence import Blocked
        from fusion_performance import matching_clock, matching_rtt_clock

        matching_clock(49_999_999, 50_000_000)
        matching_clock(99_999_998, 100_000_000)
        matching_rtt_clock(49, 50_000_000)
        matching_rtt_clock(72, 72_727_273)
        with self.assertRaises(Blocked):
            matching_clock(49_000_000, 50_000_000)
        with self.assertRaises(Blocked):
            matching_rtt_clock(48, 50_000_000)

    def test_binary_checks_reject_gap_truncation_or_wrong_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            actual = Path(directory) / 'capture.bin'
            expected = Path(directory) / 'expected.bin'
            actual.write_bytes(struct.pack('<3I', 0xffffffff, 0, 1))
            self.assertEqual(u32_sequence(actual)['next'], 2)
            actual.write_bytes(struct.pack('<2I', 1, 3))
            with self.assertRaisesRegex(ValueError, 'expected 0x2'):
                u32_sequence(actual)
            actual.write_bytes(b'abcab')
            expected.write_bytes(b'abc')
            self.assertEqual(compare_pattern(actual, expected)['bytes'], 5)
            with self.assertRaisesRegex(ValueError, 'offset 3'):
                compare_stream(actual, expected)
            expected.write_bytes(b'abb')
            with self.assertRaisesRegex(ValueError, 'offset 2'):
                compare_pattern(actual, expected)


if __name__ == '__main__':
    unittest.main()
