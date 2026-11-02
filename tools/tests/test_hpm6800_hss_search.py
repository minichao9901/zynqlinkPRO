"""Run the real HSS search loop with a modeled sample frontier; no hardware."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]


class HssSearchTests(unittest.TestCase):
    def test_fixture_and_idle_options_reach_scan_refine_and_verify(self):
        tree = ast.parse((ROOT/'tools/validate_hpm6800_streams.py').read_text())
        loop = next(n for n in ast.walk(tree) if isinstance(n, ast.For)
            and isinstance(n.iter, ast.Name) and n.iter.id == 'counts'
            and any(isinstance(s, ast.Assign) and any(isinstance(t, ast.Tuple) for t in s.targets) for s in n.body))
        fixture = bytes(range(256))*16
        calls, records = [], []
        def point(*args, **kwargs):
            self.assertEqual(args[7], fixture[256:288])
            self.assertEqual(kwargs, dict(allow_low_clock=True, base=0x0123ff00, observe_scans=True, idle_cycles=20))
            calls.append(args[4])
            return dict(skipped=0 if args[4] >= 2000 else 1, effective_Hz=12000)
        state = dict(counts=[1], a=SimpleNamespace(hss_base=0x0123ff00, observe_scans=True, idle=20, seconds=10, repeats=3),
            hss_point=point, fixture=fixture, probe=None, mem=None, dev=None, speed=60000000,
            record=lambda row: records.append(dict(row)), report=dict(summary=[]), save=lambda: None)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])), '<real HSS search>', 'exec'), state)
        self.assertEqual({r['tag'] for r in records}, {'scan','refine','verify'})
        self.assertEqual(len([r for r in records if r['tag']=='verify']), 3)
        self.assertTrue(state['report']['summary'][0]['zero_skip'])
        self.assertGreater(len(calls), 10)


if __name__ == '__main__':
    unittest.main()
