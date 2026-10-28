"""Map SWD RX windows; apply overrides before the first DPIDR read.

A speed passes this diagnostic if at least one boundary/phase combination works.
Use test_swd_lowfreq_board.py to accept the firmware's automatic profile and SRAM.
"""
import argparse
import json
from pathlib import Path

from dap_pipeline_bench import open_dap, setup, xfer
from swd_rx_trace import initialize


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speeds', default='1000,10000,25000,35000,50000,60000')
    ap.add_argument('--output', type=Path, default=Path('build/swd_boundary_check.json'))
    args = ap.parse_args()
    dev, out, inp = open_dap()
    speeds = [int(v) for v in args.speeds.split(',')]
    report = {'rows': []}
    try:
        for khz in speeds:
            for boundary in [0, 1]:
                for phase in [0, 1]:
                    row = dict(requested_khz=khz, boundary=boundary, phase=phase, passed=False)
                    try:
                        setup(out, inp, 50000)
                        initialize(out, inp, khz, boundary, phase)
                        diag = xfer(out, inp, [0x80, 255])
                        row['fclk_hz'] = int.from_bytes(diag[4:8], 'little')
                        row['cfg'] = hex(int.from_bytes(diag[8:12], 'little'))
                        reply = xfer(out, inp, [5, 0, 1, 2])
                        row['reply'] = reply.hex()
                        row['passed'] = reply == bytes.fromhex('0501017714a01b')
                    except Exception as exc:
                        row['error'] = repr(exc)
                    report['rows'].append(row)
                    print(json.dumps(row), flush=True)
    finally:
        setup(out, inp, 50000)
        xfer(out, inp, [2, 0])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    return int(any(not any(r['passed'] for r in report['rows'] if r['requested_khz'] == khz) for khz in speeds))


if __name__ == '__main__':
    raise SystemExit(main())
