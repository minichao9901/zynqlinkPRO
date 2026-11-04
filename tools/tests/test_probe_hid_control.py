import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from probe_hid_control import HidControl


class Hid:
    def __init__(self,legacy=False):self.pending=[];self.writes=[];self.legacy=legacy
    def write(self,p):
        p=bytes(p);self.writes.append(p);reply=bytearray(64);reply[0]=2;reply[2]=p[2]
        if p[2]==0x13:
            version=b'0.5-orbtrace' if self.legacy else b'0.6-nonce32'
            reply[1]=len(version)+1;reply[3:3+len(version)]=version
        else:
            reply[1]=50;reply[4]=1
            stale=bytearray(reply);stale[4]=0
            self.pending.append(stale) # Old STATUS looks like START, except nonce.
        if not self.legacy:reply[60:64]=p[60:64]
        self.pending.append(reply);return len(p)
    def read(self,n,timeout):return self.pending.pop(0) if self.pending else b''


class HidTests(unittest.TestCase):
    def test_late_same_command_status_cannot_confirm_a_new_start(self):
        d=Hid();c=HidControl(d);self.assertTrue(c.negotiate())
        p=bytes([2,0x31,1])+bytes(60)
        reply=c.exchange(p)
        self.assertEqual(reply[4],1);self.assertEqual(c.stale,1)
        self.assertEqual(len(d.writes),2) # one version + one START, no replay

    def test_old_firmware_is_not_falsely_advertised_as_correlated(self):
        c=HidControl(Hid(legacy=True));self.assertFalse(c.negotiate())

    def test_oversized_payload_cannot_overwrite_the_correlation_field(self):
        d=Hid();c=HidControl(d);c.negotiate()
        with self.assertRaises(ValueError):c.exchange(bytes([59,0x31])+bytes(61))
        self.assertEqual(len(d.writes),1)
