"""Sweep the JTAG core's TDO-return timing across FCLK periods.

Reproduces the board's behaviour offline: the DAP model drives TDO through one
absolute round-trip delay, so shrinking the FCLK period eats the capture margin
exactly as it does on hardware.
"""
import argparse
import itertools
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'fpga/sim'
RTL = ROOT / 'fpga/rtl'
OUT = ROOT / 'build/jtag_timing'
VIVADO = Path('E:/Xilinx/Vivado/2018.3/bin')

SOURCES = [RTL / 'jtag_core.v', RTL / 'jtag_shift.v',
           SIM / 'jtag_dp_model.sv', SIM / 'tb_jtag_timing.sv']


def run(cmd):
    return subprocess.run(cmd, cwd=OUT, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--clkns', default='8.33,9.44,10.0,11.67,12.22',
                    help='FCLK periods in ns')
    ap.add_argument('--tdons', default='12', help='TDO round trip in ns')
    ap.add_argument('--modes', default='0,1,16,17',help='IDDR phase bit0, previous-bit window bit4')
    ap.add_argument('--output',type=Path,default=ROOT/'results/jtag/iddr_timing_sweep.json')
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    exe=OUT/'timing.vvp'
    subprocess.run(['iverilog','-g2012','-s','tb_jtag_timing','-o',str(exe),*map(str,SOURCES)],check=True)

    rows = []
    for clkns, tdons, late in itertools.product(
            a.clkns.split(','), a.tdons.split(','), a.modes.split(',')):
        clk_ps = int(round(float(clkns) * 1000))
        tdo_ps = int(round(float(tdons) * 1000))
        (OUT / 'sim_cfg.txt').write_text('%d %d %d\n' % (clk_ps, tdo_ps, int(late)))
        sim = run(['vvp',str(exe)])
        text = (sim.stdout or '') + (sim.stderr or '')
        m = re.search(r'RESULT .*', text)
        line = m.group(0).strip() if m else 'RESULT(no output) %s' % text[-200:]
        verdict = 'PASS' if ' PASS' in line else 'FAIL'
        detail = '' if verdict == 'PASS' else line.split('FAIL', 1)[-1].strip()
        rows.append((float(clkns), float(tdons), int(late), verdict, detail))
        print(line, flush=True)

    print()
    print('FCLK ns  TCK MHz  tdo ns  late  result')
    for clkns, tdons, late, verdict, detail in rows:
        print('%7.2f  %7.2f  %6.1f  %4d  %s %s' % (
            clkns, 1e3 / (2 * clkns), tdons, late, verdict, detail))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps([dict(fclk_period_ns=c,requested_tck_MHz=500/c,tdo_return_ns=t,
                          mode=m,passed=v=='PASS',detail=d) for c,t,m,v,d in rows],indent=2))
    groups={}
    for c,t,m,v,d in rows:groups.setdefault((c,t),[]).append(v=='PASS')
    missing=[(c,t) for (c,t),passes in groups.items() if not any(passes)]
    print('NO_VALID_PHASE',missing)
    if missing:sys.exit(1)


if __name__ == '__main__':
    main()
