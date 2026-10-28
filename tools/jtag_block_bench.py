"""Measure JTAG vs SWD MEM-AP block throughput on one board.

Reports sequential and pipelined block reads plus pipelined block writes, all
against the same auto-incrementing TAR, so the numbers are wire-bound rather
than USB round-trip bound (one request per 1 KiB chunk, no re-addressing).
"""
import argparse
import json
import time
from pathlib import Path

from dap_pipeline_bench import (open_dap, setup, send, xfer, read_exact,
                                block_read_req, cmd)


def bench_read_seq(out, inp, words, loops):
    t0 = time.perf_counter()
    for _ in range(loops):
        send(out, block_read_req(words))
        if len(read_exact(inp, 4 + words * 4)) < 4 + words * 4:
            raise RuntimeError('short read')
    return time.perf_counter() - t0, loops * words * 4


def bench_read_pipe(out, inp, words, loops, depth):
    t0 = time.perf_counter()
    done = 0
    while done < loops:
        n = min(depth, loops - done)
        for _ in range(n):
            send(out, block_read_req(words))
        for _ in range(n):
            if len(read_exact(inp, 4 + words * 4)) < 4 + words * 4:
                raise RuntimeError('short read')
        done += n
    return time.perf_counter() - t0, loops * words * 4


def write_req(words, payload):
    return [0x06, 0x00, words & 0xFF, (words >> 8) & 0xFF, 0x0D] + list(payload)


def bench_write_pipe(out, inp, words, loops, depth, payload):
    t0 = time.perf_counter()
    done = 0
    while done < loops:
        n = min(depth, loops - done)
        for _ in range(n):
            send(out, write_req(words, payload))
        for _ in range(n):
            r = xfer(out, inp, b'')
            if not r or r[0] != 0x06:
                raise RuntimeError('write reply %s' % r[:8].hex(' '))
        done += n
    return time.perf_counter() - t0, loops * words * 4


def read_clock(out, inp):
    """FCLK the firmware currently has programmed (vendor 0x80, query only)."""
    r = xfer(out, inp, [0x80, 255])
    return int.from_bytes(r[4:8], 'little'), int.from_bytes(r[8:12], 'little')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed', type=int, default=60000, help='kHz')
    ap.add_argument('--transport', default='jtag')
    ap.add_argument('--words', type=int, default=256, help='words per block')
    ap.add_argument('--loops', type=int, default=64)
    ap.add_argument('--depth', type=int, default=4)
    ap.add_argument('--idle', type=int, default=None, help='DAP idle cycles between scans')
    ap.add_argument('--timing', type=int, default=None,
                    help='pin the RTL TDO sampling mode instead of auto calibration')
    ap.add_argument('--output', type=Path)
    a = ap.parse_args()

    dev, out, inp = open_dap()
    rows = []
    try:
        setup(out, inp, a.speed, a.transport)
        if a.timing is not None:
            xfer(out, inp, [0x89, a.timing])
        if a.idle is not None:
            cmd(out, inp, [0x13, a.idle])
        fclk0, _ = read_clock(out, inp)
        payload = bytes((i * 7 + 3) & 0xFF for i in range(a.words * 4))
        for name, fn in (('read_seq', lambda: bench_read_seq(out, inp, a.words, a.loops)),
                         ('read_pipe', lambda: bench_read_pipe(out, inp, a.words, a.loops, a.depth)),
                         ('write_pipe', lambda: bench_write_pipe(out, inp, a.words, a.loops, a.depth, payload))):
            fn()
            dt, nbytes = fn()
            row = {'transport': a.transport, 'speed_khz': a.speed, 'mode': name,
                   'MB_s': round(nbytes / dt / 1e6, 3)}
            rows.append(row)
            print('%-6s %6d kHz  %-11s %7.3f MB/s' % (a.transport, a.speed, name, row['MB_s']), flush=True)
    finally:
        fclk1, _ = read_clock(out, inp)
        print('FCLK after setup = %d Hz (TCK %d), FCLK after bursts = %d Hz (TCK %d)'
              % (fclk0, fclk0 // 2, fclk1, fclk1 // 2))
        if a.output:
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(json.dumps(rows + [{'fclk_before': fclk0, 'fclk_after': fclk1}],
                                           indent=2))


if __name__ == '__main__':
    main()
