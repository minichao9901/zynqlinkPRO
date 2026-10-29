"""Run restored continuous-producer RTT tests for both transports."""
from pathlib import Path
import argparse,subprocess,sys,json
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
p.add_argument('--seconds',type=float,default=2);p.add_argument('--repeats',type=int,default=3)
a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True);rows=[]
for tr in ['swd','jtag']:
 for mhz in [1,10,25,35,50,60]:
  dest=out/f'rtt_{tr}_{mhz}.json'
  cmd=[sys.executable,'tools/benchmark_rtt_forward.py','--transport',tr,'--speeds',str(mhz*1000000),'--chunks','1024','--seconds',str(a.seconds),'--repeats',str(a.repeats),'--bit',str(a.bit.resolve()),'--elf',str(a.elf.resolve()),'--output',str(dest)]
  result=subprocess.run(cmd,cwd=r,capture_output=True,text=True,errors='replace',timeout=120)
  dest.with_suffix('.log').write_text(result.stdout+result.stderr)
  rows.append(dict(transport=tr,requested_MHz=mhz,returncode=result.returncode,file=dest.name))
  (out/'runs.json').write_text(json.dumps(rows,indent=2))
  print(tr,mhz,'PASS' if result.returncode==0 else 'FAIL',(result.stdout+result.stderr)[-220:] if result.returncode else '',flush=True)
  if dest.exists() and not json.loads(dest.read_text()).get('restore_match',False):
   raise RuntimeError('Restoration was not verified; stop before another fixture overwrites its backup')
raise SystemExit(any(v['returncode'] for v in rows))
