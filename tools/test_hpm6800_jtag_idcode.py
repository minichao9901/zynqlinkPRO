"""Read the RISC-V IDCODE from HPM6800EVK through the probe JTAG core.

The probe JTAG backend is ADIv5-oriented: its IDCODE operation loads a fixed
instruction (0x0E). HPM6800 is a RISC-V DTM whose IR is 5 bits with
IDCODE=0x01, so the firmware exposes Vendor11 to set that value first.
"""
import argparse
import json
import sys
from pathlib import Path

import usb.util

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dap_pipeline_bench import open_dap, xfer, le, drain

EXPECT = 0x1000563D


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed-khz', type=int, default=1000)
    ap.add_argument('--idcode-ir', default='1')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    dev, out, inp = open_dap()
    rows = []
    try:
        drain(inp)
        print('connect JTAG  ', xfer(out, inp, [0x02, 2]).hex())
        ir = int(args.idcode_ir, 0)
        reply = xfer(out, inp, [0x8B, ir & 0xFF])
        print('idcode ir set ', reply.hex())
        print('clock         ', xfer(out, inp, [0x11] + le(args.speed_khz * 1000)).hex())
        print('swj           ', xfer(out, inp, [0x12, 88] + [0xFF] * 8 + [0x3C, 0xE7, 0x1F]).hex())
        print('configure[5]  ', xfer(out, inp, [0x15, 1, 5]).hex())
        for i in range(3):
            reply = xfer(out, inp, [0x16, 0])
            value = int.from_bytes(reply[2:6], 'little') if len(reply) >= 6 else None
            row = dict(attempt=i, reply=reply.hex(), idcode=None if value is None else '0x%08X' % value,
                       expected='0x%08X' % EXPECT, match=value == EXPECT)
            rows.append(row)
            print(json.dumps(row), flush=True)
        print('pins          ', xfer(out, inp, [0x10, 0, 0x0F, 0, 0, 0, 0]).hex())
    finally:
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(rows, indent=2) + '\n')
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
