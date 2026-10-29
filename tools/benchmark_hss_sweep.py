"""Run independently restored adaptive HSS sweeps for both protocols."""
import argparse,subprocess,sys,json,hashlib
from pathlib import Path
r=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
p.add_argument('--resume',action='store_true');a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
hashes={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('bit',a.bit),('elf',a.elf)]};rows=[]
for transport in ['swd','jtag']:
 for mhz in [1,10,25,35,50,60]:
  dest=out/f'hss_{transport}_{mhz}.json';cached=False
  if a.resume and dest.exists():
   d=json.loads(dest.read_text());cached=d.get('restore_match') and len(d.get('summary',[]))==1 and not d.get('failure') and all(d['artifacts'][k]['sha256']==v for k,v in hashes.items())
  if cached:rc=0
  else:
   result=subprocess.run([sys.executable,'tools/benchmark_hss_matrix.py','--transports',transport,'--speeds',str(mhz*1000000),'--output',str(dest),'--bit',str(a.bit.resolve()),'--elf',str(a.elf.resolve())],cwd=r,capture_output=True,text=True,errors='replace',timeout=300)
   dest.with_suffix('.log').write_text(result.stdout+result.stderr);rc=result.returncode
  rows.append(dict(transport=transport,requested_MHz=mhz,returncode=rc,file=dest.name,cached=bool(cached)))
  (out/'hss_runs.json').write_text(json.dumps(rows,indent=2))
  print(transport,mhz,'PASS' if rc==0 else 'FAIL',flush=True)
  if dest.exists() and not json.loads(dest.read_text()).get('restore_match',False):raise RuntimeError('HSS restore failed; preserve backup and stop')
raise SystemExit(any(v['returncode'] for v in rows))
