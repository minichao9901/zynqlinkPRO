"""Finite native CLI ETM E2E using exactly the real-Web CDC Echo producer."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.stress_etm_web import Echo

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--pair',type=Path,default=ROOT/'prebuilt/fclk133-release-20261101')
    p.add_argument('--elf',type=Path,default=ROOT/'prebuilt/golden/f103ze-cdc48.elf')
    p.add_argument('--port',default='COM34');p.add_argument('--seconds',type=float,default=1)
    p.add_argument('--rounds',type=int,default=3);p.add_argument('--execute',action='store_true')
    p.add_argument('--toolbox',type=Path,default=ROOT/'toolbox.py',help='Explicit fixed historical entry for controlled comparison')
    a=p.parse_args()
    if not a.execute:print(json.dumps(dict(hardwareAccess=False)));return
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False);report=dict(rows=[],passed=False,producer='tools.stress_etm_web.Echo',toolbox=str(a.toolbox.resolve()))
    def save():(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    try:
        for repeat in range(a.rounds):
            echo=Echo(a.port);echo.start();row=dict(repeat=repeat)
            try:
                command=[sys.executable,'-X','utf8',str(a.toolbox.resolve()),'trace','capture','--elf',str(a.elf.resolve()),'--bit',str((a.pair/'probe.bit').resolve()),'--zynq-elf',str((a.pair/'application.elf').resolve()),'--entry','cdc_poll','--seconds',str(a.seconds),'--swd-khz','10000','--out',str(a.out/f'record-{repeat}'),'--json-out',str(a.out/f'capture-{repeat}.json')]
                start=time.perf_counter()
                with (a.out/f'capture-{repeat}.log').open('w',encoding='utf8') as log:r=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                row['wallSeconds']=time.perf_counter()-start
                assert r.returncode==0,'CLI capture failed; no retry'
            finally:row['echo']=echo.close()
            result=json.loads((a.out/f'capture-{repeat}.json').read_text());assert result['ok'];q=result['result']['quality']
            lo,hi=q['hardwareStartBracketUnix'];lo,hi=hi+.02,lo+q['hardwareSeconds']-.02
            row.update(result=result,completeEchoesInGuaranteedHardwareWindow=sum(v['exact'] and lo<=v['sentUnix'] and v['receivedUnix']<=hi for v in row['echo']['rows']))
            assert not row['echo']['error'] and row['echo']['threadStopped'] and row['completeEchoesInGuaranteedHardwareWindow']>0
            assert not q['loss'] and q['requestedWindowComplete'] and result['result']['summary']['packetIssues']==0
            report['rows'].append(row);save();print(repeat,round(row['wallSeconds'],3),'s, exact hardware-window echoes',row['completeEchoesInGuaranteedHardwareWindow'],flush=True)
        report['passed']=True
    except BaseException as exc:report['error']=repr(exc);raise
    finally:save()

if __name__=='__main__':main()
