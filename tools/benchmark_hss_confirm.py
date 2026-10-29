"""Confirm selected HSS frontier/peak points after an interrupted sweep."""
import argparse,json,hashlib,math
from pathlib import Path
import usb.util
from dap_pipeline_bench import open_dap,setup
from probe_stream import Probe
from test_probe_board import Memory,stop
from test_swd_lowfreq_board import recover
from benchmark_probe_stream import hss_point
from probe_build_info import provenance

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--speed',type=int,required=True);p.add_argument('--periods',required=True)
 p.add_argument('--transport',choices=['swd','jtag'],default='jtag')
 p.add_argument('--output',type=Path,required=True);p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
 a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
 d,o,i=open_dap();probe=Probe();m=Memory(o,i);saved=initial=None
 report=dict(artifacts=provenance(a.bit,a.elf),transport=a.transport,requested_Hz=a.speed,rows=[])
 def save():a.output.write_text(json.dumps(report,indent=2)+'\n')
 try:
  stop(probe,d);setup(o,i,50000,'swd');initial=m.word(0xe000edf0)
  if not initial&(1<<17):m.write_word(0xe000edf0,0xa05f0003)
  saved=m.read(0x20004000,4096);a.output.with_suffix('.backup.bin').write_bytes(saved)
  report['backup_sha256']=hashlib.sha256(saved).hexdigest()
  report['RCC_before']=[m.word(0x40021000),m.word(0x40021004)]
  assert probe.action(0x31,12,bytes([1 if a.transport=='swd' else 2]))[0]==0
  for period in map(int,a.periods.split(',')):
   for repeat in range(3):
    row=dict(transport=a.transport,speed_hz=a.speed,period_ticks=period,repeat=repeat,passed=False)
    try:
     setup(o,i,50000,'swd')
     measured=hss_point(probe,m,d,a.speed,period,1,2,repeat,True,lambda:setup(o,i,50000,a.transport),True)
     row.update(measured,passed=True)
    except Exception as exc:
     row.update(getattr(exc,'measurement',{}))
     row['error']=repr(exc)
     try:stop(probe,d)
     except Exception:recover(d,i);stop(probe,d)
    finally:
     setup(o,i,50000,'swd');m.write(0x20004000,saved)
     row['restore_match']=m.read(0x20004000,4096)==saved;assert row['restore_match']
     report['rows'].append(row);save();print(json.dumps({k:v for k,v in row.items() if k not in ('m0','m1','final')}),flush=True)
  report['RCC_after']=[m.word(0x40021000),m.word(0x40021004)];assert report['RCC_before']==report['RCC_after']
 finally:
  try:
   try:stop(probe,d)
   except RuntimeError:recover(d,i);stop(probe,d)
   setup(o,i,50000,'swd')
   if saved is not None:m.write(0x20004000,saved);report['restore_match']=m.read(0x20004000,4096)==saved;assert report['restore_match']
   if initial is not None and not initial&(1<<17):m.write_word(0xe000edf0,0xa05f0001)
  finally:save();probe.close();usb.util.release_interface(d,0);usb.util.dispose_resources(d)

if __name__=='__main__':main()
