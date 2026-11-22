"""Exercise RTT STOP and reader failure handling without opening USB."""
import unittest
from unittest.mock import Mock, call, patch

from benchmark_rtt_forward import Reader, stop_rtt_capture


class RttStopTests(unittest.TestCase):
    def test_stop_retries_busy_and_returns_latest_drained_count(self):
        probe = Mock()
        probe.action.side_effect = [(-7, (1, 0, 0, 2048)), (-7, (1, 0, 0, 4096)),
                                    (0, (0, 0, 0, 6144))]
        attempts = []
        with patch("benchmark_rtt_forward.time.sleep") as sleep:
            final = stop_rtt_capture(probe, attempts=attempts)
        self.assertEqual(final[3], 6144)
        self.assertEqual([row["rc"] for row in attempts], [-7, -7, 0])
        self.assertEqual(probe.action.call_args_list, [call(0x31, 0)]*3)
        self.assertEqual(sleep.call_args_list, [call(.005), call(.005)])

    def test_stop_neither_retries_a_protocol_error_nor_exceeds_timeout(self):
        probe = Mock()
        probe.action.return_value = (-4, ())
        with self.assertRaisesRegex(RuntimeError, "RTT STOP failed: -4"):
            stop_rtt_capture(probe)
        probe.action.assert_called_once_with(0x31, 0)
        probe.action.reset_mock()
        probe.action.return_value = (-7, ())
        with patch("benchmark_rtt_forward.time.monotonic", side_effect=[0, 4.1]):
            with self.assertRaisesRegex(RuntimeError, "RTT STOP failed: -7"):
                stop_rtt_capture(probe)
        probe.action.assert_called_once_with(0x31, 0)

    def test_reader_error_wakes_the_measurement(self):
        com = Mock()
        com.read.side_effect = OSError("mock CDC failure")
        reader = Reader(com)
        reader.run()
        self.assertTrue(reader.failed.is_set())
        self.assertIn("mock CDC failure", reader.error)


if __name__ == "__main__":
    unittest.main()
