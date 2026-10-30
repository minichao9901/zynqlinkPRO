import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'etm-service/tools'))
from native_stimulus import SerialStimulus


class Echo:
    def __init__(self):
        self.written = []
        self.closed = False
    def reset_input_buffer(self): pass
    def write(self, data): self.written.append(data)
    def flush(self): pass
    def read(self, count): return self.written[-1][:count]
    def close(self): self.closed = True


class StimulusTests(unittest.TestCase):
    def test_no_send_before_arm_and_echo_rounds_are_byte_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / 'ready.json'
            echo = Echo()
            stimulus = SerialStimulus({'port': 'COM-test', 'payload': 'test\r\n', 'rounds': 3, 'intervalSeconds': 0}, ready, 1)
            with patch('native_stimulus.serial.Serial', return_value=echo):
                stimulus.prepare()
                time.sleep(.01)
                self.assertEqual(echo.written, [])
                ready.write_text(json.dumps({'armed': True, 'monotonic': time.monotonic()}))
                stimulus.thread.join(1)
                report = stimulus.close()
            self.assertTrue(report['ok'])
            self.assertEqual(len(echo.written), 3)
            self.assertTrue(echo.closed)

    def test_failed_capture_without_arm_does_not_send_serial_data(self):
        with tempfile.TemporaryDirectory() as directory:
            echo = Echo()
            stimulus = SerialStimulus({'port': 'COM-test', 'payload': 'test', 'rounds': 1, 'intervalSeconds': 0}, Path(directory) / 'not-armed', 1)
            with patch('native_stimulus.serial.Serial', return_value=echo):
                stimulus.prepare()
                report = stimulus.close()
            self.assertFalse(report['armed'])
            self.assertFalse(report['ok'])
            self.assertEqual(echo.written, [])


if __name__ == '__main__':
    unittest.main()
