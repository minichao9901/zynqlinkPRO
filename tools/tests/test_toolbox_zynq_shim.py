import sys
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'tools'));sys.path.insert(0,str(root/'etm-service/tools'))
from zynq_la import Session,CaptureError


class ZynqShimTests(unittest.TestCase):
    def test_restart_unlocks_etm_and_requires_both_programming_handshakes(self):
        session=Session();session.config={'protocol':'ETMv3','ctrl':0x810}
        session._dap_write32=Mock();session._dap_read32=Mock(side_effect=[2,0])
        session._restart_trace()
        self.assertEqual(session._dap_write32.call_args_list[0].args,(0xe0041fb0,0xc5acce55))
        session._dap_read32=Mock(return_value=0)
        with patch('zynq_la.time.sleep'),self.assertRaises(CaptureError):session._restart_trace()
        session._dap_read32=Mock(return_value=2)
        with patch('zynq_la.time.sleep'),self.assertRaises(CaptureError):session._restart_trace()


if __name__=='__main__':unittest.main()
