import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('zynq_trace_cli_test', ROOT / 'etm-service/trace.py')
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


class TraceCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / 'target.elf'
        self.image.write_bytes(b'target')
        self.record = self.root / 'record'
        self.args = ['--elf', str(self.image), '--bit', str(self.image), '--zynq-elf', str(self.image),
                     '--out', str(self.record), '--trace-id', '7', '--swd-khz', '999', '--no-decode']
        self.calls = []

    def board(self, command, **kwargs):
        self.calls.append(command)
        self.record.mkdir(exist_ok=True)
        (self.record / 'target-before.json').write_text('{"etmcr":123}')
        (self.record / 'acceptance.json').write_text(json.dumps({
            'config': {'protocol': 'ETMv3', 'traceid': 7}, 'quality': {'loss': False}, 'etm_sha256': 'test'}))
        (self.record / 'etm.bin').write_bytes(b'actual captured bytes')
        return SimpleNamespace(returncode=0)

    def call(self, args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), patch.object(trace, 'zynq_status', return_value={'ready': True}), patch.object(trace.subprocess, 'run', side_effect=self.board):
            code = trace.capture(args)
        return code, json.loads(stdout.getvalue())

    def test_trace_id_and_swd_clock_are_forwarded_and_snapshot_preserved(self):
        code, result = self.call(self.args)
        self.assertEqual(code, 0)
        command = self.calls[0]
        self.assertEqual(command[command.index('--trace-id') + 1], '7')
        self.assertEqual(command[command.index('--speed-khz') + 1], '999')
        self.assertEqual(json.loads((self.record / 'target-before.json').read_text()), {'etmcr': 123})
        self.assertFalse(result['result']['quality']['loss'])

    def test_invalid_trace_id_fails_before_board_access(self):
        args = self.args.copy()
        args[args.index('--trace-id') + 1] = '127'
        code, result = self.call(args)
        self.assertEqual(code, 2)
        self.assertFalse(result['ok'])
        self.assertEqual(self.calls, [])

    def test_existing_json_output_rejected_before_hardware(self):
        output = self.root / 'result.json'
        output.write_text('keep me')
        code, _ = self.call(self.args + ['--json-out', str(output)])
        self.assertEqual(code, 2)
        self.assertEqual(output.read_text(), 'keep me')
        self.assertEqual(self.calls, [])

    def test_decode_failure_keeps_record_and_capture_quality_in_json(self):
        def decode(*args, **kwargs):
            raise ValueError('BAD_SEQUENCE')
        with patch.dict('sys.modules', {'decode_stream': SimpleNamespace(decode_stream=decode)}):
            code, result = self.call(self.args[:-1])
        self.assertEqual(code, 5)
        self.assertFalse(result['ok'])
        self.assertFalse(result['result']['quality']['loss'])
        self.assertEqual(Path(result['result']['record']).resolve(), self.record.resolve())
        self.assertTrue((self.record / 'capture.bin').is_file())


if __name__ == '__main__':
    unittest.main()
