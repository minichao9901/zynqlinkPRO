"""Reject invalid acceptance windows before creating output or opening hardware."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AcceptanceArgumentsTests(unittest.TestCase):
    def test_invalid_measurement_cannot_skip_verification(self):
        cases = [('validate_hpm6800_streams.py', ['--stage', 'hss', '--repeats', '0']),
                 ('validate_hpm6800_streams.py', ['--stage', 'rtt', '--seconds', '0']),
                 ('validate_hpm6800_performance.py', ['--loops', '0']),
                 ('validate_hpm6800_performance.py', ['--sustain-seconds', '-1'])]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'never-created'
            for script, args in cases:
                with self.subTest(script=script, args=args):
                    result = subprocess.run([sys.executable, str(ROOT/'tools'/script),
                        '--bit', 'missing.bit', '--elf', 'missing.elf', '--out', str(output), *args],
                        cwd=ROOT, capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn('must be positive', result.stderr)
                    self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
