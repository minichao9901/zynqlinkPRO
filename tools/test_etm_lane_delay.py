"""Offline per-lane IDELAY transaction and full RAW4-to-DDR regression."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[*sorted((ROOT/'fpga/rtl').glob('orbtrace_*.v')),ROOT/'fpga/sim/sim_primitives.v',
             ROOT/'fpga/sim/tb_orbtrace_lane_delay.sv',ROOT/'fpga/sim/tb_orbtrace_lane_sampling.sv',ROOT/'fpga/sim/tb_orbtrace_ddr_trace.sv']
    cases=[]
    source_sha={s.relative_to(ROOT).as_posix():hashlib.sha256(s.read_bytes()).hexdigest() for s in sources}
    for name,top,params,expected in [
        ('delay','tb_orbtrace_lane_delay',[],'PASS lane delay:'),
        ('pins-skew','tb_orbtrace_lane_sampling',[],'PASS lane sampling:'),
        ('ddr-bypass','tb_orbtrace_ddr_trace',[],'PASS DDR trace integration cases=9'),
        ('ddr-delay','tb_orbtrace_ddr_trace',['-Ptb_orbtrace_ddr_trace.LANE_DELAY=1'],'PASS DDR trace integration cases=9'),
        ('ddr-fixed-region','tb_orbtrace_ddr_trace',['-Ptb_orbtrace_ddr_trace.LANE_DELAY=1','-Ptb_orbtrace_ddr_trace.FIXED_BYTES=8192'],'PASS DDR trace integration cases=9')]:
        exe=out/(name+'.vvp')
        compile=subprocess.run(['iverilog','-g2012','-s',top,*params,'-o',str(exe),*[str(s) for s in sources]],capture_output=True,text=True)
        (out/(name+'-compile.txt')).write_text(compile.stdout+compile.stderr,encoding='utf8')
        if compile.returncode:raise RuntimeError(compile.stderr)
        run=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=60)
        (out/(name+'.txt')).write_text(run.stdout+run.stderr,encoding='utf8')
        if run.returncode or expected not in run.stdout:raise RuntimeError(run.stdout+run.stderr)
        cases.append(name);print(run.stdout.strip(),flush=True)
    if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in source_sha.items()):raise RuntimeError('Sources changed during simulation')
    (out/'result.json').write_text(json.dumps(dict(passed=True,hardwareAccess=False,cases=cases,
        note='Functional delay and protocol model; not analog signal integrity or routed STA',
        sources=source_sha),indent=2)+'\n',encoding='utf8')


if __name__=='__main__':main()
