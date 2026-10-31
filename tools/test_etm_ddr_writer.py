"""Offline AXI write/abort/backpressure regression; no DDR or board claim."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    files=[ROOT/'fpga/rtl/orbtrace_ddr_writer.v',ROOT/'fpga/sim/tb_orbtrace_ddr_writer.sv'];exe=out/'writer.vvp'
    c=subprocess.run(['iverilog','-g2012','-s','tb_orbtrace_ddr_writer','-o',str(exe),*[str(f) for f in files]],capture_output=True,text=True)
    (out/'compile.txt').write_text(c.stdout+c.stderr,encoding='utf8')
    if c.returncode:raise RuntimeError(c.stderr)
    r=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=60)
    (out/'simulation.txt').write_text(r.stdout+r.stderr,encoding='utf8')
    if r.returncode or 'PASS ALL DDR writer cases=92' not in r.stdout:raise RuntimeError(r.stdout+r.stderr)
    controller=ROOT/'fpga/rtl/orbtrace_ddr_controller.v';bench=ROOT/'fpga/sim/tb_orbtrace_ddr_controller.sv'
    controller_exe=out/'controller.vvp';files.extend([controller,bench])
    c=subprocess.run(['iverilog','-g2012','-s','tb_orbtrace_ddr_controller','-o',str(controller_exe),*[str(f) for f in files if f.suffix=='.v' or f==bench]],capture_output=True,text=True)
    (out/'controller-compile.txt').write_text(c.stdout+c.stderr,encoding='utf8')
    if c.returncode:raise RuntimeError(c.stderr)
    check=subprocess.run(['vvp',str(controller_exe)],capture_output=True,text=True,timeout=60)
    (out/'controller-simulation.txt').write_text(check.stdout+check.stderr,encoding='utf8')
    if check.returncode or 'PASS DDR controller' not in check.stdout:raise RuntimeError(check.stdout+check.stderr)
    report=dict(passed=True,hardwareAccess=False,actualDdrReadback=False,cases=92,repeatedCapturesWithoutReset=64,
        scope='AXI channel stability, B-response completion, byte limits, 4KiB boundaries, partial WSTRB, ping-pong stalls, errors, empty input and draining abort',
        sources={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    report['controllerRegressionPassed']=True
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(r.stdout+check.stdout)


if __name__=='__main__':main()
