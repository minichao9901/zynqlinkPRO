import struct
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from openocd_native import WasmMemory


class SimulatedDap:
    """USB and ADIv5 model for the real Node/OpenOCD/PyUSB adapter path."""
    idVendor, idProduct, serial_number, product = 0x0d28, 0x0204, 'FAKE', 'CMSIS-DAP'

    def __init__(self):
        self.epoch = 4
        self.select = self.csw = self.tar = 0
        self.words = {0xe000ed00:0x411fc231,0x200003fc:0x12345678,0x20000400:0x9abcdef0}
        self.writes = []
        self.out = SimpleNamespace(bEndpointAddress=2,wMaxPacketSize=512,write=self.write)
        self.inp = SimpleNamespace(bEndpointAddress=0x81,read=self.read)

    def get_active_configuration(self):
        return SimpleNamespace(bConfigurationValue=1)

    def clear_halt(self, ep):
        assert ep in (2,0x81)

    def ctrl_transfer(self, kind, request, value, index, length, timeout):
        if kind == 0xc0:
            assert (value,index) == (0x4441,0x5052)
            if request == 0x5b:
                return struct.pack('<8I',0,0,0,self.epoch,0,0,0,0)
            assert request == 0x5a
            self.epoch += 1
            return b'DAP\0'
        assert (kind,request) == (0x80,6)
        descriptors = {
            0x100:bytes([18,1,16,2,0xef,2,1,64,40,13,4,2,0,1,0,2,3,1]),
            0x200:bytes([9,2,32,0,1,1,0,128,50,9,4,0,0,2,255,0,0,0,7,5,2,2,0,2,0,7,5,0x81,2,0,2,0]),
            0x300:bytes([4,3,9,4]),
        }
        text = (self.product if value == 0x302 else self.serial_number).encode('utf-16-le')
        return descriptors.get(value,bytes([len(text)+2,3])+text)[:length]

    def write(self, data, timeout):
        if data:
            self.command = bytes(data)
        return len(data)

    def read(self, size, timeout):
        command = self.command
        op, arg = command[0], command[1] if len(command)>1 else 0
        if op == 0:
            data = {0xf0:b'\x01',0xfe:b'\x01',0xff:b'\x40\x00'}.get(arg,b'')
            return bytes([0,len(data)])+data
        if op in (5,6):
            count = command[2] if op == 5 else int.from_bytes(command[2:4],'little')
            result = bytearray([op,count,1] if op == 5 else [op,count & 255,count >> 8,1])
            cursor = 3 if op == 5 else 5
            for _ in range(count):
                request = command[cursor] if op == 5 else command[4]
                if op == 5:
                    cursor += 1
                if request & 2:
                    result += struct.pack('<I',self.access(request,None))
                else:
                    self.access(request,struct.unpack_from('<I',command,cursor)[0])
                    cursor += 4
            return result
        if op == 0x1d:
            return bytes([op,0]) + b'\x00' * 12
        return bytes([op,1 if op == 2 else 0,0,0,0])

    def access(self, request, value):
        address = request & 12
        if not request & 1:
            if value is None:
                return {0:0x1ba01477,4:0xf0000000}.get(address,0)
            if address == 8:
                self.select = value
            return 0
        address += self.select & 0xf0
        if address == 0xfc:
            return 0x24770011
        if address == 0:
            if value is None:
                return self.csw
            self.csw = value
        if address == 4:
            if value is None:
                return self.tar
            self.tar = value
        if address == 12:
            at = self.tar
            if self.csw & 0x30 == 0x10:
                self.tar = (at & ~0x3ff) | ((at + 4) & 0x3ff)
            if value is None:
                return self.words.get(at,0)
            self.words[at] = value
            self.writes.append((at,value))
        return 0


class OpenOcdNativeTests(unittest.TestCase):
    def test_real_wasm_controls_target_and_preserves_capture_handle(self):
        device = SimulatedDap()
        memory = WasmMemory(device,device.out,device.inp,10000)
        self.addCleanup(memory.close)
        self.assertEqual(memory.open(),0x1ba01477)
        self.assertEqual(device.writes,[])  # MEM-AP0 does not examine Cortex-M.
        self.assertEqual(memory.word(0xe000ed00),0x411fc231)
        self.assertEqual(memory.read(0x200003fc,8),bytes.fromhex('78563412f0debc9a'))
        memory.write_word(0x20000400,0xdeadbeef)
        self.assertEqual(memory.word(0x20000400),0xdeadbeef)
        memory.close()
        self.assertEqual(device.writes,[(0x20000400,0xdeadbeef)])
        self.assertEqual(device.epoch,5)
        self.assertIsNone(memory.process)
