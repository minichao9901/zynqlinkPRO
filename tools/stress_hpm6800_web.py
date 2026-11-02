"""Seeded real-Web HPM handoffs: live Scope/RTT/CDC/debug and target flashing.

Every image change uses the actual Web flasher. No hidden browser evaluation.
Fails remain in the report; known missing-DEF failures do not become passes.
"""
import argparse,json,random,time,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.validate_hpm6800_web import Web
from toolbox import Client

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--rounds',type=int,default=6);p.add_argument('--seed',type=int,default=680020261102)
    p.add_argument('--initial-firmware',choices=('scope','rtt_flood','dbgstress'),default='dbgstress')
    a=p.parse_args()
    if not 1<=a.rounds<=20:p.error('rounds must be 1..20')
    client=Client(a.runtime,15)
    ready=client.request(dict(action='ping'));client.http('ack/'+ready['job'],{})
    if not ready.get('ok'):raise RuntimeError('Browser worker is not ready; no hardware action started')
    a.out.mkdir(parents=True,exist_ok=False)
    rng=random.Random(a.seed);plan=[]
    for _ in range(a.rounds):
        block=['scope','rtt','rttcdc','debug'];rng.shuffle(block);plan+=block
    report=dict(seed=a.seed,plan=plan,steps=[],started=time.time(),flash_writes_authorized=True)
    def save():(a.out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def args(out,elf,live):return SimpleNamespace(runtime=a.runtime,out=out,timeout=240,elf=elf,clock='',repeats=3,seconds=2,period=1000,channels=8,live=live,allow_cdc=True)
    firmware=a.initial_firmware;previous=None
    def status(w):
        result={}
        for page in ('scope','rtt','dbg'):
            result[page]=w.invoke(page,'summary')
        result['rttcdc']=w.invoke('rttcdc','summary',target='hid');return result
    try:
        for index,kind in enumerate(plan):
            wanted='scope' if kind=='scope' else 'dbgstress' if kind=='debug' else 'rtt_flood'
            elf=ROOT/'firmware/target/hpm6800_web_validation'/wanted/'fw.elf'
            row=dict(step=index+1,kind=kind,firmwareBefore=firmware,passed=False,started=time.time());report['steps'].append(row);save()
            if wanted!=firmware:
                f=Web(args(a.out/f'{index+1:02d}-flash-{wanted}',elf,False));f.a.repeats=1
                row['flash']=f.flash();assert row['flash']['passed'];firmware=wanted;save()
            w=Web(args(a.out/f'{index+1:02d}-{kind}',elf,True))
            if previous==kind:
                if kind=='scope':w.invoke('scope','stop','explicit restart');w.invoke('scope','disconnect')
                elif kind=='rtt':w.invoke('rtt','disconnect')
                elif kind=='rttcdc':
                    w.invoke('rttcdc','stop',target='hid');w.invoke('rttcdc','disconnect',target='hid');w.invoke('rttcdc','close',target='session')
                else:w.invoke('dbg','bpClear',target='session');w.invoke('dbg','run',target='session');w.invoke('dbg','disconnect')
            # Record the previous feature's final state AFTER a natural handoff.
            try:
                row['operation']=getattr(w,kind)();row['after']=status(w)
                assert row['operation']['passed']
                if previous=='scope' and kind!='scope':
                    s=row['after']['scope'];assert not s['running'] and s.get('tailCountDelta')==0,('Scope handoff incomplete',s)
                row['passed']=True
            except BaseException as error:
                row['error']=repr(error)
                try:row['after']=status(w)
                except BaseException as state_error:row['state_error']=repr(state_error)
                if '无法确认' in str(error) or '操作可能仍在执行' in str(error):
                    save();raise
            row.update(seconds=time.time()-row['started'],firmwareAfter=firmware);save()
            print(index+1,kind,'PASS' if row['passed'] else 'FAIL',round(row['seconds'],2),flush=True)
            previous=kind if row['passed'] else None
    finally:
        # Cleanup uses only this workbench's feature owners, no external server.
        cleaner=Web(args(a.out/'cleanup',ROOT/'firmware/target/hpm6800_web_validation'/firmware/'fw.elf',False))
        errors=[]
        before_cleanup=status(cleaner)
        cleanup=[('scope','stop','view'),('scope','disconnect','view'),('rtt','disconnect','view'),
            ('rttcdc','stop','hid'),('rttcdc','disconnect','hid'),('rttcdc','close','session')]
        if before_cleanup['dbg']['connected']:cleanup += [('dbg','bpClear','session'),('dbg','run','session'),('dbg','disconnect','view')]
        for page,method,target in cleanup:
            try:cleaner.invoke(page,method,target=target)
            except BaseException as e:errors.append(dict(page=page,method=method,error=repr(e)))
        report.update(finished=time.time(),firmware=firmware,cleanupErrors=errors,final=status(cleaner),
            passed=len(report['steps'])==len(plan) and all(s['passed'] for s in report['steps']))
        save()
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
