import sys
from pathlib import Path
import struct
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from probe_memory import transfer, MemoryTransferError


class Target:
    def __init__(self):
        self.ram=bytearray((i*13+7)&255 for i in range(4096));self.tar=0;self.calls=[];self.fail=False
    def __call__(self,p):
        self.calls.append(p)
        if self.fail:return b'\x06\x00\x00\x04'
        if p[0]==5:
            if p[2]==3:
                self.tar=struct.unpack_from('<I',p,14)[0]-0x20000000
                return b'\x05\x03\x01'
            return b'\x05\x01\x01'+bytes(4)
        n=struct.unpack_from('<H',p,2)[0]*4
        assert self.tar//1024==(self.tar+n-1)//1024
        result=struct.pack('<BHB',6,n//4,1)
        if p[4]==15:result+=self.ram[self.tar:self.tar+n]
        else:self.ram[self.tar:self.tar+n]=p[5:]
        return result


class MemoryTests(unittest.TestCase):
    def test_unaligned_cross_page_write_preserves_neighbors_and_reads_exactly(self):
        t=Target();before=bytes(t.ram);data=b'x'*2063
        transfer(t,address=0x200003fd,data=data)
        self.assertEqual(t.ram[:1021],before[:1021]);self.assertEqual(t.ram[3084:],before[3084:])
        self.assertEqual(transfer(t,address=0x200003fd,length=len(data)),data)

    def test_illegal_or_mmio_requests_have_no_wire_effect(self):
        for args in (dict(address=0x40000000,data=b'1234'),dict(address=0xe000edf0,length=4),
                     dict(address=0x20000000,length=262145),dict(address=0xfffffffc,length=8),
                     dict(address=0x20000000,length=4,csw=0)):
            t=Target()
            with self.assertRaises(ValueError):transfer(t,**args)
            self.assertEqual(t.calls,[])

    def test_fault_never_replays_write_and_cancel_stops_at_block_boundary(self):
        t=Target();t.fail=True
        with self.assertRaises(MemoryTransferError):transfer(t,address=0x20000000,data=bytes(2048))
        self.assertEqual(len(t.calls),1)
        t=Target();before=bytes(t.ram);counter=0
        def check():
            nonlocal counter
            counter+=1
            if counter==4:raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            transfer(t,address=0x20000000,data=bytes(2048),check=check)
        self.assertEqual(t.ram[:1024],bytes(1024));self.assertEqual(t.ram[1024:],before[1024:])
