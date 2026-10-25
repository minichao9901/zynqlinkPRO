"""Sweep SWCLK frequency + sampling phase and measure pipelined block throughput.

The link is trained at 50 MHz first (H743 DP does not answer the first frames
at high clock).  For every frequency the script re-runs the SWD line reset,
powers up the DP, verifies a block read, then measures pipelined 1023-word
block reads with full response validation.
"""
import argparse
import json
import time

import libusb_package
import usb.core
import usb.util

PKT = 4096
SEQ = [0xFF] * 8 + [0x9E, 0xE7] + [0xFF] * 8 + [0x00]  # 152-bit line reset + JTAG-to-SWD


def le(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--freqs', default='60000,66000,69000,70000,75000,80000')
    ap.add_argument('--address', default='0x24010000')
    ap.add_argument('--words', type=int, default=1023)
    ap.add_argument('--depth', type=int, default=8)
    ap.add_argument('--rounds', type=int, default=4)
    ap.add_argument('--idcode', default='0x6BA02477')
    ap.add_argument('--output', default='results/optimization/swclk_sweep.json')
    args = ap.parse_args()
    addr = int(args.address, 0)
    idcode = int(args.idcode, 0)
    words = args.words

    dev = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                        backend=libusb_package.get_libusb1_backend())
    if dev is None:
        raise RuntimeError('DAP not found')
    intf = dev.get_active_configuration()[(0, 0)]
    usb.util.claim_interface(dev, 0)
    out = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
    inp = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)

    def send(payload):
        b = bytes(payload)
        out.write(b, timeout=4000)
        if len(b) % 512 == 0:
            out.write(b'', timeout=4000)

    def recv(timeout=6000):
        return bytes(inp.read(PKT, timeout=timeout))

    def xfer(payload):
        send(payload)
        return recv()

    while True:
        try:
            inp.read(PKT, timeout=60)
        except usb.core.USBTimeoutError:
            break

    def set_clock(khz):
        xfer([0x11] + le(khz * 1000))

    def activate():
        xfer([0x12, 152] + SEQ)

    def query():
        r = xfer([0x80, 0xFF])
        return int.from_bytes(bytes(r[4:8]), 'little') if len(r) >= 12 else None

    def set_phase(phase):
        r = xfer([0x80, phase])
        return len(r) >= 2 and r[1] == 0

    def read_dp(req):
        r = xfer([0x05, 0x00, 0x01, req])
        return r[3:7] if len(r) >= 7 and r[2] == 0x01 else None

    def dp_power_up():
        xfer([0x05, 0x00, 0x01, 0x00] + le(0x1E))       # clear sticky errors
        xfer([0x05, 0x00, 0x01, 0x04] + le(0x50000000))  # request debug + system power
        for _ in range(20):
            val = read_dp(0x06)                          # read CTRL/STAT
            if val and (int.from_bytes(val, 'little') & 0xA0000000) == 0xA0000000:
                break
            time.sleep(0.002)
        xfer([0x05, 0x00, 0x01, 0x08] + le(0))           # APSEL = 0
        xfer([0x05, 0x00, 0x01, 0x01] + le(0x23000052))  # CSW: 32-bit, addr increment
        xfer([0x05, 0x00, 0x01, 0x05] + le(addr))        # TAR

    def probe():
        r = xfer([0x05, 0x00, 0x01, 0x02])
        if len(r) < 7 or r[2] != 0x01 or r[3:7] != bytes(le(idcode)):
            return False
        dp_power_up()
        r = xfer([0x06, 0x00, 0x04, 0x00, 0x0F])
        return len(r) >= 4 + 16 and r[3] == 0x01

    # Train at 50 MHz.
    xfer([0x02, 0x01])
    xfer([0x13, 0x00])
    xfer([0x04, 0x00, 0x40, 0x00, 0x00, 0x00])
    set_clock(50000)
    activate()
    if not probe():
        raise RuntimeError('link training at 50 MHz failed')

    rows = []
    for khz in [int(x) for x in args.freqs.split(',')]:
        set_clock(khz)
        hz = query()
        row = {'request_khz': khz, 'reported_hz': hz, 'phases': {}}
        for phase in (0, 1):
            if not set_phase(phase):
                row['phases'][str(phase)] = {'ok': False, 'reason': 'phase rejected'}
                continue
            activate()
            if not probe():
                row['phases'][str(phase)] = {'ok': False, 'reason': 'block read failed'}
                continue
            nbytes = 0
            bad = 0
            t0 = time.perf_counter()
            for _ in range(args.rounds):
                for _ in range(args.depth):
                    send([0x06, 0x00, 0xFF, 0x03, 0x0F])
                for _ in range(args.depth):
                    r = recv()
                    if len(r) >= 4 + words * 4 and r[3] == 0x01:
                        nbytes += words * 4
                    else:
                        bad += 1
            dt = time.perf_counter() - t0
            row['phases'][str(phase)] = {'ok': True, 'MB_s': round(nbytes / dt / 1e6, 3),
                                         'bad': bad, 'blocks': args.rounds * args.depth}
        rows.append(row)
        print(json.dumps(row), flush=True)
    with open(args.output, 'w', encoding='utf-8') as fh:
        json.dump({'address': args.address, 'words': words, 'rows': rows}, fh, indent=2)
    usb.util.release_interface(dev, 0)


if __name__ == '__main__':
    main()
