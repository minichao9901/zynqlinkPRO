"""Functional speed matrix for the CM3 target.

Runs the SWD and JTAG link testbenches against the real Cortex-M3 DesignStart
core at every link rate, with and without the short receive boundary, and
records pass/fail per point. Throughput numbers come from the RTL cycle
benches (``sim_regress_matrix.py``); this matrix proves the link works at each
rate.

Usage::

    python tools/run_cm3_matrix.py --out build/cm3_matrix/main.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'tools/run_cm3_sim.py'
SPEEDS = [1, 5, 10, 25, 35, 50, 60]


def run(top, plusargs, timeout=3600):
    cmd = [sys.executable, str(RUNNER), '--top', top, *plusargs]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       errors='replace', timeout=timeout)
    log = ROOT / f'build/cm3_sim/{top}/xsim.log'
    text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else p.stdout
    return p.returncode, text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--only', default='', help='substring filter on the case name')
    args = ap.parse_args()

    rows = []
    for f in SPEEDS:
        for rx in (0, 1):
            name = f'swd_{f}MHz_rx{rx}'
            if args.only and args.only not in name:
                continue
            half = 250.0 / f
            code, log = run('tb_cm3_swd', [f'half_ns={half}', f'rx_boundary={rx}', 'streams'])
            rows.append({
                'case': name, 'protocol': 'SWD', 'speed_MHz': f, 'rx_boundary': rx,
                'pass': code == 0 and 'PASS CortexM3' in log and 'RTT_PASS' in log,
                'hss': 'HSS_PASS' in log, 'rtt': 'RTT_PASS' in log,
                'fail': next((l.strip() for l in log.splitlines() if 'Fatal' in l), ''),
            })
            print(f"{name:22s} {'PASS' if rows[-1]['pass'] else 'FAIL'} {rows[-1]['fail'][:70]}", flush=True)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(rows, indent=2), encoding='utf-8')

    for f in SPEEDS:
        name = f'jtag_{f}MHz'
        if args.only and args.only not in name:
            continue
        clk = 500.0 / f
        code, log = run('tb_cm3_jtag', [f'clk_ns={clk}'])
        rows.append({
            'case': name, 'protocol': 'JTAG', 'speed_MHz': f,
            'pass': code == 0 and 'PASS JTAG full pipeline' in log,
            'hss': 'JTAG HSS' in log, 'rtt': 'RTT unaligned' in log,
            'fail': next((l.strip() for l in log.splitlines() if 'Fatal' in l), ''),
        })
        print(f"{name:22s} {'PASS' if rows[-1]['pass'] else 'FAIL'} {rows[-1]['fail'][:70]}", flush=True)
        args.out.write_text(json.dumps(rows, indent=2), encoding='utf-8')

    bad = [r['case'] for r in rows if not r['pass']]
    print(f'\n{len(rows)-len(bad)}/{len(rows)} passed')
    if bad:
        print('failed: ' + ', '.join(bad))


if __name__ == '__main__':
    main()
