"""Sweep SWCLK frequency and sampling phase after training the link at 50 MHz.

The H743 DP does not answer the first frames at high clock, so the link is
established at 50 MHz first (same as OpenOCD: connect at 50, then raise the
speed).  For each frequency the script reports IDCODE success with phase 0/1,
both without and with a fresh activation sequence.
"""
import argparse
import json

import libusb_package
import usb.core
import usb.util

PKT = 4096
IDCODE = 0x6BA02477
LINE_RESET_SEQ = [0xFF] * 8 + [0x9E, 0xE7] + [0xFF] * 8 + [0x00]  # 152 bits


def le(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--freqs', default='60000,62000,64000,66000,68000,69000,70000,72000,75000,80000')
    ap.add_argument('--trials', type=int, default=20)
    ap.add_argument('--output', default='results/optimization/phase_sweep.json')
    args = ap.parse_args()

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

    def xfer(payload):
        b = bytes(payload)
        out.write(b, timeout=3000)
        if len(b) % 512 == 0:
            out.write(b'', timeout=3000)
        return bytes(inp.read(PKT, timeout=3000))

    while True:
        try:
            inp.read(PKT, timeout=60)
        except usb.core.USBTimeoutError:
            break

    def activate():
        xfer([0x12, 152] + LINE_RESET_SEQ)

    def set_clock(khz):
        try:
            xfer([0x11] + le(khz * 1000))
        except usb.core.USBTimeoutError:
            pass

    def query():
        r = xfer([0x80, 0xFF])
        if len(r) < 12 or r[0] != 0x80:
            return None
        return {'hz': int.from_bytes(bytes(r[4:8]), 'little'), 'phase': r[2]}

    def set_phase(phase):
        r = xfer([0x80, phase])
        return len(r) >= 2 and r[1] == 0

    def idcode_ok():
        try:
            r = xfer([0x05, 0x00, 0x01, 0x02])
        except usb.core.USBTimeoutError:
            return False
        return len(r) >= 7 and r[2] == 0x01 and r[3:7] == bytes(le(IDCODE))

    def rate(trials):
        return sum(1 for _ in range(trials) if idcode_ok())

    # Train the link at 50 MHz first.
    xfer([0x02, 0x01])
    xfer([0x13, 0x00])
    xfer([0x04, 0x00, 0x40, 0x00, 0x00, 0x00])
    set_clock(50000)
    activate()
    if not idcode_ok():
        raise RuntimeError('link training at 50 MHz failed')

    rows = []
    for f in [int(x) for x in args.freqs.split(',')]:
        set_clock(f)
        info = query()
        row = {'request_khz': f, 'reported_hz': info['hz'] if info else None, 'phases': {}}
        for phase in (0, 1):
            entry = {}
            if set_phase(phase):
                entry['live'] = {'ok': rate(args.trials), 'trials': args.trials}
                activate()
                entry['reactivate'] = {'ok': rate(args.trials), 'trials': args.trials}
            else:
                entry['live'] = {'ok': 0, 'trials': args.trials, 'note': 'phase rejected'}
            row['phases'][str(phase)] = entry
        rows.append(row)
        print(json.dumps(row), flush=True)

    with open(args.output, 'w', encoding='utf-8') as fh:
        json.dump({'idcode': hex(IDCODE), 'rows': rows}, fh, indent=2)
    usb.util.release_interface(dev, 0)


if __name__ == '__main__':
    main()
