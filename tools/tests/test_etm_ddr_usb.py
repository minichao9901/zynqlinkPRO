import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'etm-service/tools'))
import zynq_ddr as d
import zynq_la


def words(count=35,state=2,transfer=7,usb_state=65536,sent=None):
    w=[0]*44;w[:3]=[0x31554445,1,1]
    r=[0]*34;r[0]=0x45444d31;r[2]=state;r[3]=0x39c00000;r[4]=104857600;r[6]=r[7]=count
    r[12:14]=[0x39c00000,0x40000000]
    r[10]=1;r[17]=200000000;r[22]=count%16;r[24]=1;r[28]=0x46524d31;r[31]=2;r[33]=2
    w[4:38]=r;w[38]=transfer;w[40]=count;w[41]=count if sent is None else sent;w[42]=usb_state
    return w


def header(w):
    r=w[4:38];h=[0]*128
    h[:16]=[0x3144445a,1,w[38],r[10],r[31],r[32],0,r[7],r[7],r[28],r[22],r[18],r[17],r[29],512,r[2]]
    return struct.pack('<128I',*h)


class DdrUsbTests(unittest.TestCase):
    def setUp(self):
        self.dev=Mock();self.t=d.Transport(self.dev,Mock(),Mock())
        self.t.capture_id=1;self.t.nonce=2;self.t.ref_hz=200000000;self.t.requested_ticks=200000000
        self.t.arm_before_unix=100;self.t.active_observed_unix=100.002
        self.scratch=ROOT/'build/ddr-usb-host-tests';self.scratch.mkdir(parents=True,exist_ok=True)

    def test_partial_reads_and_wait_for_last_descriptor(self):
        w=words();active=words(usb_state=65536|258,sent=0)
        self.dev.ctrl_transfer.side_effect=[struct.pack('<44I',*x) for x in [w,active,w]]
        payload=bytes(range(35));self.dev.read.side_effect=[header(w),payload[:10],payload[10:]]
        with tempfile.TemporaryDirectory(dir=self.scratch) as temp,patch.object(d,'xfer',return_value=b'\x8c\0'+struct.pack('<44I',*w)) as command:
            path=Path(temp)/'capture.frm1';result=self.t.download(path)
            self.assertEqual(path.read_bytes(),payload)
            self.assertEqual(result['sha256'],hashlib.sha256(payload).hexdigest())
            args=struct.unpack('<BBH6I',command.call_args.args[2])
            self.assertEqual(args,(0x8c,3,0x4445,1,2,0,0,35,0))
            self.assertEqual(self.dev.ctrl_transfer.call_count,3)
            self.assertEqual(self.dev.read.call_count,3)

    def test_stale_header_is_rejected_before_payload_or_output_creation(self):
        w=words();bad=list(struct.unpack('<128I',header(w)));bad[3]=99
        self.dev.ctrl_transfer.return_value=struct.pack('<44I',*w)
        self.dev.read.return_value=struct.pack('<128I',*bad)
        with tempfile.TemporaryDirectory(dir=self.scratch) as temp,patch.object(d,'xfer',return_value=b'\x8c\0'+struct.pack('<44I',*w)):
            path=Path(temp)/'capture.frm1'
            with self.assertRaisesRegex(d.DdrError,'header'):self.t.download(path)
            self.assertFalse(path.exists());self.dev.read.assert_called_once()

    def test_active_capture_cannot_download(self):
        self.dev.ctrl_transfer.return_value=struct.pack('<44I',*words(state=1))
        with patch.object(d,'xfer') as command,self.assertRaisesRegex(d.DdrError,'retired'):
            self.t.download(self.scratch/'must-not-exist.frm1')
        command.assert_not_called();self.dev.read.assert_not_called()

    def test_full_buffer_is_normal_completion_and_bus_error_remains_error(self):
        w=words(count=104857600);w[4+27]=1;w[4+23]=2;w[4+17]=123456
        s=d.unpack(struct.pack('<44I',*w))
        s.update(requestedTicks=200000000,referenceHz=200000000,actualWindowSeconds=123456/200000000,
                 hardwareStartBracketUnix=[100,100.002],usbSeconds=3,usbPayloadMBps=34)
        q=d.quality(s)
        self.assertTrue(q['bufferFull']);self.assertTrue(q['captureComplete']);self.assertFalse(q['loss'])
        self.assertFalse(q['requestedWindowComplete'])
        s['registers'][9]=4
        q=d.quality(s);self.assertTrue(q['loss']);self.assertFalse(q['captureComplete'])

    def test_arm_uses_advertised_fixed_region_and_rejects_variable_quota(self):
        before=d.unpack(struct.pack('<44I',*words()))
        active=words(state=1);active[4+10]=2
        self.t.snapshot=Mock(return_value=before)
        self.t.command=Mock(return_value=d.unpack(struct.pack('<44I',*active)))
        self.t.arm(1,200000000,nonce=2)
        self.t.command.assert_called_once_with(1,200000000,104857600,2,0)
        self.dev.read.assert_not_called()
        self.t.command.reset_mock()
        with self.assertRaisesRegex(ValueError,'fixed 100 MiB'):
            self.t.arm(1,200000000,byte_limit=64<<20,nonce=2)
        self.t.command.assert_not_called()

    def test_advertised_ddr_is_the_default_session_path(self):
        s=zynq_la.Session();s.open=Mock();s.dev=Mock()
        s._control=Mock(return_value=[0x45544d31,0,0,0,0,0,120000000,0])
        s.dev.ctrl_transfer.return_value=struct.pack('<4I',200000000,0,0,0x301)
        s._start_ddr=Mock(return_value='ddr-started')
        self.assertEqual(s.start(),'ddr-started');s._start_ddr.assert_called_once()
        self.assertEqual(s._control.call_count,1,'must not arm legacy ZET1 before DDR')


if __name__=='__main__':unittest.main()
