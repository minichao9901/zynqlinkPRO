"""Offline integrated RAW4 pins -> hardware window -> framed DDR write checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    files=[*sorted((ROOT/'fpga/rtl').glob('orbtrace_*.v')),ROOT/'fpga/sim/sim_primitives.v',ROOT/'fpga/sim/tb_orbtrace_ddr_trace.sv']
    exe=out/'trace.vvp'
    compile=subprocess.run(['iverilog','-g2012','-s','tb_orbtrace_ddr_trace','-o',str(exe),*[str(f) for f in files]],capture_output=True,text=True)
    (out/'compile.txt').write_text(compile.stdout+compile.stderr,encoding='utf8')
    if compile.returncode:raise RuntimeError(compile.stderr)
    run=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=60)
    (out/'simulation.txt').write_text(run.stdout+run.stderr,encoding='utf8')
    if run.returncode or 'PASS DDR trace integration cases=9' not in run.stdout:raise RuntimeError(run.stdout+run.stderr)
    report=dict(passed=True,hardwareAccess=False,integratedCases=9,
        checks=['RAW4 physical pin model and normalized formatter bytes','exact reference tick window','full frames plus partial tail',
                'capture nonce frozen independently of next configuration','legacy reset cannot clear DDR source',
                'capacity stop and FIFO EOF drain','manual stop with target clock stopped','empty source cannot reuse data',
                'no completion before final DDR B response','FIFO overflow is counted and failed','failed B is not committed bytes',
                'bounded preparation failure and cancel before source arm'],
        sources={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(run.stdout)


if __name__=='__main__':main()
