"""Regression matrix for the SWD controller against the real Cortex-M0+ model.

Compiles once with Icarus Verilog (the ARM DesignStart model stays outside the
repository) and then runs the testbench with different plusargs. Success
requires the PASS marker; a FAULT-model warning is reported separately.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = Path('E:/Share/github/ZYNQ7020_YuanZi/ZYNQ_DAPLINK_RTL_100TO50MHz/'
                     'ZYNQ_DAPLINK_RTL_100TO50MHz.srcs/sim_1/imports/cortexm0')
RTL = ['swd_core.v', 'probe_sample_engine.v', 'swd_controller.v', 'swd_batch_engine.v', 'dap_transfer_block_engine.v']
SIM = ['sim_primitives.v', 'xpm_memory_tdpram.sv', 'tb_cortexm0_link.sv']
MODEL = ['swd_cortexm0_target.v', 'CORTEXM0INTEGRATION.v', 'cortexm0ds_logic.v']

MATRIX = [
    ('base', ['+words=16']),
    ('sampler', ['+words=16', '+sampler']),
    ('words64', ['+words=64']),
    ('packets', ['+packets']),
    ('packets_err', ['+packets', '+errors']),
    ('ack1', ['+ack_delay=1', '+words=16']),
    ('ack2', ['+ack_delay=2', '+words=16']),
    ('ack3', ['+ack_delay=3', '+words=16']),
    ('ack5', ['+ack_delay=5', '+words=16']),
    ('ack7', ['+ack_delay=7', '+words=16']),
    ('ack1_pkt_err', ['+ack_delay=1', '+packets', '+errors']),
    ('ack3_pkt_err', ['+ack_delay=3', '+packets', '+errors']),
    ('ack7_pkt_err', ['+ack_delay=7', '+packets', '+errors']),
    ('turn1', ['+turn_extra=1', '+packets']),
    ('turn2', ['+turn_extra=2', '+packets']),
    ('turn3', ['+turn_extra=3', '+packets']),
    ('ret8', ['+return_ns=8.0', '+packets']),
    ('ret30', ['+return_ns=30.0', '+packets']),
    ('ret50', ['+return_ns=50.0', '+packets']),
    ('phase1', ['+phase=1', '+packets']),
    ('rxearly', ['+rx_early=1', '+packets']),
]


def compile_sim(model: Path, out: Path) -> None:
    cmd = ['iverilog', '-g2012', '-o', str(out), '-s', 'tb_cortexm0_link', '-I', str(ROOT / 'fpga/rtl')]
    cmd += [str(ROOT / 'fpga/sim' / f) for f in SIM]
    cmd += [str(ROOT / 'fpga/rtl' / f) for f in RTL]
    cmd += [str(model / f) for f in MODEL]
    subprocess.run(cmd, check=True, cwd=ROOT)


def run(vvp: Path, args):
    p = subprocess.run(['vvp', str(vvp)] + args, cwd=ROOT, capture_output=True,
                       text=True, errors='replace', timeout=900)
    log = p.stdout + p.stderr
    passed = p.returncode == 0 and 'PASS CortexM0' in log
    skip = 'FAULT_SKIP' in log
    fatal = next((l.strip() for l in log.splitlines() if 'FATAL' in l), '')
    return passed, skip, fatal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-dir', default=str(DEFAULT_MODEL))
    ap.add_argument('--only', default='')
    ap.add_argument('--fast', action='store_true')
    args = ap.parse_args()
    model = Path(args.model_dir)
    if not (model / 'cortexm0ds_logic.v').is_file():
        raise SystemExit(f'model not found: {model}')
    out = ROOT / 'build/cortexm0_regress'
    out.mkdir(parents=True, exist_ok=True)
    vvp = out / 'sim.vvp'
    compile_sim(model, vvp)
    rows = []
    for name, plusargs in MATRIX:
        if args.fast and '+packets' in plusargs:
            continue
        if args.only and args.only not in name:
            continue
        passed, skip, fatal = run(vvp, plusargs)
        rows.append({'name': name, 'passed': passed, 'fault_model_skip': skip, 'fatal': fatal})
        print(f'{name:16s} {"PASS" if passed else "FAIL"}'
              f'{" (fault model skip)" if skip else ""}'
              f'{"" if passed else "  " + fatal}', flush=True)
    (out / 'summary.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    failed = [r['name'] for r in rows if not r['passed']]
    print(f'\n{len(rows) - len(failed)}/{len(rows)} passed')
    if failed:
        raise SystemExit('failed: ' + ', '.join(failed))


if __name__ == '__main__':
    main()
