"""Real Web CDC full-window u32 integrity with 13-byte target publications.

Requires hpm6800_usb_fixture install, a verified idle probe and live page worker.
The control thread only toggles the RAM producer via serialized DAP handoffs;
it never issues a second page job while captureWindow is executing.
"""
import argparse,json,subprocess,threading,time,struct,hashlib,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.validate_hpm6800_web import Web

def sequence(data):
    words,tail=divmod(len(data),4)
    expected=np.arange(words,dtype='<u4').tobytes()+struct.pack('<I',words)[:tail]
    mismatch=np.flatnonzero(np.frombuffer(data,dtype='u1')!=np.frombuffer(expected,dtype='u1'))
    first=int(mismatch[0])if len(mismatch)else None
    return dict(sequenceExact=bool(data)and not len(mismatch),bytes=len(data),mismatchedBytes=len(mismatch),firstMismatch=first,
        actualAtFirst=data[first:first+32].hex()if first is not None else None,
        expectedAtFirst=expected[first:first+32].hex()if first is not None else None,
        sha256=hashlib.sha256(data).hexdigest(),expected_sha256=hashlib.sha256(expected).hexdigest())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',required=True);p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--batches',default='4,13,127,2048');p.add_argument('--seconds',type=float,default=6)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);report=dict(rows=[],phase='running')
    def save():(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    def control(action,batch=13):
        r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/hpm6800_usb_fixture.py'),action,'--state',str(a.fixture),'--batch',str(batch)],capture_output=True,text=True,timeout=20)
        assert r.returncode==0,(r.stdout,r.stderr)
        return json.loads(r.stdout)if action=='stop'else r.stdout
    for i,batch in enumerate(map(int,a.batches.split(','))):
        control('reset',batch);row=dict(batch=batch,passed=False);report['rows'].append(row);save()
        class SequenceWeb(Web):
            worker=None
            def invoke(self,p,m,*args,**kw):
                if p=='rttcdc'and m=='captureWindow':
                    def produce():
                        try:
                            time.sleep(.5);control('start');time.sleep(a.seconds);row['producer']=control('stop')
                        except BaseException as e:row['controlError']=repr(e)
                    self.worker=threading.Thread(target=produce);self.worker.start()
                return super().invoke(p,m,*args,**kw)
        args=SimpleNamespace(runtime=a.runtime,out=a.out/f'{i:02d}-batch{batch}',timeout=240,elf=a.fixture/'producer.elf',seconds=a.seconds+4,live=False)
        w=SequenceWeb(args)
        def check(data):row['integrity']=sequence(data);return row['integrity']['sequenceExact']
        try:
            row['web']=w.rttcdc(pattern_check=check)
            assert row['integrity']['bytes']==row['producer']['published_bytes'],('Target/window total mismatch',row)
            assert row['web']['engine']['moved']==row['producer']['published_bytes'],('RTT target tail not drained',row)
            row['passed']=True
        except BaseException as e:row['error']=repr(e)
        finally:
            if w.worker:w.worker.join(25);assert not w.worker.is_alive()
            row['stopped']=control('stop');save()
        print(batch,'PASS'if row['passed']else'FAIL',row.get('integrity'),flush=True)
    report.update(phase='completed',passed=all(r['passed']for r in report['rows']));save()
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
