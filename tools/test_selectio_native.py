"""Exercise framed WinUSB request ordering without claiming a USB interface."""
import argparse
from collections import deque
import struct
import unittest
from unittest.mock import Mock, patch

from selectio_cli import connection, selectio_clock_number
from selectio_native import HEADER, NativeStatusError, NativeStream


class NativeCliTests(unittest.TestCase):
    def test_clock_parser_returns_hertz(self):
        self.assertEqual(selectio_clock_number("73000000"), 73000000)
        with self.assertRaises(argparse.ArgumentTypeError):
            selectio_clock_number("100000001")

    def test_dap_context_releases_handle_on_command_error(self):
        device, transmit, receive = object(), object(), object()
        with patch("selectio_cli.open_dap", return_value=(device, transmit, receive)) as open_dap, \
                patch("selectio_cli.usb.util.dispose_resources") as dispose:
            with self.assertRaisesRegex(RuntimeError, "failed command"):
                with connection("12345678") as endpoints:
                    self.assertEqual(endpoints, (transmit, receive))
                    raise RuntimeError("failed command")
            open_dap.assert_called_once_with("12345678")
            dispose.assert_called_once_with(device)


class Endpoint:
    def __init__(self, advertised=16384, fail_sequence=None):
        self.advertised = advertised
        self.fail_sequence = fail_sequence
        self.replies = deque()
        self.events = []

    def queue(self, channel, op, seq, payload, status=0):
        frame = HEADER.pack(b"ZLK1", channel, op, status, 0, seq, len(payload)) + payload
        self.replies.append(frame + (b"\0" if len(frame) % 512 == 0 else b""))

    def write(self, endpoint, frame, timeout):
        magic, channel, op, _, _, seq, size = HEADER.unpack_from(frame)
        assert magic == b"ZLK1" and endpoint == 1
        data = frame[HEADER.size:HEADER.size + size]
        self.events.append(("out", seq))
        if (channel, op) == (0, 0):
            payload = struct.pack("<4sIII", b"SIO1", 200000000, 128, self.advertised)
        elif (channel, op) == (0, 5):
            payload = struct.pack("<4sIIIII", b"CAP1", 1, 4, 16, 4096, 133333333)
        elif (channel, op) == (0, 8):
            payload = data
        else:
            write, _, count, address = struct.unpack_from("<BBHI", data)
            self.assert_transfer_shape(channel, op, data, write, count)
            payload = struct.pack("<I", count).ljust(16, b"\0")
            if not write:
                payload += struct.pack("<I", address) * count
        self.queue(channel, op, seq, payload, int(seq == self.fail_sequence))
        return len(frame)

    @staticmethod
    def assert_transfer_shape(channel, op, data, write, count):
        assert (channel, op) in ((1, 6), (7, 6))
        assert len(data) == 16 + (4 * count if write else 0)

    def read(self, endpoint, capacity, timeout):
        frame = self.replies.popleft()
        assert endpoint == 0x84 and len(frame) <= capacity
        self.events.append(("in", HEADER.unpack_from(frame)[5]))
        return frame


class NativeFrameTests(unittest.TestCase):
    def test_negotiation_and_previous_session(self):
        for advertised in (4096, 16384):
            with self.subTest(advertised=advertised):
                usb = Endpoint(advertised)
                usb.queue(7, 6, 99, bytes(16000))
                native = NativeStream(usb, 0)
                self.assertEqual(native.info()["negotiated_frame"], advertised)
                self.assertEqual(native.max_bulk, advertised - 64)
                if advertised == 4096:
                    with self.assertRaises(ValueError):
                        native.set_frame_size(16384)
                else:
                    address = 0x20000020
                    n = native.max_bulk
                    self.assertEqual(native.bulk_many([(address, n, None), (address, n, bytes(n))],
                                                     transport_only=True), [struct.pack("<I", address)*(n//4), b""])
                    native.set_frame_size(4096)
                self.assertEqual(native.max_bulk, 4032)

    def test_credit_order_and_sequence_wrap(self):
        for sliding, directions in ((True, "oooioioioiii"), (False, "oooiiioooiii")):
            with self.subTest(sliding=sliding):
                usb = Endpoint()
                native = NativeStream(usb, 0xfffffffe, dma=True, max_depth=3, sliding=sliding)
                addresses = list(range(0x20000000, 0x20000018, 4))
                results = native.bulk_many(((a, 4, None) for a in addresses), depth=4)
                self.assertEqual(results, [struct.pack("<I", a) for a in addresses])
                self.assertEqual("".join(e[0] for e, _ in usb.events), directions)
                self.assertEqual(native.sequence, 4)

    def test_failed_response_drains_only_outstanding(self):
        for sliding in (True, False):
            with self.subTest(sliding=sliding):
                usb = Endpoint(fail_sequence=1)
                native = NativeStream(usb, 0, dma=True, max_depth=3, sliding=sliding)
                with self.assertRaises(NativeStatusError):
                    native.bulk_many([(0x20000000, 4, None)] * 9)
                sent = [s for e, s in usb.events if e == "out"]
                self.assertEqual(sent, list(range(4 if sliding else 3)))
                self.assertEqual([s for e, s in usb.events if e == "in"], sent)
                self.assertEqual(native.bulk(0x20000000, 4), struct.pack("<I", 0x20000000))

    def test_memory_clock_uses_the_active_queue(self):
        native = NativeStream(None, 0, advertised_frame=16384)
        for port, timing, divider in [(1, 0x1080, 4), (1, 0x1081, 2), (2, 0x600004, 4), (2, 0x780002, 2)]:
            native.exchange = Mock(return_value=struct.pack("<4I", 199999998, port, timing, 8))
            record = native.memory_clock(port, 200000000, 100000000)
            self.assertEqual(record["wire_hz"], 199999998//divider)
            self.assertEqual(record["timing"], hex(timing))
        native.advertised_frame = 4096
        native.exchange = Mock(side_effect=AssertionError("legacy probe queried for new operation"))
        self.assertEqual(native.memory_clock(1, 199999998, 50000000)["wire_hz"], 49999999)


if __name__ == "__main__":
    unittest.main()
