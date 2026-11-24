"""Verify HPM6880 SRAM traffic through J7's standard DAP DMI/SBA backend."""
import hashlib
import json
import struct
import time

import usb.util

from benchmark_hpm5301 import clock, setup
from dap_pipeline_bench import cmd, drain, open_dap
from fusion_evidence import Blocked
from fusion_fixture import read_bytes, target_io
from validate_hpm6800_performance import SramMemory


def run_hpm_sram(case, image, serial, args, out):
    p = case['parameters']
    size = p['payloadBytes']
    with target_io(case['board'], serial) as io:
        if image.word(io, 'g_mode'):
            raise RuntimeError('Prepare an idle HPM fixture')
        base = (image.word(io, 'g_perf_sram_address') if 'g_perf_sram_address' in image.symbols
                else image.address('g_perf_sram')+32)
        extent = image.word(io, 'g_perf_sram_bytes')
        start = base - 32
        address = ((base + 4 + 1023) & ~1023) + p['offsetFromAlignedPage']
        if address + size + 4 > base + extent:
            raise RuntimeError('Transfer exceeds the fixture scratch space')
        original = read_bytes(io, start, extent+64)
        if read_bytes(io, start, extent+64) != original:
            raise RuntimeError('Unstable HPM scratch backup')
        (out / 'scratch-before.bin').write_bytes(original)
    rows = []
    dirty = False
    try:
        dev, tx, rx = open_dap(serial)
        try:
            drain(rx)
            setup(tx, rx, args.rate, connect=True)
            details = clock(tx, rx)
            (out / 'clock.json').write_text(json.dumps(details, indent=2), encoding='utf8')
            if abs(details['actual_TCK_Hz'] - args.rate) > 1:
                raise Blocked(f'TCK {details["actual_TCK_Hz"]} differs from requested {args.rate} Hz')
            mem = SramMemory(tx, rx)
            for number in range(1, p['rounds'] + 1):
                for direction in p['directions']:
                    expected = hashlib.shake_256(f'{number}-{direction}'.encode()).digest(size)
                    dirty = True
                    mem.write(address, expected)
                    if mem.read(address, size) != expected:
                        raise RuntimeError('DAP SRAM prefill differs')
                    begin = time.perf_counter()
                    nread = nwritten = seq = 0
                    while time.perf_counter()-begin < p['seconds']:
                        if direction != 'read':
                            seq += 1
                            expected = hashlib.shake_256(struct.pack('<II', number, seq)).digest(size)
                            mem.write(address, expected)
                            nwritten += size
                        if direction != 'write':
                            if mem.read(address, size) != expected:
                                raise RuntimeError(f'SRAM data differs at read byte {nread}')
                            nread += size
                    elapsed = time.perf_counter()-begin
                    if mem.read(address, size) != expected:
                        raise RuntimeError('DAP SRAM final payload differs')
                    row = {'round': number, 'direction': direction, 'read_bytes': nread, 'write_bytes': nwritten,
                           'seconds': elapsed, 'MBps': (nread+nwritten)/elapsed/1e6, 'path': 'standard DAP DMI/SBA'}
                    rows.append(row)
                    with (out / 'sram-windows.jsonl').open('a', encoding='utf8') as log:
                        log.write(json.dumps(row) + '\n')
        finally:
            try:
                if cmd(tx, rx, [3]) != b'\x03\x00':
                    raise RuntimeError('DAP disconnect failed')
            finally:
                usb.util.dispose_resources(dev)
    finally:
        if dirty:
            with target_io(case['board'], serial) as io:
                current = read_bytes(io, start, extent+64)
                offset = address-start
                guards = current[:offset] == original[:offset] and current[offset+size:] == original[offset+size:]
                io.write(start, original)
                restored = read_bytes(io, start, extent+64) == original
                (out / 'sram-restoration.json').write_text(json.dumps({'scratch_restored':restored, 'guards':guards}),
                                                          encoding='utf8')
                if not restored or not guards:
                    raise RuntimeError('HPM SRAM contents or guards differ after restoration')
    return {'windows': rows, 'remaining': ['Add RISC-V subword operations and separately qualify the depth-4 fast path.']}
