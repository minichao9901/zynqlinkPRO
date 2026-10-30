"""Run restored continuous-producer RTT tests for both transports."""
from pathlib import Path
import argparse,subprocess,sys,json
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
p.add_argument('--seconds',type=float,default=2);p.add_argument('--repeats',type=int,default=3)
p.add_argument('--speeds',default='1000000,10000000,25000000,35000000,50000000,60000000',
               help='Comma-separated requested link rates in Hz')
a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True);rows=[]
speeds=[int(v) for v in a.speeds.split(',')]
if not speeds or any(v<=0 for v in speeds):p.error('--speeds must contain positive rates in Hz')
for tr in ['swd','jtag']:
 for speed in speeds:
  mhz=speed//1000000 if speed%1000000==0 else speed/1000000
  dest=out/f'rtt_{tr}_{mhz}.json'
  cmd=[sys.executable,'tools/benchmark_rtt_forward.py','--transport',tr,'--speeds',str(speed),'--chunks','1024','--seconds',str(a.seconds),'--repeats',str(a.repeats),'--bit',str(a.bit.resolve()),'--elf',str(a.elf.resolve()),'--output',str(dest)]
  result=subprocess.run(cmd,cwd=r,capture_output=True,text=True,errors='replace',timeout=120)
  dest.with_suffix('.log').write_text(result.stdout+result.stderr)
  rows.append(dict(transport=tr,requested_MHz=mhz,returncode=result.returncode,file=dest.name))
  (out/'runs.json').write_text(json.dumps(rows,indent=2))
  print(tr,mhz,'PASS' if result.returncode==0 else 'FAIL',(result.stdout+result.stderr)[-220:] if result.returncode else '',flush=True)
  if dest.exists() and not json.loads(dest.read_text()).get('restore_match',False):
   raise RuntimeError('Restoration was not verified; stop before another fixture overwrites its backup')
raise SystemExit(any(v['returncode'] for v in rows))
