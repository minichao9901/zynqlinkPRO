"""H743 peak CMSIS-DAP throughput for one (transport, speed, block size, depth).

The AP TAR auto-increments and wraps at each 1 KiB boundary, so a block of N
words always reads the same 1 KiB pattern repeated; both directions are byte
verified against that expectation.
"""
import argparse
import json
import random
import struct
import time
from pathlib import Path

import usb.util

from dap_pipeline_bench import open_dap, setup, send, xfer, le, read_exact
from test_probe_board import Memory
from test_swd_lowfreq_board import recover
from probe_build_info import swd_clock_details


def ap_select(out, inp, addr):
    packet = [5, 0, 3, 8] + le(0) + [1] + le(0x23000052) + [5] + le(addr)
    reply = xfer(out, inp, packet)
    assert reply == b'\x05\x03\x01', reply.hex()


def expected(pattern, nbytes):
    return (pattern * (nbytes // len(pattern) + 1))[:nbytes]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed', type=int, default=60000)
    ap.add_argument('--transport', choices=['swd', 'jtag'], default='swd')
    ap.add_argument('--words', type=int, default=1024)
    ap.add_argument('--depth', type=int, default=8)
    ap.add_argument('--loops', type=int, default=256, help='blocks per direction')
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--no-halt', action='store_true', help='leave the core running')
    ap.add_argument('--address', default='0x24040000')
    ap.add_argument('--jtag-ir', default='4')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    base = int(args.address, 0)
    assert args.words % 256 == 0, 'keep TAR wrap aligned to 1 KiB'
    nbytes = args.words * 4
    pattern = random.Random(0x743).randbytes(1024)
    expect = expected(pattern, nbytes)
    jtag_ir = tuple(int(v) for v in args.jtag_ir.split(','))
    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    row = dict(transport=args.transport, requested_kHz=args.speed, words=args.words,
               depth=args.depth, loops=args.loops)
    saved = None
    initial = None
    try:
        setup(out, inp, 50000)
        initial = mem.word(0xE000EDF0)
        if not args.no_halt and not initial & (1 << 17):
            mem.write_word(0xE000EDF0, 0xA05F0003)
        row['target_halted'] = bool(mem.word(0xE000EDF0) & (1 << 17))
        saved = mem.read(base, 4096)
        setup(out, inp, args.speed, transport=args.transport, jtag_ir_lengths=jtag_ir)
        diag = xfer(out, inp, [0x80, 255])
        hz, cfg = struct.unpack_from('<II', diag, 4)
        row.update(FCLK_Hz=hz, cfg=hex(cfg), **swd_clock_details(hz, cfg))
        if args.transport == 'jtag':
            row['JTAG_sampling_mode'] = xfer(out, inp, [0x89, 255])[2]
        window = pattern * 4
        mem.write(base, window)
        assert mem.read(base, len(window)) == window, 'preload mismatch'
        row['restore_ok'] = True

        def run(mode):
            ap_select(out, inp, base)
            if mode == 'read':
                request = bytes([6, 0, args.words & 255, args.words >> 8, 0x0F])
            else:
                request = bytes([6, 0, args.words & 255, args.words >> 8, 0x0D]) + expect
            done = 0
            t0 = time.perf_counter()
            while done < args.loops:
                n = min(args.depth, args.loops - done)
                for _ in range(n):
                    send(out, request)
                for _ in range(n):
                    reply = read_exact(inp, 4 + (nbytes if mode == 'read' else 0))
                    assert reply[:4] == bytes([6, args.words & 255, args.words >> 8, 1]), reply[:16].hex()
                    if mode == 'read':
                        assert reply[4:] == expect, 'read data mismatch'
                    else:
                        assert len(reply) == 4, reply.hex()
                done += n
            dt = time.perf_counter() - t0
            return dt, args.loops * nbytes / dt / 1e6

        for mode in ('read', 'write'):
            run(mode)  # warm up
            samples = []
            for _ in range(args.repeats):
                dt, rate = run(mode)
                samples.append(dict(MB_s=rate, seconds=dt))
            rates = sorted(x['MB_s'] for x in samples)
            row[mode] = dict(MB_s=rates[len(rates) // 2], samples=samples,
                             blocks=args.loops, bytes=args.loops * nbytes)
            if mode == 'write':
                assert mem.read(base, len(window)) == window, 'write readback mismatch'
        row['passed'] = True
    except Exception as exc:
        row['error'] = repr(exc)
    finally:
        try:
            recover(dev, inp)
            setup(out, inp, 50000)
            if saved is not None:
                mem.write(base, saved)
                row.setdefault('restore_match', mem.read(base, len(saved)) == saved)
            if initial is not None and not args.no_halt and not initial & (1 << 17):
                mem.write_word(0xE000EDF0, 0xA05F0001)
        except Exception as exc:
            row['recover_error'] = repr(exc)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(row, indent=2))
        print(json.dumps(row), flush=True)
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
