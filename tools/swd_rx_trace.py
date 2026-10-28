"""Capture 16 FCLK samples from SWDIO release without an external probe.

Initialize transport without reading DPIDR, apply optional RX overrides, arm
CSR 0x54 raw mode, then perform exactly one DPIDR read. No target RAM writes.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys

from dap_pipeline_bench import open_dap, setup, xfer, le

ROOT = Path(__file__).resolve().parents[1]


def arm():
    work = ROOT / 'build/swd_rx_trace'
    work.mkdir(parents=True, exist_ok=True)
    script = work / 'arm.tcl'
    script.write_text('connect\ntargets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}\n'
                      'set c [mrd -force -value 0x400100f8]\n'
                      'if {($c >> 16) == 0x5343} {mwr -force 0x400100f8 1;mwr -force 0x400100f8 0}\n'
                      'mwr -force 0x40010054 3\nset s [mrd -force -value 0x40010054]\n'
                      'if {!($s & 0x40000000)} {error "SWD raw trace not supported by loaded bit"}\n'
                      'disconnect\nexit\n')
    subprocess.run([sys.executable, str(ROOT / 'tools/run_xsct.py'), str(script)], check=True)


def clock_observer():
    from jtag_internal_trace import run
    import re
    text = run('puts [format "CLKOBS %08X %08X" [mrd -force -value 0x400100f8] [mrd -force -value 0x400100fc]]')
    match = re.search(r'CLKOBS ([0-9A-Fa-f]{8}) ([0-9A-Fa-f]{8})', text)
    assert match, text
    counter, flags = [int(value, 16) for value in match.groups()]
    if counter >> 16 != 0x5343:
        return None
    return dict(pad_rises=(counter >> 8) & 255, intended_rises=counter & 255,
                rise_while_low=bool(flags & 8), fall_while_high=bool(flags & 4))


def initialize(out, inp, khz, boundary=None, phase=None):
    assert xfer(out, inp, [2, 1]) == b'\x02\x01'
    assert xfer(out, inp, [0x11] + le(khz * 1000)) == b'\x11\x00'
    xfer(out, inp, [0x13, 0])
    xfer(out, inp, [4, 1, 0, 0, 0, 0])  # no retry: preserve the first response
    if phase is not None:
        assert xfer(out, inp, [0x80, phase])[1] == 0
    if boundary is not None:
        assert xfer(out, inp, [0x8a, boundary])[1] == 0
    xfer(out, inp, [0x12, 152] + [255] * 8 + [0x9e, 0xe7] + [255] * 8 + [0])


def decode(response):
    assert len(response) == 70 and response[:2] == b'\x88\x00', response.hex()
    status = int.from_bytes(response[2:6], 'little')
    assert status >> 30 == 3 and (status >> 4) & 65535 == 16, hex(status)
    rows = []
    for i, (raw,) in enumerate(struct.iter_unpack('<I', response[6:])):
        assert raw >> 28 == 10 and ((raw >> 24) & 15) == i, hex(raw)
        rows.append(dict(index=i, raw=hex(raw), request=(raw >> 16) & 255,
                         clock_pad=(raw >> 13) & 1, boundary=(raw >> 12) & 1, phase=(raw >> 11) & 1,
                         result_valid=(raw >> 10) & 1, parity_error=(raw >> 9) & 1,
                         ack=(raw >> 6) & 7, released=(raw >> 5) & 1,
                         host_out=(raw >> 4) & 1, swclk=(raw >> 3) & 1,
                         pad=(raw >> 2) & 1, q1=(raw >> 1) & 1, q2=raw & 1))
    return status, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speeds', default='1000,10000,25000,35000,50000,60000')
    ap.add_argument('--boundary', type=int, choices=[0, 1])
    ap.add_argument('--phase', type=int, choices=[0, 1])
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    dev, out, inp = open_dap()
    report = {'rows': []}
    try:
        for khz in map(int, args.speeds.split(',')):
            setup(out, inp, 50000)
            initialize(out, inp, khz, args.boundary, args.phase)
            diagnostic = xfer(out, inp, [0x80, 255])
            hz, cfg = struct.unpack_from('<II', diagnostic, 4)
            arm()
            reply = xfer(out, inp, [5, 0, 1, 2])
            status, samples = decode(xfer(out, inp, [0x88, 0]))
            rises = [i for i in range(len(samples) - 1)
                     if samples[i]['swclk'] == 0 and samples[i + 1]['swclk'] == 1]
            selected = 'q1' if (cfg >> 17) & 1 else 'q2'
            windows = {}
            for label, start in [('short', 1), ('legacy', 2)]:
                indices = rises[start:start + 3]
                bits = [samples[i][selected] for i in indices]
                windows[label] = dict(indices=indices, bits_in_wire_order=bits,
                                      ack=sum(bit << n for n, bit in enumerate(bits)) if len(bits) == 3 else None)
            row = dict(requested_khz=khz, fclk_hz=hz, swclk_hz=hz / 2,
                       cfg=hex(cfg), boundary=(cfg >> 18) & 1, phase=(cfg >> 17) & 1,
                       reply=reply.hex(), passed=reply == bytes.fromhex('0501017714a01b'),
                       trace_status=hex(status), ack_windows=windows, samples=samples,
                       clock_observer=clock_observer())
            report['rows'].append(row)
            print(json.dumps({k: v for k, v in row.items() if k != 'samples'}), flush=True)
    finally:
        setup(out, inp, 50000)
        xfer(out, inp, [2, 0])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    return int(any(not row['passed'] for row in report['rows']))


if __name__ == '__main__':
    raise SystemExit(main())
