"""Verify the descriptor-driven Cortex-M3 producer with Unicorn (optional fixture test)."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_PC

BASE = 0x20008000


def check(code, ring_size):
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(BASE, 16384)
    cpu.mem_write(BASE, b"\xa5"*16384)
    cpu.mem_write(BASE, code)
    ring = BASE + (0x400 if ring_size == 1024 else 0x1000)
    descriptor = BASE + 0x200
    cpu.mem_write(descriptor, struct.pack("<16sII6II", b"SEGGER RTT", 1, 0, 0, ring, ring_size, 0, 0, 0, 0))
    pc = BASE
    received = bytearray()
    rd = 0
    for i in range(80):
        cpu.emu_start(pc | 1, BASE + len(code), count=40000)
        pc = cpu.reg_read(UC_ARM_REG_PC)
        wr = struct.unpack("<I", cpu.mem_read(descriptor+36, 4))[0]
        produced = struct.unpack("<I", cpu.mem_read(descriptor+48, 4))[0]
        available = (wr-rd) % ring_size
        assert produced*4 == len(received)+available and wr % 4 == 0
        assert ring_size-4 <= available < ring_size, "producer should stall before overwriting the reader"
        take = min(available, (511, 997, 1453)[i%3])
        a = min(ring_size-rd, take)
        received.extend(cpu.mem_read(ring+rd, a))
        if take > a:
            received.extend(cpu.mem_read(ring, take-a))
        rd = (rd+take) % ring_size
        cpu.mem_write(descriptor+40, struct.pack("<I", rd))
    n = (len(received)+3)//4
    assert received == struct.pack(f"<{n}I", *range(n))[:len(received)]
    assert cpu.mem_read(ring-4, 4) == cpu.mem_read(ring+ring_size, 4) == b"\xa5"*4
    assert cpu.mem_read(BASE, len(code)) == code
    return dict(ring_size=ring_size, verified_bytes=len(received), complete_wraps=len(received)//ring_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    code = parser.parse_args().binary.read_bytes()
    if not code.endswith(b"RTTD"):
        parser.error("expected a producer built with RTT_FROM_DESCRIPTOR")
    print(json.dumps(dict(producer_sha256=hashlib.sha256(code).hexdigest(),
                          windows=[check(code, n) for n in (1024, 8192)]), indent=2))
