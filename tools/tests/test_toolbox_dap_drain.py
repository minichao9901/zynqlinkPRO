import unittest
from pathlib import Path
import sys
import usb.core
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from native_probe import drain_dap_replies

class DrainTests(unittest.TestCase):
    def test_late_response_is_drained_before_the_quiet_interval(self):
        class Device:
            delay=50
            timeouts=[]
            def read(self,ep,length,timeout):
                self.timeouts.append(timeout)
                if self.delay is None:raise usb.core.USBTimeoutError('quiet')
                if timeout<self.delay:
                    self.delay-=timeout;raise usb.core.USBTimeoutError('still processing')
                self.delay=None;return b'\x03\x00'
        device=Device();self.assertEqual(drain_dap_replies(device),1)
        self.assertEqual(device.timeouts,[80,80])

    def test_a_nonquiet_endpoint_is_rejected_instead_of_claimed_clean(self):
        class Device:
            def read(self,*args,**kwargs):return b'\x03\x00'
        with self.assertRaisesRegex(ValueError,'未静默'):drain_dap_replies(Device(),limit=3)

if __name__=='__main__':unittest.main()
