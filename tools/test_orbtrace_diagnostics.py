"""Offline RTL diagnostics and legacy trace regression; no board access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    rtl=sorted((ROOT/'fpga/rtl').glob('orbtrace_*.v'));rows=[]
    for top in ('tb_orbtrace_diagnostics','tb_orbtrace_controller','tb_orbtrace_tpiu_stream','tb_orbtrace_parallel','tb_orbtrace_raw','tb_orbtrace_samples'):
        executable=out/(top+'.vvp')
        command=['iverilog','-g2012','-s',top,'-o',str(executable),*[str(f) for f in rtl],str(ROOT/'fpga/sim/sim_primitives.v'),str(ROOT/'fpga/sim'/(top+'.sv'))]
        c=subprocess.run(command,capture_output=True,text=True)
        (out/(top+'-compile.txt')).write_text(c.stdout+c.stderr,encoding='utf8')
        if c.returncode:raise RuntimeError(c.stderr)
        variants=[[]]
        if top=='tb_orbtrace_parallel':variants=[[f'+pins={pins}',f'+phase={phase}'] for pins in (1,2,4) for phase in (0,1)]
        for n,extra in enumerate(variants):
            result=subprocess.run(['vvp',str(executable),*extra],capture_output=True,text=True,timeout=60)
            (out/(top+f'-{n}.txt')).write_text(result.stdout+result.stderr,encoding='utf8')
            if result.returncode or 'PASS' not in result.stdout:raise RuntimeError(top+': '+result.stdout+result.stderr)
            rows.append({'top':top,'arguments':extra,'passed':True});print(result.stdout.strip(),flush=True)
    report={'hardwareAccess':False,'tests':rows,'rtlSha256':{f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in rtl}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    return 0


if __name__=='__main__':raise SystemExit(main())
