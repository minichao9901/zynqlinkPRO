"""Sanity-check the RTL TCK edge counter against a known number of IDCODE scans."""
import time

from dap_pipeline_bench import open_dap, setup, cmd, xfer


def edges(out, inp):
    r = xfer(out, inp, [0x89, 255])
    return int.from_bytes(r[4:8], 'little')


def main():
    dev, out, inp = open_dap()
    setup(out, inp, 60000, 'jtag')
    e0 = edges(out, inp)
    for _ in range(1000):
        cmd(out, inp, [0x16, 0])
    e1 = edges(out, inp)
    time.sleep(0.2)
    for _ in range(1000):
        cmd(out, inp, [0x16, 0])
    e2 = edges(out, inp)
    print('first batch edges = %d' % ((e1 - e0) & 0xFFFFFFFF))
    print('second batch edges = %d' % ((e2 - e1) & 0xFFFFFFFF))
    print('TCK cycles per IDCODE scan = %.1f' % (((e2 - e1) & 0xFFFFFFFF) / 1000.0))


if __name__ == '__main__':
    main()
