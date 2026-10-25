"""Sweep SWDIO input delay (IDELAY taps) x SWCLK frequency x sampling phase.

Vendor command 0x82 sets SWD_CFG[22:18] (0..31 IDELAY taps, ~78 ps each).
For every combination the link is re-trained at the target frequency, the DP
is powered up and a block read is verified; working points then get a
pipelined throughput measurement.
"""
import argparse
import json
import time

import libusb_package
import usb.core
import usb.util

PKT = 4096
SEQ = [0xFF] * 8 + [0x9E, 0xE7] + [0xFF] * 8 + [0x00]


def le(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--freqs', default='60000,66000,69000,75000')
    ap.add_argument('--phases', default='0,1')
    ap.add_argument('--delays', default=','.join(str(i) for i in range(32)))
    ap.add_argument('--address', default='0x24010000')
    ap.add_argument('--words', type=int, default=1023)
    ap.add_argument('--depth', type=int, default=8)
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--idcode', default='0x6BA02477')
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    addr = int(args.address, 0)
    idcode = int(args.idcode, 0)

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

    def set_phase(phase):
        return xfer([0x80, phase])[1] == 0

    def set_delay(taps):
        r = xfer([0x82, taps])
        return len(r) >= 3 and r[1] == 0

    def query_delay():
        r = xfer([0x82, 255])
        return r[2] if len(r) >= 3 else None

    def activate():
        xfer([0x12, 152] + SEQ)

    def read_dp(req):
        r = xfer([0x05, 0x00, 0x01, req])
        return r[3:7] if len(r) >= 7 and r[2] == 0x01 else None

    def dp_power_up():
        xfer([0x05, 0x00, 0x01, 0x00] + le(0x1E))
        xfer([0x05, 0x00, 0x01, 0x04] + le(0x50000000))
        for _ in range(20):
            val = read_dp(0x06)
            if val and (int.from_bytes(val, 'little') & 0xA0000000) == 0xA0000000:
                break
            time.sleep(0.002)
        xfer([0x05, 0x00, 0x01, 0x08] + le(0))
        xfer([0x05, 0x00, 0x01, 0x01] + le(0x23000052))
        xfer([0x05, 0x00, 0x01, 0x05] + le(addr))

    def probe():
        r = xfer([0x05, 0x00, 0x01, 0x02])
        if len(r) < 7 or r[2] != 0x01 or r[3:7] != bytes(le(idcode)):
            return False
        dp_power_up()
        r = xfer([0x06, 0x00, 0x04, 0x00, 0x0F])
        return len(r) >= 4 + 16 and r[3] == 0x01

    def measure():
        nbytes = 0
        bad = 0
        t0 = time.perf_counter()
        for _ in range(args.rounds):
            for _ in range(args.depth):
                send([0x06, 0x00, 0xFF, 0x03, 0x0F])
            for _ in range(args.depth):
                r = recv()
                if len(r) >= 4 + args.words * 4 and r[3] == 0x01:
                    nbytes += args.words * 4
                else:
                    bad += 1
        dt = time.perf_counter() - t0
        return round(nbytes / dt / 1e6, 3), bad

    # Train at 50 MHz.
    xfer([0x02, 0x01])
    xfer([0x13, 0x00])
    xfer([0x04, 0x00, 0x40, 0x00, 0x00, 0x00])
    set_clock(50000)
    activate()
    if not probe():
        raise RuntimeError('link training at 50 MHz failed')
    print('trained, delay=', query_delay(), flush=True)

    rows = []
    for khz in [int(x) for x in args.freqs.split(',')]:
        for phase in [int(x) for x in args.phases.split(',')]:
            for taps in [int(x) for x in args.delays.split(',')]:
                set_clock(khz)
                set_phase(phase)
                if not set_delay(taps):
                    continue
                activate()
                if not probe():
                    continue
                rate, bad = measure()
                row = {'freq_khz': khz, 'phase': phase, 'taps': taps,
                       'MB_s': rate, 'bad': bad}
                rows.append(row)
                print(json.dumps(row), flush=True)
    with open(args.output, 'w', encoding='utf-8') as fh:
        json.dump({'address': args.address, 'rows': rows}, fh, indent=2)
    usb.util.release_interface(dev, 0)


if __name__ == '__main__':
    main()
