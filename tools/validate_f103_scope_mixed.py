"""Real F103 scope mixed scalars, unaligned reads, CSV and offline replay."""
from pathlib import Path
from types import SimpleNamespace
import sys,struct,json,time,csv,io,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from validate_f103_main_web import Web
from f103_ram_fixture import Fixture
from benchmark_web_cli_25 import validate_hss
from toolbox import pack_file
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',required=True,type=Path);p.add_argument('--runtime',required=True)
p.add_argument('--execute',action='store_true');args=p.parse_args()
if not args.execute:print(json.dumps(dict(hardwareAccess=False)));raise SystemExit(0)
out=args.out
w=Web(SimpleNamespace(runtime=args.runtime,artifacts=out,case_timeout=180))
fields=[('i8',0x21,'b',-77),('f64',0x101,'d',123.456),('u8',0x300,'B',211),('u16',0x304,'H',48350),('u32',0x3ff,'I',0x89abcdef),('f32',0x580,'f',.25),('i16',0x6ff,'h',-23456),('i32',0x7fd,'i',-123456789)]
pattern=bytearray(4096)
for scalar,offset,fmt,value in fields:struct.pack_into('<'+fmt,pattern,offset,value)
expected=b''.join(pattern[offset:offset+struct.calcsize('<'+fmt)] for _,offset,fmt,_ in fields)
report=dict(passed=False)
try:
 with Fixture(out/'fixture') as f:
  f.prepare_hss(bytes(pattern));w.page('scope','show');w.page('scope','describe')
  w.set('scope','#sc-mock',False);w.set('scope','#sc-target','swd');w.set('scope','#sc-clock','60000')
  w.invoke('scope','connectHid',False);w.invoke('scope','connectUsb',False)
  w.set('scope','#sc-period','1000');w.set('scope','#sc-seconds','10');w.set('scope','#sc-raw',True)
  w.set('scope','#sc-batch',True);w.set('scope','#sc-cdcoff',True);w.page('scope','click',selector='#sc-varclear')
  for scalar,offset,fmt,value in fields:w.invoke('scope','toggleVar',dict(name='mixed.'+scalar,addr=0x20004000+offset,size=struct.calcsize('<'+fmt),scalar=scalar,scale=1,offset=0),True)
  try:
   w.invoke('scope','start');assert w.invoke('scope','summary')['running'];time.sleep(3)
   w.invoke('scope','stop','mixed scalar acceptance');end=w.invoke('scope','summary')
   w.invoke('scope','saveRaw');raw=w.download('scope',out/'mixed.jsp');reader,versions=validate_hss(raw,expected,24000)
   assert reader.samples==end['receivedSamples']==end['probeMetrics']['produced']
   assert not any(end.get(k)for k in ['lostUsb','lostGap','readErrors','metricsError'])
   w.invoke('scope','exportCsv');body=w.download('scope',out/'mixed.csv')
   rows=list(csv.DictReader(io.StringIO(body.decode('utf8'))));assert len(rows)==reader.samples
   for row in rows:
    for scalar,offset,fmt,value in fields:assert float(row['mixed.'+scalar])==value,(scalar,row['mixed.'+scalar],value)
   report.update(summary=end,samples=reader.samples,allRawValuesExact=True,allCsvValuesExact=True,protocolVersions=versions)
   w.invoke('scope','zoomToPoints',500);report['zoom']=w.invoke('scope','summary')['view']
   w.set('scope','#sc-trig-mode','1');w.set('scope','#sc-trig-ch','0');w.set('scope','#sc-trig-level','0')
   w.invoke('scope','applyTrigger');w.invoke('scope','findNextTrigger');report['trigger']=w.invoke('scope','summary')['trigger'];assert report['trigger']['hit']==-1
  finally:w.invoke('scope','stop','cleanup');w.invoke('scope','disconnect')
 w.page('scope','upload',selector='@file:view.jspInput',files=[pack_file(out/'mixed.jsp')])
 deadline=time.monotonic()+10
 while time.monotonic()<deadline:
  replay=w.invoke('scope','summary')
  if replay['state'].startswith('回放完成') and replay['samples']==report['samples']:break
  time.sleep(.05)
 assert replay['samples']==report['samples'] and replay['state'].startswith('回放完成'),replay
 assert not any(replay.get(k)for k in ['lostUsb','lostGap','readErrors','lost'])
 report['replay']=replay;report['passed']=True
finally:w.save(out/'result.json',report)
print('Mixed 8 scalar types / unaligned values / CSV / zoom / trigger / replay:',report['passed'])
