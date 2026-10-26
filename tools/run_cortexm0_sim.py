"""Run XSim against the user's local Cortex-M0 DesignStart model.

ARM files stay outside this repository. --build compiles/elaborates with
Vivado; subsequent invocations reuse the snapshot. Success requires a test
PASS marker; XSim's process exit status alone is not a verification result.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pefile

ROOT = Path(__file__).resolve().parents[1]
VIVADO = Path(r'E:/Xilinx/Vivado/2018.3')
WORK = ROOT / 'build/cortexm0_sim/cortexm0_sim.sim/sim_1/behav/xsim'
SNAPSHOT = 'tb_cortexm0_link_behav'


def environment():
    v = VIVADO
    paths = [v/'lib/win64.o', v/'bin/unwrapped/win64.o',
             v/'bin/unwrapped/win64.o/Microsoft.VC140.CRT', v/'tps/win64',
             v/'tps/win64/jre9.0.4/bin/server', v/'tps/win64/jre9.0.4/bin']
    env = os.environ.copy()
    env['PATH'] = os.pathsep.join(map(str, paths)) + os.pathsep + env['PATH']
    env.update(XILINX_VIVADO=v.as_posix(), RDI_APPROOT=v.as_posix(), HDI_APPROOT=v.as_posix(),
               RDI_BINROOT=(v/'bin').as_posix(), RDI_PLATFORM='win64', RDI_OPT_EXT='.o',
               RDI_DATADIR=(v/'data').as_posix(),
               RDI_BINDIR=(v/'bin').as_posix(),
               RDI_LIBDIR=(v/'lib/win64.o').as_posix(),
               TCL_LIBRARY=(v/'tps/tcl/tcl8.5').as_posix())
    return env, paths


def prepare_kernel(paths):
    dest = WORK / 'xsim.dir' / SNAPSHOT
    seen = set()

    def copydeps(p):
        if p.name.lower() in seen:
            return
        seen.add(p.name.lower())
        pe = pefile.PE(str(p), fast_load=True)
        pe.parse_data_directories(directories=[1])
        for imp in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
            name = imp.dll.decode()
            q = next((d/name for d in paths if (d/name).is_file()), None)
            if q:
                if not (dest/name).exists():
                    shutil.copy2(q, dest/name)
                copydeps(q)
        pe.close()
    copydeps(dest/'xsimk.exe')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--model-dir', default='')
    ap.add_argument('--tag', default='baseline')
    ap.add_argument('plusargs', nargs='*')
    args = ap.parse_args()
    # XSim silently accepts misspelled plusargs. Reject them here so a requested
    # delay sweep cannot accidentally rerun the default target timing.
    flags = {'packets', 'errors', 'trace', 'vcd', 'recovery'}
    values = {'half_ns', 'return_ns', 'phase', 'ack_delay', 'turn_extra', 'words', 'idle'}
    for arg in args.plusargs:
        name, sep, value = arg.lstrip('+').partition('=')
        if (sep and name not in values) or (not sep and name not in flags):
            ap.error(f'Unknown testbench plusarg: {arg}')
    if args.build:
        cmd = [sys.executable, str(ROOT/'tools/run_vivado.py'), '-mode', 'batch',
               '-nojournal', '-log', str(ROOT/'build/cortexm0_sim.log'),
               '-source', str(ROOT/'fpga/sim/run_cortexm0.tcl')]
        if args.model_dir:
            cmd += ['-tclargs', args.model_dir]
        subprocess.run(cmd, cwd=ROOT, check=True)
    env, paths = environment()
    prepare_kernel(paths)
    out = ROOT/'results/optimization/cortexm0_sim'
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(VIVADO/'bin/unwrapped/win64.o/xsim.exe'), SNAPSHOT, '-runall', '-log', str(out/f'{args.tag}.xsim.log')]
    for arg in args.plusargs:
        cmd += ['-testplusarg', arg.lstrip('+')]
    p = subprocess.run(cmd, cwd=WORK, env=env, capture_output=True, text=True,
                       errors='replace', timeout=900)
    log = p.stdout+p.stderr
    (out/f'{args.tag}.log').write_text(log, encoding='utf-8')
    ok = p.returncode == 0 and 'PASS CortexM0' in log and 'Fatal:' not in log
    (out/f'{args.tag}.json').write_text(json.dumps(
        dict(passed=ok, returncode=p.returncode, plusargs=args.plusargs), indent=2))
    print(log[-6000:])
    if not ok:
        raise SystemExit(f'CortexM0 verification failed: {out/args.tag}')


if __name__ == '__main__':
    main()
