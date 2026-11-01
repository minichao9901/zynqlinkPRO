import sys
from pathlib import Path
import unittest
import importlib.util
from unittest.mock import Mock,patch

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'tools'));sys.path.insert(0,str(root/'etm-service/tools'))
from zynq_la import Session,CaptureError,Vis


class ZynqShimTests(unittest.TestCase):
    def test_packaged_dap_setup_supports_exact_hz_and_checks_clock_ack(self):
        spec=importlib.util.spec_from_file_location('etm_dap_fixture',root/'etm-service/tools/dap_pipeline_bench.py')
        dap=importlib.util.module_from_spec(spec);spec.loader.exec_module(dap)
        def reply(_out,_inp,packet):
            return bytes([2,1]) if packet[0]==2 else bytes([5,1,1,0x77,0x14,0xa0,0x1b]) if packet[:4]==[5,0,1,2] else bytes([packet[0],0])
        with patch.object(dap,'drain'),patch.object(dap,'cmd',side_effect=reply) as cmd:
            dap.setup(None,None,1000,speed_hz=10000000)
            self.assertIn([0x11]+dap.le(10000000),[call.args[2] for call in cmd.call_args_list])
        with patch.object(dap,'drain'),patch.object(dap,'cmd',side_effect=[bytes([2,1]),bytes([0x11,255])]),self.assertRaises(RuntimeError):
            dap.setup(None,None,10000)

    def test_capture_handoff_preserves_selected_swd_clock_through_usb_open(self):
        for hz in [1000000,10000000]:
            probe=Session()
            probe._dap_write32=Mock()
            vis=Vis();vis.swd_hz=hz
            with patch('zynq_la.session',return_value=probe),patch.object(probe,'start',side_effect=probe.open),\
                 patch('zynq_la.open_dap',return_value=(Mock(),Mock(),Mock())),patch('zynq_la.setup') as setup:
                vis.sock.sendall(b'start')
                self.assertEqual(setup.call_args.kwargs['speed_hz'],hz)
                self.assertEqual(setup.call_args.args[2],hz//1000)

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
