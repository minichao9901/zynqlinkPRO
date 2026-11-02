import sys,struct,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analyze_usbpcap_cdc import extract
def packet(irp,info,data=b'',status=0):
    header=struct.pack('<HQIHBHHBBI',27,irp,status,9,info,3,8,0x83,3,len(data))
    p=header+data;return struct.pack('<4I',1,0,len(p),len(p))+p
class CaptureTests(unittest.TestCase):
    def run_capture(self,records,expected):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'test.pcap';p.write_bytes(struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,249)+records)
            return extract(p,3,8,expected=expected)
    def test_request_order_and_canceled_payload_are_kept_separate(self):
        raw=packet(1,0)+packet(2,0)+packet(2,1,b'cancel',0xc0010000)+packet(1,1,b'good')
        data,s=self.run_capture(raw,b'good')
        self.assertEqual(data,b'goodcancel');self.assertTrue(s['matchesWebSuccessfulOnly'])
        self.assertFalse(s['matchesWeb']);self.assertEqual(s['failedPayloadBytes'],6)
        self.assertEqual(s['reorderedCompletions'],2)
    def test_truncated_last_record_is_reported_not_invented_as_complete(self):
        data,s=self.run_capture(packet(1,0)+packet(1,1,b'ok')+packet(2,1,b'truncated')[:-3],b'ok')
        self.assertEqual(data,b'ok');self.assertGreater(s['incompleteTailBytes'],0)
if __name__=='__main__':unittest.main()
