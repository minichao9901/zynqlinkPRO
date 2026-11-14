import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools.run_board_acceptance import (BOARDS, BUSINESSES, ENDINGS, FEATURES, Pending,
                                        Report, Unsafe, campaign, plan, review, rotation)


class TestBoardAcceptance(unittest.TestCase):
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
            def evidence(board, only, serial='12345678', suffix=''):
                cases = plan(board, None, only, 7)
                files = {name: {'sha256': name} for name in ('bit', 'zynqElf', 'targetElf')}
                path = Path(temp) / (board + suffix + '.json')
                records = [dict(case, status='not-applicable' if 'notApplicable' in case else 'pass')
                           for case in cases]
                path.write_text(json.dumps(dict(board=board, revision='abc', probeSerial=serial, files=files,
                    seed=7, finishedAt='2026-11-14T10:00:00+00:00', status='pass', plan=cases,
                    results=[{'id': 'preflight', 'status': 'pass'}, *records,
                             {'id': 'final-state', 'status': 'pass'}])), encoding='utf-8')
                return path

            first = evidence('f103ze', FEATURES)
            h7 = evidence('h743', set(FEATURES)-{'etm'})
            hpm = evidence('hpm6800evk', FEATURES)
            self.assertEqual(review([first, h7, hpm])['status'], 'incomplete')
            etm = evidence('h743', {'etm'}, suffix='-etm')
            self.assertTrue(review([first, h7, hpm, etm])['accepted'])
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
        data[20] ^= 1
        with self.assertRaises(RuntimeError):
            jsp_data(definition + data, 0xf0404800, 1, 25_000_000)

    def test_unknown_browser_write_blocks_further_commands(self):
        from types import SimpleNamespace
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


if __name__ == '__main__':
    unittest.main()
