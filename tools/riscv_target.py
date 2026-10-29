"""Raw RISC-V DMI control and target bootstrap through CMSIS-DAP sequences."""
import time
import struct

from read_riscv_dtm import sequence


class RiscvTarget:
    def __init__(self, out, inp):
        self.out, self.inp = out, inp
        sequence(out, inp, [(6, 1, 0, False), (16, 0, 0, False)])
        self.ir = None

    def select(self, ir):
        # Explicit selection also works after the PL memory engine used DMI.
        sequence(self.out, self.inp, [(2, 1, 0, False), (2, 0, 0, False),
                 (4, 0, ir & 15, False), (1, 1, ir >> 4, False),
                 (1, 1, 0, False), (1, 0, 0, False)])
        self.ir = ir

    def scan(self, value, width):
        r = sequence(self.out, self.inp, [(1, 1, 0, False), (2, 0, 0, False),
                     (width - 1, 0, value & ((1 << (width - 1)) - 1), True),
                     (1, 1, value >> (width - 1), True),
                     (1, 1, 0, False), (16, 0, 0, False)])
        return r[0] | (r[1] << (width - 1))

    def dmi(self, address, value=None):
        self.select(17)
        self.scan((address << 34) | ((0 if value is None else value) << 2)
                  | (1 if value is None else 2), 41)
        result = self.scan(0, 41)
        if result & 3:
            raise RuntimeError(f'DMI addr={address:#x} status={result & 3}, response={result:#x}')
        return (result >> 2) & 0xFFFFFFFF

    def active(self):
        self.dmi(0x10, 1)
        return self.dmi(0x11)

    def halt(self):
        self.dmi(0x10, 0x80000001)
        for _ in range(100):
            if self.dmi(0x11) & (1 << 9):
                self.dmi(0x10, 1)
                return
        raise RuntimeError('RISC-V halt timeout')

    def resume(self):
        self.dmi(0x10, 0x40000001)
        for _ in range(100):
            status = self.dmi(0x11)
            if status & (1 << 17) or (status & (1 << 10) and not status & (1 << 9)):
                self.dmi(0x10, 1)
                return
        raise RuntimeError('RISC-V resume timeout')

    def register(self, regno, value=None):
        self.dmi(0x16, 0x700)  # W1C abstract command error.
        if value is not None:
            self.dmi(4, value)
        self.dmi(0x17, 0x220000 | (0x10000 if value is not None else 0) | regno)
        for _ in range(100):
            status = self.dmi(0x16)
            if not status & (1 << 12):
                if status & 0x700:
                    raise RuntimeError(f'Abstract register {regno:#x}: {status:#x}')
                return self.dmi(4) if value is None else value
        raise RuntimeError('Abstract command timeout')

    def word(self, addr, value=None):
        self.dmi(0x38, 0x440000 | 0x7000)  # Access32, clear sticky errors.
        self.dmi(0x38, 0x140000 if value is None else 0x40000)
        self.dmi(0x39, addr)
        if value is not None:
            self.dmi(0x3C, value)
        for _ in range(100):
            status = self.dmi(0x38)
            if status & 0x407000:
                raise RuntimeError(f'SBA address {addr:#x}: {status:#x}')
            if not status & (1 << 21):
                return self.dmi(0x3C) if value is None else value
        raise RuntimeError('SBA timeout')

    def read(self, addr, size):
        assert addr % 4 == 0 and size % 4 == 0
        result = bytearray()
        for offset in range(0, size, 128):
            count = min(128, size - offset) // 4
            self.dmi(0x38, 0x407000 | 0x40000)
            self.dmi(0x38, 0x158000)
            self.dmi(0x39, addr + offset)
            for _ in range(count):
                result += struct.pack('<I', self.dmi(0x3C))
            status = self.dmi(0x38)
            if status & 0x607000:
                raise RuntimeError(f'SBA block read {addr + offset:#x}: {status:#x}')
        self.dmi(0x38, 0x40000)
        return bytes(result)

    def write(self, addr, data):
        assert addr % 4 == 0 and len(data) % 4 == 0
        self.dmi(0x38, 0x407000 | 0x40000)
        self.dmi(0x38, 0x50000)
        self.dmi(0x39, addr)
        for offset in range(0, len(data), 128):
            words = struct.unpack('<' + 'I' * (min(128, len(data) - offset) // 4), data[offset:offset + 128])
            for word in words:
                self.dmi(0x3C, word)
            status = self.dmi(0x38)
            if status & 0x607000:
                raise RuntimeError(f'SBA block write {addr + offset:#x}: {status:#x}')
