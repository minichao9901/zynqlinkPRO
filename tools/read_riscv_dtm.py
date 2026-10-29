"""Read a single RISC-V TAP using raw CMSIS-DAP JTAG sequences.

Bypasses the ARM DP/AP calibration and the configurable IDCODE CSR packing.
Only scans IDCODE and DTMCS; does not access memory or halt the target.
"""
import argparse
import json
from pathlib import Path

import usb.util

from dap_pipeline_bench import drain, le, open_dap, xfer


def sequence(out, inp, items):
    payload = [0x14, len(items)]
    sizes = []
    for count, tms, tdi, capture in items:
        assert 1 <= count <= 64
        size = (count + 7) // 8
        payload += [(count & 63) | (tms << 6) | (capture << 7)]
        payload += list(tdi.to_bytes(size, 'little'))
        if capture:
            sizes.append((size, count))
    reply = xfer(out, inp, payload)
    if reply[:2] != b'\x14\x00' or len(reply) != 2 + sum(s for s, _ in sizes):
        raise RuntimeError('JTAG Sequence failed: ' + reply.hex())
    offset = 2
    values = []
    for size, count in sizes:
        values.append(int.from_bytes(reply[offset:offset + size], 'little') & ((1 << count) - 1))
        offset += size
    return values


def read_register(out, inp, ir=None):
    items = [(6, 1, 0, False), (1, 0, 0, False)]  # Reset -> Idle.
    if ir is not None:
        # Idle -> SelectDR -> SelectIR -> CaptureIR -> ShiftIR.
        items += [(2, 1, 0, False), (2, 0, 0, False),
                  (4, 0, ir & 15, True), (1, 1, ir >> 4, True),
                  (1, 1, 0, False), (1, 0, 0, False)]
    # Idle -> SelectDR -> CaptureDR -> ShiftDR; exit on the final data bit.
    items += [(1, 1, 0, False), (2, 0, 0, False),
              (31, 0, 0, True), (1, 1, 0, True),
              (1, 1, 0, False), (8, 0, 0, False)]
    values = sequence(out, inp, items)
    value = values[-2] | (values[-1] << 31)
    ir_capture = None if ir is None else values[0] | (values[1] << 4)
    return dict(ir=ir, ir_capture=ir_capture, value=f'0x{value:08X}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speed-khz', type=int, default=1000,
                        help='Requested CMSIS clock; raw sequences may run slower')
    parser.add_argument('--compare-idcode-command', action='store_true',
                        help='Also run the experimental vendor IR=1 / IDCODE command')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = dict(requested_clock_hz=args.speed_khz * 1000, scans=[])
    dev, out, inp = open_dap()
    try:
        drain(inp)
        for payload in ([2, 2], [0x11] + le(args.speed_khz * 1000), [0x89, 0]):
            reply = xfer(out, inp, payload)
            if reply[:2] != bytes([payload[0], 2 if payload[0] == 2 else 0]):
                raise RuntimeError('Setup failed: ' + reply.hex())
        for ir in (None, None, None, 1, 0x10):
            row = read_register(out, inp, ir)
            report['scans'].append(row)
            print(json.dumps(row), flush=True)
        dtmcs = int(report['scans'][-1]['value'], 16)
        report['dtmcs'] = dict(version=dtmcs & 15, abits=(dtmcs >> 4) & 63,
                               dmistat=(dtmcs >> 10) & 3, idle=(dtmcs >> 12) & 7)
        if args.compare_idcode_command:
            report['vendor_ir_reply'] = xfer(out, inp, [0x8B, 1]).hex()
            report['configure_reply'] = xfer(out, inp, [0x15, 1, 5]).hex()
            report['idcode_command_reply'] = xfer(out, inp, [0x16, 0]).hex()
            report['raw_after_idcode_command'] = read_register(out, inp, 1)
        ids = [int(row['value'], 16) for row in report['scans'][:4]]
        report['valid'] = (len(set(ids)) == 1 and ids[0] not in (0, 0xFFFFFFFF)
                           and ids[0] & 1 == 1
                           and report['scans'][3]['ir_capture'] & 3 == 1
                           and report['scans'][4]['ir_capture'] & 3 == 1
                           and report['dtmcs']['version'] == 1
                           and report['dtmcs']['abits'] > 0
                           and report['dtmcs']['dmistat'] == 0)
        print(json.dumps(report, indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if not report['valid']:
            raise SystemExit('RISC-V TAP validation failed')
    finally:
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
