"""AI experiment: scan physical input delays, retain failing points, validate a candidate.

Target firmware owns the clock. Run inside etm.ram-fixture for the SRAM72
target. This is an observed protocol-quality search, not an electrical eye/BER
measurement. No automatic retry of a point or silent acceptance of a bad decode.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from etm_lane_delay import LaneDelay
from probe_flash import Session
from zynq_memory import PhysicalMemory
from stress_etm_web import Echo

ROOT=Path(__file__).resolve().parents[1]


def choose_window(points,min_width=5):
    """Choose the middle of a fully measured, non-wrapping passing tap run."""
    if set(points)!=set(range(32)):return None
    runs=[];start=None
    for i in range(33):
        passing=i<32 and points[i] is True
        if passing and start is None:start=i
        if not passing and start is not None:
            end=i-1
            if end-start+1>=min_width:runs.append((start,end))
            start=None
    if not runs:return None
    lo,hi=max(runs,key=lambda r:(r[1]-r[0],-abs((r[0]+r[1])/2-15.5)))
    return dict(first=lo,last=hi,tap=(lo+hi)//2,width=hi-lo+1,
                meaning='Observed protocol-quality run; no unmeasured taps or wraparound')


def excitation(path):
    data=np.fromfile(path,dtype=np.uint8)
    nibbles=np.column_stack((data&15,data>>4)).reshape(-1)
    change=nibbles[1:]^nibbles[:-1]
    lanes=[]
    for i in range(4):
        ones=int(np.count_nonzero(nibbles&(1<<i)));zeros=len(nibbles)-ones
        transitions=int(np.count_nonzero(change&(1<<i)))
        lanes.append(dict(ones=ones,zeros=zeros,transitions=transitions))
    return dict(estimatedFrom='Normalized formatter nibbles, not independent analog pad measurements',
        dataLanes=lanes,excited=all(min(r['ones'],r['zeros'],r['transitions'])>=64 for r in lanes))


def score(row):
    q=row['quality'];useful=q['synced'] and row['formatterBytes']>=1024 and row['excitation']['excited']
    grade=0 if useful and not q['loss'] else (1 if useful else 2)
    return grade,q['diagnostics']['parserErrors'],-row['formatterBytes']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair',type=Path,required=True);p.add_argument('--target-elf',type=Path,required=True)
    p.add_argument('--ram-image',action='store_true');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--milliseconds',type=int,default=10);p.add_argument('--coarse',default='0,8,16,24,31')
    p.add_argument('--coarse-only',action='store_true');p.add_argument('--cdc-port',default='COM34')
    p.add_argument('--keep-candidate',action='store_true',help='Only retain a fully validated candidate; default restores original selection')
    a=p.parse_args()
    if not 2<=a.milliseconds<=100:p.error('Calibration short windows must be 2..100ms')
    try:coarse=sorted(set(int(v) for v in a.coarse.split(',')))
    except ValueError:p.error('Invalid coarse tap list')
    if not coarse or min(coarse)<0 or max(coarse)>31:p.error('Coarse taps must be 0..31')
    pair=a.pair.resolve();elf=a.target_elf.resolve()
    if a.ram_image:
        from f103_ram_image import plan
        plan(elf)
    manifest=json.loads((pair/'manifest.json').read_text(encoding='utf8'))
    for name in ('probe.bit','application.elf','ps7_init.tcl'):
        expected=manifest['files'][name];expected=expected['sha256'] if isinstance(expected,dict) else expected
        if hashlib.sha256((pair/name).read_bytes()).hexdigest()!=expected:raise ValueError('Probe pair identity mismatch')
    a.out.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False,hardwareAccess=True,flashWrites=False,hostTargetClockWrites=False,
        pair=str(pair),targetElf=str(elf),targetSha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
        measuredElectricalEye=False,retryFailedPoints=False,rows=[],windows=[],candidate=None)
    def save():(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    control=LaneDelay(PhysicalMemory(Session(a.out/'jtag',Path('E:/Xilinx/SDK/2018.3'),'tcp:127.0.0.1:3121')))
    original=None;echo=None;cache={};keep=False;clock_baseline=None;save()
    def measure(taps,enabled=True,milliseconds=None,holdout=False):
        nonlocal clock_baseline
        duration=milliseconds or a.milliseconds;key=(enabled,*taps,duration)
        if not holdout and key in cache:return cache[key]
        index=len(report['rows'])+1;folder=a.out/f'point-{index:03d}'
        row=dict(index=index,taps=list(taps),enabled=enabled,milliseconds=duration,holdout=holdout)
        report['rows'].append(row);save()
        row['configuration']=control.configure(enabled,taps);save()
        command=[sys.executable,str(ROOT/'tools/test_orbtrace_board.py'),'--target-elf',str(elf),
            '--bit',str(pair/'probe.bit'),'--elf',str(pair/'application.elf'),'--output',str(folder),
            '--milliseconds',str(duration),'--speed-khz','1000','--transport','ddr']
        if a.ram_image:command.append('--ram-image')
        run=subprocess.run(command,capture_output=True,cwd=ROOT)
        (a.out/f'point-{index:03d}.log').write_bytes(run.stdout+run.stderr);row['returnCode']=run.returncode
        acceptance=json.loads((folder/'acceptance.json').read_text(encoding='utf8'))
        ddr=json.loads((folder/'ddr/result.json').read_text(encoding='utf8'));q=ddr['quality']
        row.update(quality=q,formatterBytes=ddr['bytes'],formatterSha256=ddr['sha256'],rcc=acceptance['rcc_before'])
        save()
        if not acceptance.get('restored') or not acceptance.get('fpb_restored') or any(acceptance.get(k) for k in ('target_cleanup_error','usb_cleanup_error','reconnect_error','usb_reader_errors')):
            raise RuntimeError('Capture cleanup failed; scan stopped')
        if row['rcc']!=acceptance['rcc_after']:raise RuntimeError('Target firmware clocks changed within a point')
        if clock_baseline is None:clock_baseline=row['rcc']
        if row['rcc']!=clock_baseline:raise RuntimeError('Target firmware clocks changed between points')
        diagnostics=q['diagnostics']
        if any(diagnostics[k] for k in ('frameDrops','writerError','idelayReadyLosses')) or q['stopReason'] or not q['ended']:
            raise RuntimeError('Non-input capture failure; not a calibration score')
        if run.returncode and 'DDR hardware quality/window failed' not in acceptance.get('error',''):
            raise RuntimeError('Unexpected capture failure; no retry')
        row['excitation']=excitation(folder/'ddr/capture.frm1')
        row['protocolPass']=score(row)[0]==0
        earliest,latest=q['hardwareStartBracketUnix'];seconds=q['hardwareSeconds'];margin=min(.020,seconds*.1)
        lower,upper=latest+margin,earliest+seconds-margin
        row['echoInsideHardwareWindow']=sum(x['exact'] and lower<=x['sentUnix'] and x['receivedUnix']<=upper for x in echo.rows)
        cache[key]=row;save()
        print('point',index,'taps',taps,'pass',row['protocolPass'],'parser',diagnostics['parserErrors'],flush=True)
        return row
    try:
        original=control.snapshot();report['original']=original;save()
        echo=Echo(a.cdc_port);echo.start()
        report['bypass']=measure(original['taps'],False)
        coarse_rows=[]
        for data_tap in coarse:
            for clock_tap in coarse:coarse_rows.append(measure([data_tap]*4+[clock_tap]))
        best=min(coarse_rows,key=score);current=list(best['taps']);report['coarseBest']=best['index'];save()
        if a.coarse_only:return 0
        for lane in range(5):
            rows=[]
            for tap in range(32):
                candidate=current.copy();candidate[lane]=tap;rows.append(measure(candidate))
            window=choose_window({r['taps'][lane]:r['protocolPass'] for r in rows})
            report['windows'].append(dict(lane=lane,otherTaps=current.copy(),window=window))
            if window:current[lane]=window['tap']
            else:current=list(min(rows,key=score)['taps'])
            save()
        report['candidate']=current;save()
        # Check local margin under the final settings, since lane searches interact.
        neighbors=[]
        for lane in range(5):
            if not 2<=current[lane]<=29:raise RuntimeError('Candidate has no two-tap margin inside the measured range')
            for delta in (-2,-1,1,2):
                candidate=current.copy();candidate[lane]+=delta;neighbors.append(measure(candidate))
        if not all(r['protocolPass'] for r in neighbors):raise RuntimeError('Final-setting neighborhood did not pass')
        from trace_signal_analysis import native_summary
        for duration in (100,1000):
            row=measure(current,milliseconds=duration,holdout=True)
            if not row['protocolPass'] or not row['echoInsideHardwareWindow']:raise RuntimeError('Candidate holdout/CDC failed')
            folder=a.out/f"point-{row['index']:03d}"
            acceptance=json.loads((folder/'acceptance.json').read_text(encoding='utf8'))
            row['decode']=native_summary((folder/'etm.bin').read_bytes(),elf,acceptance['config'],folder/'validation-decode');save()
            if not row['decode']['interiorPass']:raise RuntimeError('Candidate failed native instruction decode')
        report['passed']=True;keep=a.keep_candidate;save()
    except Exception as e:report['error']=str(e);save();raise
    finally:
        try:
            if echo:
                result=echo.close();(a.out/'echo.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
                report['echoError']=result['error']
                if result['error']:report['passed']=False;keep=False
            if original and not keep:report['restoration']=control.configure(original['enabled'],original['taps'])
        except Exception as e:report['restoreError']=str(e);report['passed']=False;raise
        finally:
            report['candidateRetained']=keep;save()
    if not report['passed']:raise RuntimeError('Calibration/echo did not pass')
    print(json.dumps(dict(passed=True,candidate=report['candidate'],candidateRetained=keep)))
    return 0


if __name__=='__main__':raise SystemExit(main())
