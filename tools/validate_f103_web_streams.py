"""Real Web F103 RAM stream comparison; explicit --execute and verified probe required."""
import argparse
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import numpy as np
from serial.tools.list_ports import comports
from validate_f103_main_web import Web
from f103_ram_fixture import Fixture
from probe_build_info import live_clock_snapshot
from benchmark_web_cli_25 import validate_hss


def sequence(data):
    assert data and len(data)%4==0
    values=np.frombuffer(data,dtype='<u4')
    assert values[0]==0 and np.all(np.diff(values)==1),(len(data),values[:4])
    return dict(bytes=len(data),words=len(values),sequenceExact=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['hss','rttcdc'],required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--runtime',required=True)
    p.add_argument('--seconds',type=float,default=3);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--points',default='1:24000,8:24000,1:48,8:192')
    p.add_argument('--speeds',default='50000000,60000000')
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print(json.dumps(dict(hardwareAccess=False,stage=a.stage)));return
    a.out.mkdir(parents=True,exist_ok=False);report=dict(stage=a.stage,rows=[],passed=False)
    def save():(a.out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    w=Web(SimpleNamespace(runtime=a.runtime,artifacts=a.out/'web',case_timeout=240))
    try:
        with Fixture(a.out/'fixture') as f:
            if a.stage=='hss':
                f.prepare_hss();w.page('scope','show');w.page('scope','describe')
                w.set('scope','#sc-mock',False);w.set('scope','#sc-target','swd')
                w.invoke('scope','connectHid',False);w.invoke('scope','connectUsb',False)
                w.set('scope','#sc-clock','60000');w.set('scope','#sc-raw',True)
                w.set('scope','#sc-batch',True);w.set('scope','#sc-cdcoff',True)
                w.set('scope','#sc-seconds',str(a.seconds+10))
                try:
                    for spec in a.points.split(','):
                        n,period=map(int,spec.split(':'))
                        w.page('scope','click',selector='#sc-varclear')
                        for i in range(n):w.invoke('scope','toggleVar',dict(name=f'fixture.w{i}',addr=0x20004100+4*i,size=4,scalar='u32'),True)
                        w.set('scope','#sc-period',str(period/24))
                        for repeat in range(a.repeats):
                            w.invoke('scope','clear');w.invoke('scope','start');time.sleep(.3)
                            state=w.invoke('scope','summary');assert state['running'],state
                            clock=live_clock_snapshot()
                            first=w.invoke('scope','readScopeMetrics',dict(fresh=True));time.sleep(a.seconds)
                            last=w.invoke('scope','readScopeMetrics',dict(fresh=True))
                            stop_error=None
                            try:w.invoke('scope','stop','F103 main comparison')
                            except RuntimeError as exc:stop_error=str(exc)
                            end=w.invoke('scope','summary');w.invoke('scope','saveRaw')
                            raw=w.download('scope',a.out/f'n{n}-p{period}-r{repeat}.jsp')
                            actual_period=end['probeMetrics']['periodTicks']
                            reader,versions=validate_hss(raw,f.pattern[256:256+4*n],actual_period)
                            dt=((last['tick']-first['tick'])&0xffffffff)/last['hz'];produced=(last['produced']-first['produced'])&0xffffffff
                            row=dict(variables=n,requestedPeriodTicks=period,periodTicks=actual_period,stopError=stop_error,repeat=repeat,clock=clock,measuredSeconds=dt,effectiveHz=produced/dt,
                                skipped=(last['skipped']-first['skipped'])&0xffffffff,first=first,last=last,final=end,
                                rawBytes=len(raw),rawSamples=reader.samples,protocolVersions=versions,allValuesExact=True,tailDelta=end['tailCountDelta'])
                            report['rows'].append(row);save()
                            assert reader.samples==end['receivedSamples']==end['probeMetrics']['produced'],(reader.samples,end)
                            assert not any(end[k] for k in ['lostUsb','lostGap','readErrors','metricsError']),end
                            print(n,period,repeat,row['effectiveHz'],row['skipped'],flush=True)
                            assert abs(clock['actual_link_Hz']-60000000)<10
                    w.invoke('scope','exportCsv');w.download('scope',a.out/'last-window.csv')
                finally:w.invoke('scope','stop','cleanup');w.invoke('scope','disconnect')
            else:
                f.release_hid()
                w.page('rttcdc','show');w.page('rttcdc','describe')
                w.set('rttcdc','#h-target','swd');w.set('rttcdc','#h-addr','0x20000200')
                w.set('rttcdc','#h-size','0x100');w.set('rttcdc','#h-chan','0')
                w.invoke('rttcdc','connect',target='hid');w.page('rttcdc','describe',target='hid')
                w.invoke('rttcdc','refreshPorts')
                options=next(c['options'] for c in w.page('rttcdc','describe')['controls'] if c['selector']=='#c-port')
                port=next(p.device for p in comports() if p.vid==0xd28 and p.pid==0x204)
                chosen=[o for o in options if port.lower() in o['label'].lower()];assert len(chosen)==1,(port,options)
                w.set('rttcdc','#c-port',chosen[0]['value']);w.set('rttcdc','#c-ts',False)
                w.set('rttcdc','#c-record-auto',False);w.invoke('rttcdc','connect')
                try:
                    for speed in map(int,a.speeds.split(',')):
                        w.set('rttcdc','#h-clock',str(speed))
                        for repeat in range(a.repeats):
                            f.prepare_rtt();w.page('rttcdc','click',selector='#c-clear');w.page('rttcdc','click',selector='#c-statclear')
                            w.invoke('rttcdc','start',target='hid')
                            begin=w.invoke('rttcdc','summary',target='hid');assert begin['running'],begin
                            clock=live_clock_snapshot();row=dict(speed=speed,repeat=repeat,clock=clock)
                            def produce():
                                try:
                                    time.sleep(.3);f.resume();time.sleep(a.seconds);row['published']=f.halt_producer()
                                except BaseException as exc:row['producerError']=repr(exc)
                            worker=threading.Thread(target=produce);worker.start()
                            try:window=w.invoke('rttcdc','captureWindow',dict(seconds=a.seconds+2,maxMiB=64))
                            finally:worker.join(10)
                            assert not worker.is_alive() and not row.get('producerError'),row
                            w.invoke('rttcdc','stop',target='hid');w.invoke('rttcdc','refresh',target='hid')
                            end=w.invoke('rttcdc','summary',target='hid')
                            raw=w.download('rttcdc',a.out/f'speed{speed}-r{repeat}.bin')
                            row.update(window=window,engine=end,integrity=sequence(raw))
                            assert len(raw)==row['published']==end['moved'] and not end['rdErr'] and not end['wrErr'],row
                            assert abs(clock['actual_link_Hz']-speed)<10
                            report['rows'].append(row);save();print(speed,repeat,len(raw),window,flush=True)
                finally:
                    w.invoke('rttcdc','stop',target='hid');w.invoke('rttcdc','disconnect',target='hid');w.invoke('rttcdc','close',target='session')
        report['passed']=True
    except BaseException as exc:report['error']=repr(exc);raise
    finally:save()

if __name__=='__main__':main()
