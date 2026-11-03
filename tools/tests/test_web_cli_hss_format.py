"""Check real Web v1/v2 wire layouts without weakening value/sequence checks."""
import struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmark_web_cli_25 import validate_hss

def packet(version,seq,stamp,value=0x68001234):
    b=bytearray(512);struct.pack_into('<HBBIIHH',b,0,0x4a53,version,2,seq,stamp,1,4)
    struct.pack_into('<I',b,16,value);return bytes(b)

class Formats(unittest.TestCase):
    def test_microseconds_and_ticks_validate_the_same_period_and_values(self):
        for version,step in [(1,40),(2,960)]:
            raw=packet(version,1,0)+packet(version,2,step)
            reader,versions=validate_hss(raw,struct.pack('<I',0x68001234),960)
            self.assertEqual((reader.samples,reader.timeline_skips,versions),(2,0,[version]))
            self.assertEqual(raw[2],version,'Validator must not mutate evidence')
    def test_bad_values_and_sequence_gaps_still_fail(self):
        expected=struct.pack('<I',0x68001234)
        for raw in [packet(1,1,0,value=0),packet(1,1,0)+packet(1,3,40),packet(3,1,0)]:
            with self.assertRaises(AssertionError):validate_hss(raw,expected,960)

if __name__=='__main__':unittest.main()
