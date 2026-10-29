"""Measure actual PL scans/bits/cycles per SRAM word, with bounded buffers."""
import argparse
import json
from pathlib import Path
import random
import struct
import time

import usb.util

from benchmark_hpm5301 import BASE, SIZE, clock, recover_link, setup
from dap_pipeline_bench import open_dap, read_exact, send, xfer
from probe_build_info import provenance
from test_probe_board import Memory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--speed', type=int, default=24500000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    report = dict(artifacts=provenance(args.bit, args.elf), rows=[])
    saved = None
    def stats():
        return struct.unpack_from('<3I', xfer(out, inp, [0x89, 255]), 3)
    try:
        setup(out, inp, args.speed, connect=True)
        report.update(clock(out, inp))
        saved = mem.read(BASE, SIZE)
        data = random.Random(0x5301).randbytes(SIZE)
        mem.write(BASE, data)
        for direction in ('read', 'write'):
            mem.address(BASE)
            before = stats()
            start = time.perf_counter()
            for index in range(32):
                request = bytes([6, 0, 0, 2, 15 if direction == 'read' else 13])
                if direction == 'write':
                    request += data[2048 * index:2048 * (index + 1)]
                send(out, request)
            for index in range(32):
                reply = read_exact(inp, 2052 if direction == 'read' else 4)
                assert reply[:4] == bytes([6, 0, 2, 1]), reply[:16].hex()
                if direction == 'read':
                    assert reply[4:] == data[2048 * index:2048 * (index + 1)]
            elapsed = time.perf_counter() - start
            delta = [(b - a) & 0xFFFFFFFF for a, b in zip(before, stats())]
            words = SIZE // 4
            report['rows'].append(dict(direction=direction, words=words, MB_s=SIZE / elapsed / 1e6,
                elapsed_s=elapsed, phy_cycles=delta[0], scan_bits=delta[1], scans=delta[2],
                scans_per_word=delta[2] / words, bits_per_word=delta[1] / words,
                phy_cycles_per_word=delta[0] / words,
                phy_wait_fraction=delta[0] / report['FCLK_Hz'] / elapsed))
        assert mem.read(BASE, SIZE) == data
        print(json.dumps(report, indent=2), flush=True)
    finally:
        try:
            recover_link(dev, out, inp)
            if saved is not None:
                mem.write(BASE, saved)
                report['restore_match'] = mem.read(BASE, SIZE) == saved
                assert report['restore_match']
        finally:
            args.output.write_text(json.dumps(report, indent=2) + '\n')
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
