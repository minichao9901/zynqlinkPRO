"""Same-fixture HPM6800 Web/CLI 25MHz comparison. No Flash/PLL/reset writes.

Requires independently verified idle probe and hpm6800_usb_fixture install.
That outer fixture owns all RAM/register backups and must be restored afterwards.
"""
import argparse,json,random,struct,subprocess,sys,threading,time
from pathlib import Path
from types import SimpleNamespace
import serial
from serial.tools.list_ports import comports
import usb.util
from probe_stream import Probe
from dap_pipeline_bench import open_dap,xfer
from validate_hpm6800_performance import SramMemory
from benchmark_hpm5301 import setup,hss_scan_observation
from probe_build_info import live_clock_snapshot
from riscv_target import RiscvTarget
from benchmark_rtt_forward import Reader
from benchmark_probe_stream import HssReader
from validate_hpm6800_web import Web
from validate_hpm6800_cdc_sequence import sequence
ROOT=Path(__file__).resolve().parents[1]

def validate_hss(raw,expected,period):
    # Integer-us Web periods use v1; fractional-us periods use v2 ticks.
    # Preserve raw bytes and normalize only timestamp units for the shared
    # sequence/timeline/value checker. Payload bytes are never modified.
    assert len(raw)%512==0
    normalized=bytearray(raw);versions=set()
    for at in range(0,len(raw),512):
        magic,version=struct.unpack_from('<HB',raw,at);assert magic==0x4a53 and version in (1,2)
        versions.add(version)
        if version==1:
            normalized[at+2]=2
            struct.pack_into('<I',normalized,at+8,(struct.unpack_from('<I',raw,at+8)[0]*24)&0xffffffff)
    reader=HssReader(None,expected,period,allow_duplicate_stat=True);reader.consume(normalized)
    return reader,sorted(versions)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['cli-rtt','web-rtt','prepare-rtt','prepare-hss','web-hss'],required=True)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--runtime');p.add_argument('--seconds',type=float,default=3);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--points',default='1:174,1:173,8:921,8:920');p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not .1<=a.seconds<=20 or a.repeats<1:p.error('--seconds must be 0.1..20 and --repeats positive')
    if a.execute and a.stage.startswith('web-') and not a.runtime:p.error('Web execution requires --runtime')
    if not a.execute:print(json.dumps(dict(stage=a.stage,hardwareAccess=False)));return
    a.out.mkdir(parents=True,exist_ok=False);report=dict(stage=a.stage,rows=[],passed=False)
    def save():(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    def control(action):
        r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/hpm6800_usb_fixture.py'),action,'--state',str(a.fixture),'--batch','2048'],capture_output=True,text=True,timeout=20)
        assert r.returncode==0,(r.stdout,r.stderr)
        return json.loads(r.stdout) if action=='stop' else r.stdout
    def web(out):return Web(SimpleNamespace(runtime=a.runtime,out=out,timeout=240,elf=a.fixture/'producer.elf',seconds=a.seconds,live=False))
    try:
        if a.stage=='prepare-rtt':
            dev,tx,rx=open_dap()
            try:
                setup(tx,rx,10000000,0,connect=True);target=RiscvTarget(tx,rx);target.active();target.halt()
                meta=json.loads((a.fixture/'state.json').read_text());assert meta['phase']=='installed'
                target.register(0x7b0,(meta['registers'][str(0x7b0)]&~7)|3)
                target.register(0x7b1,0x10000);target.resume()
            finally:usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
            report['target']='RAM producer resumed; outer backup remains authoritative'
        elif a.stage=='prepare-hss':
            control('stop');dev,tx,rx=open_dap()
            try:
                setup(tx,rx,10000000,0,connect=True);target=RiscvTarget(tx,rx);target.active();target.halt()
                mem=SramMemory(tx,rx);data=random.Random(0x68004853).randbytes(4096)
                mem.write(0xf0404000,data);assert mem.read(0xf0404000,4096)==data
                assert xfer(tx,rx,[3])==b'\x03\x00' # Release native fixture's DAP connection before Web owns the stream.
            finally:usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
            report['target']='temporary producer halted; same static AHB fixture as native CLI'
        elif a.stage=='cli-rtt':
            for repeat in range(a.repeats):
                control('reset');probe=Probe();port=next(p.device for p in comports() if p.vid==0xd28 and p.pid==0x204)
                with serial.Serial(port,115200,timeout=.025) as com:
                    class ObservedPort:
                        first=None;last=None;firstBytes=0
                        def read(self,n):
                            data=com.read(n)
                            if data:
                                now=time.perf_counter()
                                if self.first is None:self.first=now;self.firstBytes=len(data)
                                self.last=now
                            return data
                    observed=ObservedPort();com.reset_input_buffer();reader=Reader(observed);reader.start()
                    try:
                        assert probe.action(0x31,10,b'\x01')[0]==0
                        assert probe.action(0x31,7,struct.pack('<IHBB',25000000,2048,0,255))[0]==0
                        assert probe.action(0x31,1,struct.pack('<IIB',0xf0400200,256,0))[0]==0
                        clock=live_clock_snapshot();clock['effectiveIdle']=hss_scan_observation()['effective_idle']
                        control('start');time.sleep(.3)
                        t0=time.perf_counter();_,first=probe.action(0x31,2);n0=reader.count
                        time.sleep(a.seconds)
                        _,last=probe.action(0x31,2);n1=reader.count;t1=time.perf_counter()
                        published=control('stop')['published_bytes'];deadline=time.monotonic()+5
                        while reader.count!=published and time.monotonic()<deadline:time.sleep(.02)
                        assert probe.action(0x31,0)[0]==0
                        reader.quit.set();reader.join(2)
                        assert not reader.error and not reader.pending and reader.count==published,(reader.error,reader.count,published)
                        assert abs(clock['actual_link_Hz']-25000000)<10
                        report['rows'].append(dict(repeat=repeat,hostBytesPerSecond=(n1-n0)/(t1-t0),probeBytesPerSecond=(last[3]-first[3])/(t1-t0),
                            activeBytesPerSecond=(reader.count-observed.firstBytes)/(observed.last-observed.first),
                            clock=clock,sequenceExact=True,publishedBytes=published,receivedBytes=reader.count,first=first,last=last))
                    finally:
                        control('stop');probe.action(0x31,0);reader.quit.set();reader.join(2);probe.close()
                save();print(report['rows'][-1],flush=True)
        elif a.stage=='web-rtt':
            for repeat in range(a.repeats):
                control('reset');row=dict(repeat=repeat);report['rows'].append(row);save()
                class TimedWeb(Web):
                    worker=None
                    def set(self,page,selector,value):
                        if page=='rttcdc' and selector=='#h-size':value='0x100'
                        return super().set(page,selector,value)
                    def invoke(self,page,method,*args,**kwargs):
                        if page=='rttcdc' and method=='start':
                            self.set('rttcdc','#h-clock','25000000')
                        if page=='rttcdc' and method=='captureWindow':
                            args=({**args[0],'seconds':a.seconds+3},)
                            def produce():
                                try:
                                    time.sleep(.5);control('start');time.sleep(.3)
                                    # No second page job during captureWindow.
                                    time.sleep(a.seconds);row['producer']=control('stop')
                                except BaseException as e:row['controlError']=repr(e)
                            self.worker=threading.Thread(target=produce);self.worker.start()
                        value=super().invoke(page,method,*args,**kwargs)
                        if page=='rttcdc' and method=='start':
                            row['clock']=live_clock_snapshot();row['clock']['effectiveIdle']=hss_scan_observation()['effective_idle']
                        return value
                w=TimedWeb(SimpleNamespace(runtime=a.runtime,out=a.out/f'round-{repeat}',timeout=240,elf=a.fixture/'producer.elf',seconds=a.seconds+3,live=False))
                try:
                    row['web']=w.rttcdc(pattern_check=lambda data:bool(row.update(integrity=sequence(data))) or row['integrity']['sequenceExact'])
                    assert not row.get('controlError'),row
                    assert row['integrity']['bytes']==row['producer']['published_bytes']==row['web']['engine']['moved'],row
                    assert abs(row['clock']['actual_link_Hz']-25000000)<10
                finally:
                    if w.worker:w.worker.join(25)
                    control('stop');save()
                print(row,flush=True)
        else:
            w=web(a.out/'web');w.page('scope','show');w.page('scope','describe')
            w.set('scope','#sc-mock',False);w.set('scope','#sc-target','riscv')
            w.invoke('scope','connectHid',False);w.invoke('scope','connectUsb',False)
            w.set('scope','#sc-clock','25000');w.set('scope','#sc-raw',True);w.set('scope','#sc-batch',False);w.set('scope','#sc-cdcoff',False)
            w.set('scope','#sc-seconds',str(a.seconds+5));fixture=random.Random(0x68004853).randbytes(4096)
            try:
                for spec in a.points.split(','):
                    n,period=map(int,spec.split(':'))
                    w.page('scope','click',selector='#sc-varclear')
                    for i in range(n):w.invoke('scope','toggleVar',dict(name=f'fixture.w{i}',addr=0xf0404100+4*i,size=4,scalar='u32'),True)
                    w.set('scope','#sc-period',str(period/24))
                    for repeat in range(a.repeats):
                        w.invoke('scope','clear');w.invoke('scope','start');time.sleep(.3)
                        start=w.invoke('scope','summary');assert start['running'],start
                        clock=live_clock_snapshot();clock['effectiveIdle']=hss_scan_observation()['effective_idle']
                        first=w.invoke('scope','readScopeMetrics',dict(fresh=True));time.sleep(a.seconds)
                        last=w.invoke('scope','readScopeMetrics',dict(fresh=True));w.invoke('scope','stop','25MHz comparison')
                        end=w.invoke('scope','summary');w.invoke('scope','saveRaw');raw=w.download('scope',a.out/f'n{n}-p{period}-r{repeat}.jsp')
                        reader,versions=validate_hss(raw,fixture[256:256+4*n],period)
                        assert reader.samples==end['receivedSamples']==end['probeMetrics']['produced'],(reader.samples,end)
                        assert not any(end[k] for k in ['lostUsb','lostGap','readErrors','metricsError']),end
                        dt=((last['tick']-first['tick'])&0xffffffff)/last['hz'];produced=(last['produced']-first['produced'])&0xffffffff
                        row=dict(variables=n,periodTicks=period,repeat=repeat,clock=clock,measuredSeconds=dt,effectiveHz=produced/dt,
                            skipped=(last['skipped']-first['skipped'])&0xffffffff,first=first,last=last,final=end,
                            rawBytes=len(raw),rawSamples=reader.samples,protocolVersions=versions,allValuesExact=True,tailDelta=end['tailCountDelta'])
                        report['rows'].append(row);save();print({k:v for k,v in row.items() if k not in ['first','last','final']},flush=True)
                        assert abs(clock['actual_link_Hz']-25000000)<10
            finally:w.invoke('scope','stop','cleanup');w.invoke('scope','disconnect')
        report['passed']=True
    except BaseException as exc:report['error']=repr(exc);raise
    finally:save()
if __name__=='__main__':main()
