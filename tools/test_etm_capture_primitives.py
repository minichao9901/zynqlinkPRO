"""Offline bounded-window/async-frame bridge checks; not integrated board capture."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    files=[ROOT/'fpga/experiments/etm_ddr'/n for n in ['etm_ref_window.v','etm_frame_async_fifo.v','tb_etm_capture_primitives.sv']]
    variants=[]
    for address_bits,frames in [(3,1028),(9,2597)]:
        exe=out/f'primitives-{address_bits}.vvp'
        c=subprocess.run(['iverilog','-g2012','-s','tb_etm_capture_primitives',f'-Ptb_etm_capture_primitives.FIFO_ADDR={address_bits}','-o',str(exe),*[str(f) for f in files]],capture_output=True,text=True)
        (out/f'compile-{address_bits}.txt').write_text(c.stdout+c.stderr,encoding='utf8')
        if c.returncode:raise RuntimeError(c.stderr)
        r=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=60)
        (out/f'simulation-{address_bits}.txt').write_text(r.stdout+r.stderr,encoding='utf8')
        if r.returncode or f'PASS reference windows=12; async frames={frames}' not in r.stdout:raise RuntimeError(r.stdout+r.stderr)
        variants.append(dict(depth=1<<address_bits,windowCases=12,acceptedFrameChecks=frames));print(r.stdout)
    report=dict(passed=True,hardwareAccess=False,productionIntegration=False,variants=variants,
        note='Reference-domain command primitive only; owner CDC handshake, source stop acknowledgement, partial frame flush and AXI completion integration remain required.',
        sources={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
