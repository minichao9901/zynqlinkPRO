"""Exercise random and unaligned transfers against a real 1 KiB wrap model."""
from pathlib import Path
import random
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_probe_board import Memory


class WrappedMemory(Memory):
    def __init__(self):
        self.data = bytearray(random.Random(743).randbytes(8192))
        self.tar = 0

    def transfer(self, packet):
        packet = bytes(packet)
        if packet[0] == 5:
            self.tar = struct.unpack_from('<I', packet, 14)[0]
            return b'\x05\x03\x01'
        count = int.from_bytes(packet[2:4], 'little')
        payload = bytearray()
        for n in range(count):
            if packet[4] == 15:
                payload += self.data[self.tar:self.tar+4]
            else:
                self.data[self.tar:self.tar+4] = packet[5+4*n:9+4*n]
            self.tar = (self.tar & ~1023) | ((self.tar+4) & 1023)
        return bytes([6, count & 255, count >> 8, 1])+payload


class MemoryWrapTests(unittest.TestCase):
    def test_multiboundary_backup_write_and_restore(self):
        m = WrappedMemory()
        original = bytes(m.data)
        for address, size in [(0, 4096), (1019, 4101), (17, 6000)]:
            before = m.read(address, size)
            self.assertEqual(before, original[address:address+size])
            pattern = random.Random(size).randbytes(size)
            m.write(address, pattern)
            self.assertEqual(m.read(address,size),pattern)
            self.assertEqual(m.data[address:address+size],pattern)
            m.write(address,before)
            self.assertEqual(bytes(m.data),original)


if __name__ == '__main__':
    unittest.main()
