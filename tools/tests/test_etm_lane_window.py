from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from calibrate_etm_lanes import choose_window,excitation


class LaneWindowTests(unittest.TestCase):
    def test_only_fully_measured_nonwrapping_windows_are_candidates(self):
        self.assertIsNone(choose_window({i:True for i in range(31)}))
        points={i:8<=i<=18 for i in range(32)}
        self.assertEqual(choose_window(points)['tap'],13)
        self.assertEqual(choose_window(points)['width'],11)
        self.assertIsNone(choose_window({i:i<3 or i>28 for i in range(32)}))
        self.assertEqual(choose_window({i:True for i in range(32)})['tap'],15)

    def test_unexcited_lanes_cannot_claim_a_window_from_clean_parser_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'frames';path.write_bytes(bytes(4096))
            self.assertFalse(excitation(path)['excited'])
            path.write_bytes(bytes(range(256))*32)
            self.assertTrue(excitation(path)['excited'])


if __name__=='__main__':unittest.main()
