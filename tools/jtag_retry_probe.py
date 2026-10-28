"""Hold a JTAG block-read burst at a forced clock and sampling mode.

Calibration may step the clock down when the capture window is marginal. For
hardware timing work we instead re-apply the requested clock after setup and
pin a known-good sampling mode, so no later transfer re-calibrates.
"""
import argparse
import time

from dap_pipeline_bench import open_dap, setup, cmd, le, send, xfer, read_exact, block_read_req


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed', type=int, default=60000)
    ap.add_argument('--mode', type=int, default=17)
    ap.add_argument('--words', type=int, default=256)
    ap.add_argument('--depth', type=int, default=8)
    ap.add_argument('--seconds', type=float, default=30.0)
    a = ap.parse_args()

    dev, out, inp = open_dap()
    setup(out, inp, a.speed, 'jtag')
    cmd(out, inp, [0x11] + le(a.speed * 1000))       # re-apply the clock
    xfer(out, inp, [0x12, 63] + [0xFF] * 8)          # TAP reset after the clock change
    xfer(out, inp, [0x89, a.mode])                   # pin the phase, skip calibration
    fclk = int.from_bytes(xfer(out, inp, [0x80, 255])[4:8], 'little')
    stats = xfer(out, inp, [0x89, 255])
    print('forced FCLK %d Hz (TCK %d), timing=%02x' % (fclk, fclk // 2, stats[2]), flush=True)
    print('idcode=%s' % cmd(out, inp, [0x16, 0])[2:6].hex(' '), flush=True)

    deadline = time.time() + a.seconds
    words = 0
    while time.time() < deadline:
        for _ in range(a.depth):
            send(out, block_read_req(a.words))
        for _ in range(a.depth):
            if len(read_exact(inp, 4 + a.words * 4)) < 4 + a.words * 4:
                raise SystemExit('short read')
        words += a.depth * a.words
    print('burst done, %d words' % words, flush=True)


if __name__ == '__main__':
    main()
