"""Exercise the SPI CDC stream verifier without opening a serial device."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from selectio_spi_cdc_test import capture


class SerialInput:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []
        self.offset = 0

    def read(self, size):
        self.requests.append(size)
        end = min(self.offset + size, len(self.payload))
        data = self.payload[self.offset:end]
        self.offset = end
        return data


class SpiCdcCaptureTests(unittest.TestCase):
    def test_large_payload_uses_bulk_reads(self):
        payload = bytes(range(256)) * 512
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected.bin"
            path.write_bytes(payload)
            port = SerialInput(payload)
            result = capture(port, path, 1)
        self.assertEqual(port.requests, [1, 65535, 65536])
        self.assertEqual(result["bytes"], len(payload))
        self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertGreater(result["pc_receive_MBps"], 0)

    def test_mismatch_reports_absolute_offset(self):
        payload = bytes(65540)
        received = payload[:65538] + b"A" + payload[65539:]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected.bin"
            path.write_bytes(payload)
            with self.assertRaisesRegex(RuntimeError, r"byte 65538: got 41, expected 00"):
                capture(SerialInput(received), path, 1)


if __name__ == "__main__":
    unittest.main()
