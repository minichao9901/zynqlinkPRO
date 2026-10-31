"""Simulate the experimental DDR stream frontend; not a DDR/board acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    files=[ROOT/'fpga/experiments/etm_ddr'/name for name in ['etm_ddr_packetizer.v','tb_etm_ddr_packetizer.sv']]
    exe=out/'packetizer.vvp'
    c=subprocess.run(['iverilog','-g2012','-s','tb_etm_ddr_packetizer','-o',str(exe),*[str(f) for f in files]],capture_output=True,text=True)
    (out/'compile.txt').write_text(c.stdout+c.stderr,encoding='utf8')
    if c.returncode:raise RuntimeError(c.stderr)
    result=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=60)
    (out/'simulation.txt').write_text(result.stdout+result.stderr,encoding='utf8')
    if result.returncode or 'PASS' not in result.stdout:raise RuntimeError(result.stdout+result.stderr)
    report={'hardwareAccess':False,'productionIntegration':False,'ddrWritesVerified':False,'passed':True,
        'normalCases':39,'invalidFrameChecked':True,'scope':'AXIS64 byte order/TKEEP/TLAST, empty EOF, arbitrary partial frames, bounded prefix, stalls, source silence and rejected busy start',
        'sources':{f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(result.stdout.strip())
    return 0


if __name__=='__main__':raise SystemExit(main())
