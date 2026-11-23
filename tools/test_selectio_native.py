"""Exercise framed WinUSB request ordering without claiming a USB interface."""
import argparse
import contextlib
import io
from collections import deque
import struct
import unittest
from unittest.mock import Mock, patch

from selectio_cli import connection, main, selectio_clock_number
from selectio_native import HEADER, NativeStatusError, NativeStream
from selectio_scope import verify_scope_tail


class NativeCliTests(unittest.TestCase):
    def test_scope_stop_requires_a_matching_terminal_stat(self):
        frame = bytearray(512)
        struct.pack_into("<HBBIIHH", frame, 0, 0x4a53, 2, 3, 4, 0, 0, 0)
        struct.pack_into("<III", frame, 16, 20, 0, 5)
        verify_scope_tail(frame, 5 * 512, 20)
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            verify_scope_tail(frame, 5 * 512, 21)
        frame[3] = 2
        with self.assertRaisesRegex(ValueError, "terminal STAT"):
            verify_scope_tail(frame, 5 * 512, 20)

    def test_invalid_stream_and_memory_timing_fail_without_usb(self):
        cases = (
            (["profile", "--transport", "swd", "--tap", "8", "--slot", "24", "--idle", "16"], "SWD idle"),
            (["scope", "--transport", "jtag", "--clock", "73000000", "--tap", "16", "--slot", "15",
              "--idle", "25", "--period", "264", "--var", "0x20008a00:4:4", "--seconds", "1",
              "--out", "unused.hss"], "JTAG sample slot"),
            (["rtt-send", "--transport", "jtag", "--tap", "16", "--slot", "28", "--idle", "28",
              "--address", "0x20008000", "--text", "probe"], "require odd idle"),
        )
        for argv, reason in cases:
            with self.subTest(argv=argv), patch("sys.argv", ["selectio", *argv]), \
                    patch("selectio_cli.connection") as dap, patch("selectio_cli.native_connection") as native, \
                    contextlib.redirect_stderr(io.StringIO()) as diagnostics:
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                self.assertIn(reason, diagnostics.getvalue())
                dap.assert_not_called()
                native.assert_not_called()

    def test_live_jtag_still_accepts_even_idle(self):
        argv = ["selectio", "profile", "--transport", "jtag", "--tap", "16", "--slot", "28", "--idle", "28"]
        with patch("sys.argv", argv), patch("selectio_cli.native_connection") as native, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        device = native.return_value.__enter__.return_value
        device.exchange.assert_called_once_with(0, 2, bytes((2, 16, 28, 28)))

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
    def test_split_pipe_routing_and_sequence_spaces(self):
        usb = Mock()
        usb.write.side_effect = lambda endpoint, data, timeout: len(data)
        native = NativeStream(usb, 90, split=True)
        requests = [(6, 2), (6, 4), (6, 1), (1, 6), (8, 6), (4, 2)]
        expected = [(5, 0x88, 90), (5, 0x85, 91), (7, 0x87, 90),
                    (6, 0x86, 90), (7, 0x87, 91), (10, 0x8a, 90)]
        pending = [native._write(channel, operation, b"") for channel, operation in requests]
        for call, (out, _, seq) in zip(usb.write.call_args_list, expected):
            endpoint, frame = call.args
            self.assertEqual(endpoint, out)
            self.assertEqual(HEADER.unpack_from(frame)[5], seq)
        for (channel, operation), (_, inp, seq), pending_seq in zip(requests, expected, pending):
            usb.read.return_value = HEADER.pack(b"ZLK1", channel, operation, 0, 0, seq, 0)
            self.assertEqual(native._read(channel, operation, pending_seq), b"")
            self.assertEqual(usb.read.call_args.args[0], inp)

    def test_split_session_discards_stale_frames_once_per_in_pipe(self):
        usb = Mock()
        native = NativeStream(usb, 15, split=True)
        native.unsynchronized_in = {0x86, 0x87}
        stale = HEADER.pack(b"ZLK1", 1, 6, 0, 0, 10, 0)
        current = HEADER.pack(b"ZLK1", 1, 6, 0, 0, 15, 0)
        usb.read.side_effect = [stale, current, stale]
        self.assertEqual(native._read(1, 6, 15), b"")
        self.assertEqual(native.unsynchronized_in, {0x87})
        with self.assertRaisesRegex(RuntimeError, "expected"):
            native._read(1, 6, 16)

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
