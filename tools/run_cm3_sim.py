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
import hashlib
import os
import re
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
    ap.add_argument('--work-dir',type=Path,help='Isolated simulator output/library directory')
    ap.add_argument('--debug', choices=['off','typical','all'], default='off', help='Enable waveform/debug instrumentation only when needed')
    ap.add_argument('plusargs', nargs='*')
    args = ap.parse_args()

    rtl = args.rtl.resolve()
    if not (rtl / 'cortexm3_integration.v').is_file():
        sys.exit(f'CM3 RTL not found: {rtl}\nset CM3_RTL or pass --rtl')

    work = args.work_dir.resolve() if args.work_dir else ROOT / 'build/cm3_sim' / args.top
    work.mkdir(parents=True, exist_ok=True)
    env = environment()
    exe = VIVADO / 'bin/unwrapped/win64.o'

    def run(cmd, timeout=3600):
        p = subprocess.run([str(c) for c in cmd], cwd=str(work), env=env,
                           capture_output=True, text=True, errors='replace', timeout=timeout)
        log = p.stdout + p.stderr
        (work / (Path(str(cmd[0])).stem + '.log')).write_text(log, encoding='utf-8', errors='replace')
        return p, log

    # A worktree has its own sources, and a prior failed compile may leave an
    # xsim.dir behind. Reuse only a successful snapshot of these exact inputs.
    inputs = sorted([*(ROOT / 'fpga/rtl').glob('*.v'),
                     *(ROOT / 'fpga/sim').glob('*.v'),
                     *(ROOT / 'fpga/sim').glob('*.sv'),
                     *(ROOT / 'fpga/sim').glob('*.svh'),
                     *rtl.glob('*.v'), *rtl.glob('*.vp')])
    digest = hashlib.sha256((args.top + str(VIVADO) + args.debug).encode())
    for source in inputs:
        digest.update(str(source).encode())
        digest.update(source.read_bytes())
    fingerprint = digest.hexdigest()
    stamp = work / 'snapshot.sha256'
    if args.rebuild or not stamp.exists() or stamp.read_text().strip() != fingerprint:
        stamp.unlink(missing_ok=True)
        rtl_files = sorted(str(p) for p in rtl.glob('*.v'))
        dut_files = sorted(str(p) for p in (ROOT / 'fpga/rtl').glob('*.v'))
        sim_v = [str(ROOT / 'fpga/sim/axi3_sram.v'),
                 str(ROOT / 'fpga/sim/sim_primitives.v')]
        sim_sv = [str(ROOT / 'fpga/sim/xpm_memory_tdpram.sv'),
                  str(ROOT / 'fpga/sim/jtag_dp_model.sv'),
                  str(ROOT / 'fpga/sim/cm3_target.sv'),
                  str(ROOT / f'fpga/sim/{args.top}.sv')]
        if args.top == 'tb_cm3_etm':
            sim_sv.insert(-1, str(ROOT / 'fpga/sim/tb_cm3_swd.sv'))
        p, log = run([exe / 'xvlog.exe', '--relax', '-i', str(rtl),
                      *rtl_files, *dut_files, *sim_v])
        if p.returncode:
            print(log[-4000:])
            sys.exit('xvlog failed (verilog)')
        p, log = run([exe / 'xvlog.exe', '--relax', '--sv', '-i',str(ROOT/'fpga/sim'), *sim_sv])
        if p.returncode:
            print(log[-4000:])
            sys.exit('xvlog failed (systemverilog)')
        debug_args = [] if args.debug=='off' else ['--debug', args.debug]
        p, log = run([exe / 'xelab.exe', '--mt', '2', *debug_args, '-s', args.top + '_snap', args.top])
        if p.returncode:
            print(log[-4000:])
            sys.exit('xelab failed')
        stamp.write_text(fingerprint + '\n')
        print('built', args.top)

    cmd = [exe / 'xsim.exe', args.top + '_snap', '-runall', '-log', 'xsim.log']
    for a in args.plusargs:
        cmd += ['-testplusarg', a]
    p, log = run(cmd)
    tail = [l for l in log.splitlines() if any(marker in l for marker in
            ('PASS', 'FAIL', 'Fatal', 'Error', 'IDCODE', 'JTAG_WR_', 'JTAG_BLK_', 'JTAG_PKT_'))]
    print('\n'.join(tail[-20:]) or log[-2000:])
    # Successful coverage messages include "sticky-error fence/drop". Only
    # diagnostic lines starting with a failure marker denote simulation errors.
    failed = re.search(r'^\s*(?:Fatal|Error|FAIL)\b', log, re.IGNORECASE | re.MULTILINE)
    return 0 if p.returncode == 0 and 'PASS' in log and not failed else 1


if __name__ == '__main__':
    raise SystemExit(main())
