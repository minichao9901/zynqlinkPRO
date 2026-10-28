"""Run XSim against the Cortex-M3 DesignStart RTL.

The CM3 RTL is IEEE-1735 encrypted for Xilinx tools, so it only simulates
inside Vivado/XSim. It is not part of this repository; point ``CM3_RTL`` (or
``--rtl``) at the directory holding cortexm3_integration.v and friends, for
example::

    reference/cortex_m3_on_xc7a100t/cm3_core/Arm_ipi_repository/CM3DbgAXI/rtl

Usage::

    python tools/run_cm3_sim.py --top tb_cm3_smoke
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIVADO = Path(r'E:/Xilinx/Vivado/2018.3')
DEFAULT_RTL = ROOT / 'reference/cortex_m3_on_xc7a100t/cm3_core/Arm_ipi_repository/CM3DbgAXI/rtl'


def environment():
    paths = [VIVADO / 'lib/win64.o', VIVADO / 'bin/unwrapped/win64.o',
             VIVADO / 'bin/unwrapped/win64.o/Microsoft.VC140.CRT', VIVADO / 'tps/win64',
             VIVADO / 'tps/win64/jre9.0.4/bin/server', VIVADO / 'tps/win64/jre9.0.4/bin']
    env = os.environ.copy()
    env['PATH'] = os.pathsep.join(map(str, paths)) + os.pathsep + env['PATH']
    env.update(XILINX_VIVADO=VIVADO.as_posix(), RDI_APPROOT=VIVADO.as_posix(),
               HDI_APPROOT=VIVADO.as_posix(), RDI_BINROOT=(VIVADO / 'bin').as_posix(),
               RDI_PLATFORM='win64', RDI_OPT_EXT='.o',
               RDI_DATADIR=(VIVADO / 'data').as_posix(),
               RDI_BINDIR=(VIVADO / 'bin').as_posix(),
               RDI_LIBDIR=(VIVADO / 'lib/win64.o').as_posix(),
               TCL_LIBRARY=(VIVADO / 'tps/tcl/tcl8.5').as_posix())
    return env


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--top', required=True)
    ap.add_argument('--rtl', type=Path, default=Path(os.environ.get('CM3_RTL', DEFAULT_RTL)))
    ap.add_argument('--rebuild', action='store_true')
    ap.add_argument('plusargs', nargs='*')
    args = ap.parse_args()

    rtl = args.rtl.resolve()
    if not (rtl / 'cortexm3_integration.v').is_file():
        sys.exit(f'CM3 RTL not found: {rtl}\nset CM3_RTL or pass --rtl')

    work = ROOT / 'build/cm3_sim' / args.top
    work.mkdir(parents=True, exist_ok=True)
    env = environment()
    exe = VIVADO / 'bin/unwrapped/win64.o'

    def run(cmd, timeout=3600):
        p = subprocess.run([str(c) for c in cmd], cwd=str(work), env=env,
                           capture_output=True, text=True, errors='replace', timeout=timeout)
        log = p.stdout + p.stderr
        (work / (Path(str(cmd[0])).stem + '.log')).write_text(log, encoding='utf-8', errors='replace')
        return p, log

    if args.rebuild or not (work / 'xsim.dir').exists():
        rtl_files = sorted(str(p) for p in rtl.glob('*.v'))
        sim_files = [str(ROOT / 'fpga/sim/axi3_sram.v'), str(ROOT / 'fpga/sim/cm3_target.sv'),
                     str(ROOT / f'fpga/sim/{args.top}.sv')]
        p, log = run([exe / 'xvlog.exe', '--relax', '-i', str(rtl), *rtl_files, *sim_files])
        if p.returncode:
            print(log[-4000:])
            sys.exit('xvlog failed')
        p, log = run([exe / 'xelab.exe', '--debug', 'typical', '-s', args.top + '_snap', args.top])
        if p.returncode:
            print(log[-4000:])
            sys.exit('xelab failed')
        print('built', args.top)

    cmd = [exe / 'xsim.exe', args.top + '_snap', '-runall', '-log', 'xsim.log']
    for a in args.plusargs:
        cmd += ['-testplusarg', a]
    p, log = run(cmd)
    tail = [l for l in log.splitlines() if ('PASS' in l or 'FAIL' in l or 'Error' in l or 'IDCODE' in l)]
    print('\n'.join(tail[-20:]) or log[-2000:])
    return 0 if p.returncode == 0 and 'PASS' in log else 1


if __name__ == '__main__':
    raise SystemExit(main())
