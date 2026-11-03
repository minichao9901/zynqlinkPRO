"""A benchmark must never post a decode job to a prior runtime's port."""
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest


class BenchmarkPortTests(unittest.TestCase):
    def test_busy_port_is_rejected_before_record_creation(self):
        root = Path(__file__).resolve().parents[2]
        with socket.socket() as listener, tempfile.TemporaryDirectory() as temp:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            output = Path(temp) / 'must-not-exist'
            result = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'tools/bench_etm_native_offline.py'),
                '--record', str(Path(temp) / 'missing'), '--out', str(output),
                '--port', str(listener.getsockname()[1]), '--repeat', '1'],
                capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn('already listening', result.stderr.decode('utf8', 'replace'))
            self.assertFalse(output.exists())
            listener.settimeout(1)
            connection, _ = listener.accept()
            with connection:
                self.assertEqual(connection.recv(100), b'')  # no HTTP request or mutation


if __name__ == '__main__':
    unittest.main()
