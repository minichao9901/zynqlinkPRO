"""AI F103-only DDR acceptance: changed entry, hardware window, CDC, native decode.

Load and identity-verify the supplied probe pair before running. No Flash or
target clock writes; no automatic retries. Web acceptance is a separate test.
H743 remains on its existing ETMv4 Web/Kingst path pending separate board tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.stress_etm_web import Echo
from trace_signal_analysis import native_summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair',type=Path,required=True)
    p.add_argument('--target-elf',type=Path,default=ROOT/'prebuilt/golden/f103ze-cdc48.elf')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--rounds',type=int,default=2)
    p.add_argument('--seconds',default='1,2')
    p.add_argument('--functions',default='cdc_poll,cdc_tx_poll')
    p.add_argument('--cdc-port',default='COM34')
    p.add_argument('--decode',action='store_true',help='Full native packet/range verification, may expand to large native.bin')
    p.add_argument('--download',choices=('usb','physical'),default='usb')
    p.add_argument('--verify-ddr-physical',action='store_true',help='Compare USB bytes with the same physical AP0 DDR buffer')
    a=p.parse_args()
    seconds=[float(x) for x in a.seconds.split(',')]
    functions=a.functions.split(',')
    if not 1<=a.rounds<=20 or not seconds or not all(0<x<=2 for x in seconds) or not all(functions):
        p.error('invalid finite rounds/windows/functions')
    pair=a.pair.resolve();out=a.out.resolve()
    manifest=json.loads((pair/'manifest.json').read_text())
    for name in ('probe.bit','application.elf','ps7_init.tcl'):
        expected=manifest['files'][name]
        if isinstance(expected,dict):expected=expected['sha256']
        if hashlib.sha256((pair/name).read_bytes()).hexdigest()!=expected:raise ValueError('pair hash mismatch')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(hardwareAccess=True,webAcceptance=False,usbDdrDownload=a.download=='usb',flashWrites=False,
        pair=str(pair),files=manifest['files'],reloadBetweenRounds=False,retryFailedRounds=False,
        runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),rows=[],passed=False)
    def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    for index in range(a.rounds):
        duration=seconds[index%len(seconds)];function=functions[index%len(functions)]
        work=out/f'round-{index+1:03}'
        row=dict(round=index+1,seconds=duration,function=function,passed=False)
        report['rows'].append(row);save()
        echo=Echo(a.cdc_port)
        try:
            echo.start()
            command=[sys.executable,str(ROOT/'tools/test_orbtrace_board.py'),'--target-elf',str(a.target_elf.resolve()),
                '--bit',str(pair/'probe.bit'),'--elf',str(pair/'application.elf'),'--output',str(work),
                '--milliseconds',str(duration*1000),'--speed-khz','1000','--entry',function]
            command+=['--ddr-physical'] if a.download=='physical' else ['--transport','ddr']
            if a.verify_ddr_physical:command+=['--verify-ddr-physical']
            started=time.time()
            # Wait for the target-restoration finally block; do not kill a capture subprocess.
            run=subprocess.run(command,capture_output=True)
            (out/f'round-{index+1:03}.log').write_bytes(run.stdout+run.stderr)
            row.update(returnCode=run.returncode,hostStartedUnix=started,hostEndedUnix=time.time())
        finally:
            row['echo']=echo.close();save()
        acceptance=work/'acceptance.json'
        if acceptance.exists():row['capture']=json.loads(acceptance.read_text())
        save()
        if run.returncode:raise RuntimeError('capture failed; first failure retained')
        capture=row['capture'];ddr=capture['ddr']
        if not capture.get('restored') or not capture.get('fpb_restored') or capture.get('target_cleanup_error'):
            raise RuntimeError('target restoration incomplete')
        earliest,latest=ddr['hardwareStartBracketUnix']
        # Same Windows host clock in XSCT and Python. Require complete echo
        # transactions inside the intersection of all possible hardware windows.
        lower,upper=latest+.020,earliest+ddr['actualWindowSeconds']-.020
        row['guaranteedHardwareWindowUnix']=[lower,upper]
        row['echoInsideHardwareWindow']=sum(r['exact'] and lower<=r['sentUnix'] and r['receivedUnix']<=upper for r in row['echo']['rows'])
        save()
        if row['echo']['error'] or not row['echoInsideHardwareWindow']:
            raise RuntimeError('no exact CDC echo proven inside hardware window')
        if a.decode:
            row['decode']=native_summary((work/'etm.bin').read_bytes(),a.target_elf,capture['config'],work/'decode')
            save()
            # Explicitly report a partial final packet; never count interior corruption as a boundary.
            if not row['decode']['interiorPass']:raise RuntimeError('native instruction-range decode failed')
        row['passed']=True;save()
        print('DDR trace',index+1,function,duration,'s',ddr['bytes'],'formatter bytes; exact hardware-window echoes',row['echoInsideHardwareWindow'],flush=True)
    report['passed']=True;save()
    print(json.dumps(dict(passed=True,rounds=len(report['rows']),webAcceptance=False)))


if __name__=='__main__':main()
