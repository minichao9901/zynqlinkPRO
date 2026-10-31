"""AI: repeat explicit JTAG/RAM loads and physical DDR checks; no Flash.

Each cycle loads the declared pair, checks physical OCM identity, waits for
USB enumeration, performs normal DAP setup and verifies a changed PL pattern.
Stop at the first failure and retain the board state for diagnosis.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--rounds',type=int,default=10);p.add_argument('--bytes',type=int,default=1048576)
    p.add_argument('--loader',type=Path,default=ROOT/'tools/download_dap_fpga.tcl')
    a=p.parse_args(argv)
    if not 1<=a.rounds<=30 or not 1<=a.bytes<=16<<20:p.error('finite load rounds 1..30 and pattern bytes 1..16MiB required')
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(hardware=True,flashWrites=False,retryFailedRounds=False,pair=str(a.pair.resolve()),
        loader=str(a.loader.resolve()),loaderSha256=hashlib.sha256(a.loader.read_bytes()).hexdigest(),requestedRounds=a.rounds,
        rounds=[],passed=False,runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output=out/'result.json'
    def save():output.write_text(json.dumps(report,indent=2)+'\n')
    save()
    for n in range(a.rounds):
        folder=out/f'load-{n+1:03}';seed=(0x27181300+n*0x45d9f3b)&0xffffffff
        started=time.monotonic()
        command=[sys.executable,str(ROOT/'tools/test_etm_ddr_memory.py'),'--pair',str(a.pair.resolve()),
            '--out',str(folder),'--loader',str(a.loader.resolve()),'--bytes',str(a.bytes),'--seed',str(seed),'--clock-mode','dap']
        with (out/f'load-{n+1:03}-console.txt').open('w',encoding='utf8') as log:
            run=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        result=folder/'result.json';data=json.loads(result.read_text()) if result.is_file() else None
        row=dict(round=n+1,exitCode=run.returncode,seconds=time.monotonic()-started,
            passed=run.returncode==0 and bool(data and data.get('passed')),result=str(result.relative_to(out)))
        report['rounds'].append(row);save()
        if not row['passed']:
            report.update(failedRound=n+1,boardStatePreservedForDiagnosis=True);save()
            raise RuntimeError('First load/check failure retained: '+str(result))
        print('load',n+1,'verified',round(row['seconds'],3),'seconds',flush=True)
    report['passed']=True;save();print(json.dumps(dict(passed=True,loadRounds=len(report['rounds']))));return 0


if __name__=='__main__':raise SystemExit(main())
