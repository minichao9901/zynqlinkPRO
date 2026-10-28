"""Derive the TCK rate the JTAG PHY actually used during a block burst.

The RTL counts TCK rising edges (CSR 0xC0). Reading it around a host-timed
burst gives the real scan rate, which the requested CMSIS-DAP clock does not
necessarily match, plus the number of TCK cycles spent per transferred word.
"""
import argparse
import time

from dap_pipeline_bench import open_dap, setup, send, xfer, read_exact, block_read_req


def tck_edges(out, inp):
    r = xfer(out, inp, [0x89, 255])
    return int.from_bytes(r[4:8], 'little') & 0xFFFFFFFF


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--transport', default='jtag')
    ap.add_argument('--speed', type=int, default=60000)
    ap.add_argument('--words', type=int, default=256)
    ap.add_argument('--loops', type=int, default=64)
    ap.add_argument('--depth', type=int, default=8)
    a = ap.parse_args()

    dev, out, inp = open_dap()
    setup(out, inp, a.speed, a.transport)
    clock, _ = (lambda r: (int.from_bytes(r[4:8], 'little'), 0))(xfer(out, inp, [0x80, 255]))

    # warm up so the measurement does not include first-packet effects
    for _ in range(a.depth):
        send(out, block_read_req(a.words))
    for _ in range(a.depth):
        read_exact(inp, 4 + a.words * 4)

    before = tck_edges(out, inp)
    t0 = time.perf_counter()
    done = 0
    while done < a.loops:
        n = min(a.depth, a.loops - done)
        for _ in range(n):
            send(out, block_read_req(a.words))
        for _ in range(n):
            if len(read_exact(inp, 4 + a.words * 4)) < 4 + a.words * 4:
                raise RuntimeError('short read')
        done += n
    elapsed = time.perf_counter() - t0
    after = tck_edges(out, inp)

    edges = (after - before) & 0xFFFFFFFF
    words = a.loops * a.words
    print('%s  requested %d kHz  FCLK %d Hz' % (a.transport, a.speed, clock))
    print('  %d TCK edges in %.4f s  -> actual TCK %.2f MHz'
          % (edges, elapsed, edges / elapsed / 1e6))
    print('  %.1f TCK cycles per word, %.3f MB/s'
          % (edges / words, words * 4 / elapsed / 1e6))


if __name__ == '__main__':
    main()
