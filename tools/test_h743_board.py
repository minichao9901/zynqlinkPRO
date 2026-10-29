"""STM32H743 SWD/JTAG acceptance and throughput with verified SRAM windows.

Adapted from tools/test_swd_lowfreq_board.py: the target-specific parts
(F103 SRAM/RCC addresses, single-TAP JTAG) are parameters here instead of
constants.  Every rate point writes a random window, reads it back, then
restores the original bytes; failed points are recovered at 50 MHz so one bad
rate cannot poison the rest of the sweep.
"""
import argparse
import hashlib
import json
import random
import struct
import time
from pathlib import Path

import usb.util

from dap_pipeline_bench import open_dap, setup, send, xfer, block_read_req, le
from test_probe_board import Memory
from test_swd_lowfreq_board import recover
from probe_build_info import provenance, swd_clock_details

H743_DPIDR = 0x6BA02477


def ap_select(out, inp, addr):
    """APSEL=0, 32-bit auto-increment CSW, then TAR -- one DAP_Transfer."""
    packet = [5, 0, 3, 8] + le(0) + [1] + le(0x23000052) + [5] + le(addr)
    reply = xfer(out, inp, packet)
    assert reply == b'\x05\x03\x01', reply.hex()


def diagnostic(out, inp):
    diag = xfer(out, inp, [0x80, 255])
    if len(diag) < 12:
        return {}
    hz, cfg = struct.unpack_from('<II', diag, 4)
    return dict(diagnostic=diag.hex(), FCLK_Hz=hz, cfg=hex(cfg),
                phase=(cfg >> 17) & 1, rx_boundary=(cfg >> 18) & 1,
                **swd_clock_details(hz, cfg))


def measure(out, inp, addr, words, mode, loops, depth, pattern):
    """Pipelined block traffic; returns (seconds, MB/s, validated bytes)."""
    count = words
    if mode == 'read':
        request = block_read_req(count)
    else:
        request = bytes([6, 0, count & 255, count >> 8, 13]) + pattern[:count * 4]
    ap_select(out, inp, addr)
    t0 = time.perf_counter()
    done = 0
    while done < loops:
        n = min(depth, loops - done)
        for _ in range(n):
            send(out, request)
        for _ in range(n):
            reply = bytes(inp.read(4096, timeout=5000))
            assert reply[:4] == bytes([6, count & 255, count >> 8, 1]), reply[:16].hex()
            if mode == 'read':
                assert reply[4:] == pattern[:count * 4], 'read data mismatch'
            else:
                assert len(reply) == 4, reply.hex()
        done += n
    dt = time.perf_counter() - t0
    nbytes = loops * count * 4
    return dt, nbytes / dt / 1e6, nbytes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speeds', default='250,500,1000,2000,5000,10000,15000,20000,'
                                        '25000,30000,35000,40000,45000,50000,55000,60000')
    ap.add_argument('--bench-speeds', default='10000,30000,50000,60000')
    ap.add_argument('--transport', choices=['swd', 'jtag', 'both'], default='both')
    ap.add_argument('--address', default='0x24040000')
    ap.add_argument('--window', type=int, default=4096)
    ap.add_argument('--loops', type=int, default=3, help='functional rounds per rate')
    ap.add_argument('--bench-loops', type=int, default=4096, help='1KiB blocks per rate')
    ap.add_argument('--depth', type=int, default=4)
    ap.add_argument('--jtag-ir', default='4', help='comma-separated IR lengths of the JTAG chain')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--bit', type=Path)
    ap.add_argument('--elf', type=Path)
    args = ap.parse_args()
    assert 0 < args.window <= 4096 and args.window % 4 == 0
    base = int(args.address, 0)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    backup = initial = None
    report = dict(artifacts=provenance(args.bit, args.elf), address=hex(base),
                  window=args.window, depth=args.depth, rows=[])
    transports = ['swd', 'jtag'] if args.transport == 'both' else [args.transport]
    try:
        setup(out, inp, 50000)
        initial = mem.word(0xe000edf0)
        if not initial & (1 << 17):
            mem.write_word(0xe000edf0, 0xa05f0003)
        report['CPUID'] = hex(mem.word(0xe000ed00))
        report['DPIDR'] = hex(mem.word(0xe000ed00))
        backup = mem.read(base, args.window)
        args.output.with_suffix('.backup.bin').write_bytes(backup)
        report['backup_sha256'] = hashlib.sha256(backup).hexdigest()

        for transport in transports:
            jtag_ir = tuple(int(v) for v in args.jtag_ir.split(','))
            for khz in [int(x) for x in args.speeds.split(',')]:
                row = dict(transport=transport, requested_kHz=khz, passed=False)
                try:
                    reply = setup(out, inp, khz, transport=transport,
                                  jtag_ir_lengths=jtag_ir)
                    row['idcode_reply'] = reply.hex()
                    row['IDCODE'] = reply[2:6].hex() if transport == 'jtag' else reply[3:7].hex()
                    row.update(diagnostic(out, inp))
                    row['actual_link_Hz'] = row.get('SWCLK_Hz')
                    if transport == 'jtag':
                        row['JTAG_sampling_mode'] = xfer(out, inp, [0x89, 255])[2]
                    t = time.perf_counter()
                    for i in range(args.loops):
                        pattern = random.Random(0x20261029 + khz * 31 + i).randbytes(args.window)
                        mem.write(base, pattern)
                        assert mem.read(base, args.window) == pattern, 'SRAM byte mismatch'
                    row.update(passed=True, bytes_each_direction=args.loops * args.window,
                               roundtrip_seconds=time.perf_counter() - t)
                except Exception as exc:
                    row['error'] = repr(exc)
                finally:
                    try:
                        recover(dev, inp)
                        setup(out, inp, 50000, transport=transport, jtag_ir_lengths=jtag_ir)
                        mem.write(base, backup)
                        row['restore_match'] = mem.read(base, args.window) == backup
                    except Exception as exc:
                        row['recover_error'] = repr(exc)
                    report['rows'].append(row)
                    args.output.write_text(json.dumps(report, indent=2))
                    print(json.dumps(row), flush=True)

        # Throughput at the requested high-rate points, verified end to end.
        for transport in transports:
            jtag_ir = tuple(int(v) for v in args.jtag_ir.split(','))
            for khz in [int(x) for x in args.bench_speeds.split(',')]:
                row = dict(transport=transport, requested_kHz=khz, kind='throughput')
                try:
                    setup(out, inp, khz, transport=transport, jtag_ir_lengths=jtag_ir)
                    row.update(diagnostic(out, inp))
                    words = 256
                    pattern = random.Random(0x743).randbytes(words * 4)
                    # The read bench re-reads the first 1KiB block after each
                    # 1KiB wrap, so seed the whole window with that pattern.
                    mem.write(base, pattern * (args.window // (words * 4)))
                    assert mem.read(base, args.window) == pattern * (args.window // (words * 4))
                    for mode in ('read', 'write'):
                        measure(out, inp, base, words, mode, 8, args.depth, pattern)  # warm up
                        dt, rate, nbytes = measure(out, inp, base, words, mode,
                                                   args.bench_loops, args.depth, pattern)
                        row[mode] = dict(MB_s=rate, blocks=args.bench_loops,
                                         bytes=nbytes, seconds=dt)
                    mem.write(base, pattern * (args.window // (words * 4)))
                    assert mem.read(base, args.window) == pattern * (args.window // (words * 4))
                    row['passed'] = True
                except Exception as exc:
                    row['error'] = repr(exc)
                finally:
                    try:
                        recover(dev, inp)
                        setup(out, inp, 50000, transport=transport, jtag_ir_lengths=jtag_ir)
                        mem.write(base, backup)
                        row['restore_match'] = mem.read(base, args.window) == backup
                    except Exception as exc:
                        row['recover_error'] = repr(exc)
                    report['rows'].append(row)
                    args.output.write_text(json.dumps(report, indent=2))
                    print(json.dumps(row), flush=True)
    except BaseException as exc:
        report['fatal_error'] = repr(exc)
        raise
    finally:
        try:
            recover(dev, inp)
            setup(out, inp, 50000)
            if backup is not None:
                mem.write(base, backup)
                report['restore_match'] = mem.read(base, args.window) == backup
                assert report['restore_match']
            if initial is not None and not initial & (1 << 17):
                mem.write_word(0xe000edf0, 0xa05f0001)
        finally:
            args.output.write_text(json.dumps(report, indent=2))
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
