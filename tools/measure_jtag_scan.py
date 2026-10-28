"""Recover the half-cycle delay the JTAG PHY actually used.

jtag_core accumulates PHY-wait FCLK cycles, scanned bits and completed scans
(CSR 0xC0..0xC8). For the shifter, cycles = 2*(half_delay+1)*bits, so the ratio
tells whether a 60 MHz request really scanned at 60 MHz (ratio ~1) or at half
that (ratio ~2).
"""
import argparse
import time

from dap_pipeline_bench import open_dap, setup, send, xfer, read_exact, block_read_req


def scan_stats(out, inp):
    # response: [0]=cmd, [1]=status, [2]=timing, then three little-endian u32.
    r = xfer(out, inp, [0x89, 255])
    return (int.from_bytes(r[3:7], 'little'),
            int.from_bytes(r[7:11], 'little'),
            int.from_bytes(r[11:15], 'little'), r[2])


def report(name, a, b, elapsed, words):
    cycles = (b[0] - a[0]) & 0xFFFFFFFF
    bits = (b[1] - a[1]) & 0xFFFFFFFF
    scans = (b[2] - a[2]) & 0xFFFFFFFF
    print('%s: scans=%d bits=%d cycles=%d' % (name, scans, bits, cycles))
    if bits:
        ratio = cycles / (2.0 * bits)
        half = ratio - 1.0
        print('  cycles/(2*bits) = %.3f  -> half_delay ~ %.2f  (1 => TCK=FCLK/2, 2 => TCK=FCLK/4)'
              % (ratio, half))
        print('  %.1f TCK per word, %.1f bits/scan'
              % (scans / float(words) * (1.0 if bits else 0), bits / float(scans)))
    if elapsed:
        print('  effective TCK ~ %.2f MHz (bits/elapsed)' % (bits / elapsed / 1e6))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed', type=int, default=60000)
    ap.add_argument('--words', type=int, default=256)
    ap.add_argument('--loops', type=int, default=64)
    ap.add_argument('--depth', type=int, default=8)
    a = ap.parse_args()

    dev, out, inp = open_dap()
    setup(out, inp, a.speed, 'jtag')
    clock = int.from_bytes(xfer(out, inp, [0x80, 255])[4:8], 'little')
    print('requested %d kHz, FCLK %d Hz (TCK nominal %d)' % (a.speed, clock, clock // 2))

    # Baseline: 1000 IDCODE scans through the same core, no block engine.
    s0 = scan_stats(out, inp)
    for _ in range(1000):
        xfer(out, inp, [0x16, 0])
    s1 = scan_stats(out, inp)
    report('IDCODE x1000', s0, s1, 0.0, 1000)

    # Block burst.
    for _ in range(a.depth):
        send(out, block_read_req(a.words))
    for _ in range(a.depth):
        read_exact(inp, 4 + a.words * 4)
    s2 = scan_stats(out, inp)
    t0 = time.perf_counter()
    done = 0
    while done < a.loops:
        n = min(a.depth, a.loops - done)
        for _ in range(n):
            send(out, block_read_req(a.words))
        for _ in range(n):
            read_exact(inp, 4 + a.words * 4)
        done += n
    elapsed = time.perf_counter() - t0
    s3 = scan_stats(out, inp)
    report('block read', s2, s3, elapsed, a.loops * a.words)


if __name__ == '__main__':
    main()
