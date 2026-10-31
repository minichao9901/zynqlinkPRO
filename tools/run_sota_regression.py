"""Reproduce the F103ZE 50/60MHz record after explicit pair/clock setup.

This runner does not load firmware or change target clocks. For the current
CDC application use run_f103_clock_fixture.py and run_f103_jtag_fixture.py as
outer wrappers. Output files must be new; historical evidence is not replaced.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bit', type=Path, required=True)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--phase', choices=['peak_rtt', 'hss'], default='peak_rtt')
    p.add_argument('--speeds', default='50000,60000', help='Requested kHz: 50000,60000')
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args()
    speeds = [int(v) for v in a.speeds.split(',')]
    if not speeds or any(v not in (50000, 60000) for v in speeds):
        p.error('--speeds must contain only 50000 and/or 60000 kHz')
    root = Path(__file__).resolve().parents[1]
    dest = a.output_dir.resolve()
    art = ['--bit', str(a.bit.resolve()), '--elf', str(a.elf.resolve())]
    jobs = []
    if a.phase == 'peak_rtt':
        for tr in ['swd', 'jtag']:
            for speed in speeds:
                options = ['h743_peak.py', '--transport', tr, '--jtag-ir', '4,5', '--speed', str(speed),
                           '--address', '0x20008000', '--words', '512', '--depth', '32',
                           '--loops', '256', '--repeats', '3', *art]
                if tr == 'swd' and speed == 60000:
                    options += ['--soak-seconds', '30']
                jobs.append((f'peak_{tr}_{speed}', options))
        for tr in ['swd', 'jtag']:
            for speed in speeds:
                jobs.append((f'rtt_{tr}_{speed*1000}', ['benchmark_rtt_forward.py', '--transport', tr,
                             '--speeds', str(speed*1000), '--chunks', '2048', '--seconds', '3',
                             '--repeats', '2', *art]))
    else:
        points = [('swd', 50000, 1, '24'), ('swd', 60000, 1, '24'),
                  ('swd', 50000, 8, '236'), ('swd', 60000, 8, '197,195'),
                  ('jtag', 50000, 1, '89,60'), ('jtag', 60000, 1, '74,40'),
                  ('jtag', 50000, 8, '529,527'), ('jtag', 60000, 8, '442,441,411')]
        for tr, speed, nvars, periods in points:
            if speed in speeds:
                jobs.append((f'hss_{tr}_{speed*1000}_{nvars}', ['benchmark_probe_stream.py',
                             '--transport', tr, '--speeds', str(speed*1000), '--variables', str(nvars),
                             '--periods', periods, '--seconds', '2', '--repeats', '3', *art]))
    plan = []
    for name, options in jobs:
        output = dest / (name + '.json')
        command = [sys.executable, '-X', 'utf8', str(root/'tools'/options[0]), *options[1:],
                   '--output', str(output)]
        plan.append(dict(name=name, output=str(output), command=command))
        if not a.dry_run and (output.exists() or output.with_suffix('.log').exists()):
            p.error('Use a fresh output directory: ' + str(output))
    if a.dry_run:
        print(json.dumps(plan, indent=2))
        return
    dest.mkdir(parents=True, exist_ok=True)
    results = []
    for job in plan:
        output = Path(job['output'])
        with output.with_suffix('.log').open('w', encoding='utf-8') as log:
            run = subprocess.run(job['command'], cwd=root, stdout=log, stderr=subprocess.STDOUT)
        value = json.loads(output.read_text()) if output.exists() else {}
        passed = run.returncode == 0 and value.get('passed', True) and not value.get('recover_error')
        row = dict(**job, returncode=run.returncode, passed=passed,
                   restore_match=value.get('restore_match'))
        results.append(row)
        (dest/(a.phase+'_runs.json')).write_text(json.dumps(results, indent=2)+'\n')
        print(job['name'], 'PASS' if passed else 'FAIL', flush=True)
        if not passed or not value.get('restore_match'):
            raise RuntimeError('Case or SRAM restoration failed; inspect saved logs before continuing')


if __name__ == '__main__':
    main()
