import argparse,subprocess,sys,json,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True);p.add_argument('--speeds',default='50000,60000');p.add_argument('--phase',choices=['peak_rtt','hss'],default='peak_rtt');a=p.parse_args();root=Path.cwd();dest=root/'docs/validation/orbtrace-sota-20261031'/a.label;dest.mkdir(parents=True,exist_ok=True);art=['--bit',str(a.bit.resolve()),'--elf',str(a.elf.resolve())];os.environ['TEMP']=os.environ['TMP']=str(root/'build/probe_tmp');jobs=[];rows=[]
if a.phase=='peak_rtt':
 for tr in ['swd','jtag']:
  for speed in [int(x) for x in a.speeds.split(',')]:
   extra=['tools/h743_peak.py','--transport',tr,'--jtag-ir','4,5','--speed',str(speed),'--address','0x20008000','--words','512','--depth','32','--loops','256','--repeats','3',*art]
   if tr=='swd' and speed==60000:extra+=['--soak-seconds','30']
   jobs.append((f'peak_{tr}_{speed}',extra))
 for tr in ['swd','jtag']:
  for speed in [int(x)*1000 for x in a.speeds.split(',')]:jobs.append((f'rtt_{tr}_{speed}',['tools/benchmark_rtt_forward.py','--transport',tr,'--speeds',str(speed),'--chunks','2048','--seconds','3','--repeats','2',*art]))
else:
 points=[('swd',50000000,1,'24'),('swd',60000000,1,'24'),('swd',50000000,8,'236'),('swd',60000000,8,'197,195'),('jtag',50000000,1,'89,60'),('jtag',60000000,1,'74,40'),('jtag',50000000,8,'529,527'),('jtag',60000000,8,'442,441,411')]
 for tr,speed,nvars,periods in points:jobs.append((f'hss_{tr}_{speed}_{nvars}',['tools/benchmark_probe_stream.py','--transport',tr,'--speeds',str(speed),'--variables',str(nvars),'--periods',periods,'--seconds','2','--repeats','3',*art]))
for name,extra in jobs:
 out=dest/(name+'.json');cmd=[sys.executable,'-X','utf8',*extra,'--output',str(out)]
 with out.with_suffix('.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 v=json.loads(out.read_text()) if out.exists() else {};passed=r.returncode==0 and v.get('passed',True) and not v.get('recover_error');row=dict(name=name,command=cmd,returncode=r.returncode,passed=passed,restore_match=v.get('restore_match'),error=v.get('error',v.get('failure')));rows.append(row);(dest/(a.phase+'_runs.json')).write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps({k:v for k,v in row.items() if k!='command'}),flush=True)
 if v.get('backup_sha256') or v.get('rows') or name.startswith('peak'):assert v.get('restore_match'),'RAM restoration not verified'
 if not passed:raise RuntimeError('SOTA case failed; preserve raw data and investigate before next case')
