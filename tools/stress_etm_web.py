"""AI drives real Web buttons: probe lifecycle, changed entries, capture and CDC.

No Flash programming, PLL/AHB changes or automatic retry of failed rounds.
Run against a loaded, identity-verified probe and the matching target ELF.
H743 requires explicit ELF and recurring entry functions; it never borrows F103 firmware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.f103_stream_acceptance import Streams,symbol
from toolbox import pack_file


class Echo:
    def __init__(self,port):
        import serial
        self.serial=serial.Serial(port,115200,timeout=.02,write_timeout=1)
        self.serial.dtr=True
        # A DTR transition can emit the application's banner. Consume this
        # startup-only traffic before measuring byte-exact echo payloads.
        deadline=time.monotonic()+.2
        while time.monotonic()<deadline:self.serial.read(self.serial.in_waiting or 1)
        self.rows=[];self.error=None;self.stop=threading.Event();self.thread=None
    def start(self):
        self.serial.reset_input_buffer()
        def run():
            try:
                for n in range(10000):
                    if self.stop.is_set():break
                    payload=(('ETM_%06d_'%n+'0123456789abcdef'*4)[:62]+'\r\n').encode()
                    tx=time.time();self.serial.write(payload);received=bytearray();until=time.monotonic()+15
                    while len(received)<len(payload) and time.monotonic()<until:
                        received.extend(self.serial.read(len(payload)-len(received)))
                        if self.stop.is_set() and not received:break
                    row={'number':n,'sentUnix':tx,'receivedUnix':time.time(),'bytes':len(received),
                        'sha256':hashlib.sha256(received).hexdigest(),'exact':bytes(received)==payload}
                    self.rows.append(row)
                    if not row['exact']:
                        if not self.stop.is_set():raise RuntimeError('CDC echo mismatch: '+str(row))
                        break
                    self.stop.wait(.002)
            except Exception as error:self.error=str(error)
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(2)
        self.serial.close()
        if self.thread:self.thread.join(1)
        return {'rows':self.rows,'error':self.error,'threadStopped':not self.thread or not self.thread.is_alive()}


class Stress(Streams):
    def __init__(self,args):
        super().__init__(args)
        runtime=json.loads((Path(args.runtime)/'toolbox-runtime.json').read_text(encoding='utf8'))
        self.records=Path(args.records_root or runtime.get('recordsDirectory') or ROOT/'etm-service/records')
    def ready(self,selector,timeout=30):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            value=self.page('etm','read',selector=selector)
            if not value['disabled']:return
            time.sleep(.05)
        status=self.page('etm','read',selector='#job-state')['text']
        log=self.page('etm','read',selector='#log')['text']
        self.save(self.out/'timeout.json',{'selector':selector,'status':status,'log':log})
        raise TimeoutError('Web control did not become ready: '+selector+'; '+status)

    def initialize(self):
        self.page('etm','show')
        self.page('etm','upload',selector='#elf-file',files=[pack_file(self.args.elf)])
        self.wait('etm','#elf-label',Path(self.args.elf).name);self.ready('#choose-elf')
        self.set('etm','#hse',str(self.args.hse_mhz));self.set('etm','#target-profile',self.args.profile)
        self.set('etm','#reset-before',self.args.reset_before);self.set('etm','#entry-before',True)
        self.set('etm','#duration',str(self.args.milliseconds));self.set('etm','#auto-decode',True)
        if self.args.sources:
            root=Path(self.args.sources)
            files=[pack_file(p,root.name+'/'+p.relative_to(root).as_posix()) for p in sorted(root.rglob('*')) if p.is_file()]
            self.page('etm','upload',selector='#sources-files',files=files)
            self.wait('etm','#sources-label','已保存本地快照');self.ready('#choose-elf')

    def connect(self):
        start=time.perf_counter();self.page('etm','click',selector='#connect');self.ready('#disconnect')
        info=self.invoke('etm','inspect',target='target')
        if info['profile']!=self.args.profile or info.get('clockError'):raise RuntimeError('Unexpected target: '+str(info))
        return info,time.perf_counter()-start

    def disconnect(self):
        start=time.perf_counter();self.page('etm','click',selector='#disconnect');self.ready('#connect')
        return time.perf_counter()-start

    def lifecycle(self):
        rows=[]
        for n in range(self.args.rounds):
            info,opened=self.connect();closed=self.disconnect()
            rows.append({'round':n+1,'openSeconds':opened,'closeSeconds':closed,'profile':info['profile'],'clocks':info['clocks'],'rcc':info['rcc'],'halted':info['halted']})
            self.save(self.out/'lifecycle.json',rows)
            print('probe',n+1,'open',round(opened,3),'close',round(closed,3),flush=True)
        return rows

    def captures(self):
        from serial.tools.list_ports import comports
        port=self.args.cdc_port
        if self.args.echo and not port:
            ports=[p.device for p in comports() if p.vid==0xf055 and p.pid==0x1031]
            if self.args.profile!='stm32f103ze' or len(ports)!=1:
                raise ValueError('Select the target CDC port explicitly with --cdc-port; found '+str(ports))
            port=ports[0]
        rows=[];functions=self.args.functions.split(',')
        for n in range(self.args.capture_rounds):
            info,opened=self.connect();function=functions[n%len(functions)];echo=None
            row={'round':n+1,'function':function,'before':info,'openSeconds':opened}
            try:
                if self.args.echo:
                    self.page('etm','click',selector='#run');self.ready('#disconnect')
                    echo=Echo(port);echo.start()
                self.set('etm','#break-command','b '+function)
                self.page('etm','click',selector='#add-break');self.ready('#start')
                if self.args.native_exchange!='auto':
                    enabled=self.args.native_exchange=='on' or self.args.native_exchange=='alternate' and n%2==1
                    self.invoke('etm','setNativeExchange',enabled,target='target');row['nativeExchange']=enabled
                if self.args.packed_memory!='auto':
                    packed=self.args.packed_memory=='on' or self.args.packed_memory=='alternate' and n%2==1
                    self.invoke('etm','setPackedMemory',packed,target='target');row['packedMemory']=packed
                if self.args.register_batch!='auto':
                    grouped=self.args.register_batch=='on' or self.args.register_batch=='alternate' and n%2==1
                    self.invoke('etm','setRegisterBatch',grouped,target='target');row['registerBatch']=grouped
                if self.args.profile_control:self.invoke('etm','resetTransportStats',target='target')
                previous=self.page('etm','read',selector='#records')['value'];started=time.perf_counter()
                row['captureAttemptUnix']=time.time()
                self.page('etm','click',selector='#start')
                until=time.monotonic()+self.args.case_timeout
                while time.monotonic()<until:
                    status=self.page('etm','read',selector='#job-state')['text']
                    controls=self.page('etm','read',selector='#disconnect')
                    sid=self.page('etm','read',selector='#records')['value']
                    if not controls['disabled']:
                        if '失败' in status or 'loss=' in status or '超时' in status or '错误' in status:
                            raise RuntimeError(status)
                        if sid and sid!=previous:
                            folder=self.records/sid
                            metadata=json.loads((folder/'session.json').read_text(encoding='utf8'))
                            if metadata.get('errorStage')=='capture':raise RuntimeError(metadata.get('error') or 'Capture failed')
                            if (folder/'decoded.json').is_file():break
                    time.sleep(.05)
                else:raise TimeoutError('Capture did not finish: '+status)
                self.invoke('etm','waitForDisplay',target='history')
                record=self.records/sid
                meta=json.loads((record/'session.json').read_text(encoding='utf8'))
                decoded=json.loads((record/'decoded.json').read_text(encoding='utf8'))
                if self.args.profile_control:row['controlTransport']=self.invoke('etm','transportStats',target='target')
                quality=meta.get('captureQuality') or {}
                if quality.get('transport')=='ddr-usb/1':
                    if not meta.get('captureExtent',{}).get('complete') or meta.get('captureWarning'):
                        raise RuntimeError('Measured DDR window metadata is inconsistent: '+str(meta.get('captureWarning')))
                if quality.get('loss') or not quality.get('synced') or not quality.get('ended'):
                    raise RuntimeError('Transport quality did not pass: '+str(quality))
                if decoded['summary']['packetIssues']:raise RuntimeError('Decoder packet errors')
                entry=decoded.get('captureStart') or {}
                if entry.get('selectedPC')!=(symbol(self.args.elf,function)&~1) or not entry.get('entryRecovered'):
                    raise RuntimeError('Selected function entry was not recovered: '+str(entry))
                if not decoded['summary'].get('functions',{}).get(function):raise RuntimeError('Trace did not execute the requested function')
                row.update(record=sid,seconds=time.perf_counter()-started,transport=quality,summary=decoded['summary'],
                    rawBytes=(record/'capture.bin').stat().st_size,rawSha256=hashlib.sha256((record/'capture.bin').read_bytes()).hexdigest(),
                    captureStart=decoded.get('captureStart'),rccAfter=self.invoke('etm','inspect',target='target')['rcc'])
                if row['rccAfter']!=info['rcc']:raise RuntimeError('Firmware clock registers changed')
            except Exception as error:
                row['error']=str(error)
                # Failed captures need not become the selected decoded record.
                # Locate only this round's new evidence; never retry the action.
                if row.get('captureAttemptUnix'):
                    candidates=[]
                    for session_path in self.records.glob('capture-*/session.json'):
                        metadata=json.loads(session_path.read_text(encoding='utf8'))
                        if metadata.get('created',0)>=row['captureAttemptUnix']:candidates.append((session_path,metadata))
                    if len(candidates)==1:
                        path,metadata=candidates[0];raw=path.parent/'capture.bin'
                        row.update(record=path.parent.name,transport=metadata.get('captureQuality'),captureExtent=metadata.get('captureExtent'))
                        if raw.is_file():row.update(rawBytes=raw.stat().st_size,rawSha256=hashlib.sha256(raw.read_bytes()).hexdigest())
                self.save(self.out/'capture-failure.json',row)
                self.save(self.out/'web-log.json',{'log':self.page('etm','read',selector='#log')['text']})
                raise
            finally:
                # Cleanup is separate from acceptance and never replays capture.
                try:
                    self.ready('#remove-break',timeout=10);self.page('etm','click',selector='#remove-break');self.ready('#run')
                    self.page('etm','click',selector='#run');self.ready('#disconnect')
                except Exception as cleanup:
                    row['cleanupError']=str(cleanup)
                if echo:
                    row['echo']=echo.close();self.save(self.out/f'echo-{n+1:03}.json',row['echo'])
                    window=row.get('transport',{})
                    row['echoInsideWindow']=sum(r['exact'] and window.get('hostStartedUnix',float('inf'))<=r['receivedUnix']<=window.get('hostEndedUnix',0) for r in row['echo']['rows'])
                    if window.get('transport')=='ddr-usb/1':
                        earliest,latest=window['hardwareStartBracketUnix'];duration=window['hardwareSeconds']
                        margin=min(.020,duration*.1);lower,upper=latest+margin,earliest+duration-margin
                        row['guaranteedHardwareWindowUnix']=[lower,upper]
                        row['echoInsideHardwareWindow']=sum(r['exact'] and lower<=r['sentUnix'] and r['receivedUnix']<=upper for r in row['echo']['rows'])
                try:row['closeSeconds']=self.disconnect()
                except Exception as cleanup:
                    row['cleanupError']=str(cleanup)
                    try:self.invoke('etm','disconnect',target='target')
                    except Exception:pass
                rows.append(row);self.save(self.out/'captures.json',rows)
            if row.get('cleanupError') or row.get('echo',{}).get('error'):raise RuntimeError('Capture cleanup/echo failed: '+str(row))
            if self.args.echo and not row['echoInsideWindow']:raise RuntimeError('No verified echo observed inside host capture window')
            if self.args.echo and row.get('transport',{}).get('transport')=='ddr-usb/1' and not row['echoInsideHardwareWindow']:
                raise RuntimeError('No complete exact CDC transaction proven inside hardware window')
            print('capture',n+1,function,row['rawBytes'],'bytes',round(row['seconds'],3),'seconds',flush=True)
        return rows


def arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',required=True);p.add_argument('--artifacts',required=True)
    p.add_argument('--records-root',help='Explicit server record directory; default from runtime metadata')
    p.add_argument('--profile-control',action='store_true',help='Record per-action native USB HTTP round-trip counters')
    p.add_argument('--native-exchange',choices=('auto','on','off','alternate'),default='auto',help='AI controlled A/B only; normal product default is on')
    p.add_argument('--packed-memory',choices=('auto','on','off','alternate'),default='auto',help='AI controlled scalar batching comparison')
    p.add_argument('--register-batch',choices=('auto','on','off','alternate'),default='auto',help='AI controlled grouped-register comparison')
    p.add_argument('--rounds',type=int,default=30);p.add_argument('--capture-rounds',type=int,default=10)
    p.add_argument('--milliseconds',type=int,default=10);p.add_argument('--case-timeout',type=float,default=120)
    p.add_argument('--profile',choices=['stm32f103ze','stm32h743'],default='stm32f103ze')
    p.add_argument('--elf');p.add_argument('--sources');p.add_argument('--hse-mhz',type=float)
    p.add_argument('--functions');p.add_argument('--echo',action='store_true');p.add_argument('--cdc-port')
    p.add_argument('--reset-before',action='store_true',help='Reset and run to entry; does not program Flash')
    a=p.parse_args(argv)
    if not 1<=a.rounds<=1000 or not 0<=a.capture_rounds<=1000 or not 1<=a.milliseconds<=1000:raise ValueError('Invalid finite campaign bounds')
    if a.profile=='stm32h743':
        if not a.elf or not a.functions:p.error('H743 requires --elf and --functions for the firmware actually on the board')
        if a.echo and not a.cdc_port:p.error('H743 echo requires its explicit --cdc-port')
    else:
        a.elf=a.elf or str(ROOT/'prebuilt/golden/f103ze-cdc48.elf')
        a.sources=a.sources or str(ROOT/'prebuilt/golden/source-snapshot')
        a.functions=a.functions or 'cdc_poll,cdc_tx_poll'
    a.hse_mhz=a.hse_mhz if a.hse_mhz is not None else (25 if a.profile=='stm32h743' else 8)
    if not 0<a.hse_mhz<=100: p.error('--hse-mhz must be the actual board oscillator, in (0,100] MHz')
    if not Path(a.elf).is_file():p.error('Target ELF does not exist: '+a.elf)
    if any(not f.strip() for f in a.functions.split(',')):p.error('--functions contains an empty entry')
    a.functions=','.join(f.strip() for f in a.functions.split(','))
    return a


def main(argv=None):
    a=arguments(argv)
    campaign=Stress(a);report={'hardware':True,'noFlash':True,'clockPolicy':'target-firmware-owned','retryFailedRounds':False,
        'profile':a.profile,'targetElf':str(Path(a.elf).resolve()),'targetElfSha256':hashlib.sha256(Path(a.elf).read_bytes()).hexdigest(),
        'hseMHz':a.hse_mhz,'functions':a.functions,'resetBefore':a.reset_before}
    try:
        campaign.initialize();report['lifecycle']=campaign.lifecycle()
        if a.capture_rounds:report['captures']=campaign.captures()
        report['ok']=True
    except Exception as error:
        report.update(ok=False,error=str(error))
        try:campaign.invoke('etm','disconnect',target='target')
        except Exception as cleanup:report['cleanupError']=str(cleanup)
        raise
    finally:campaign.save(campaign.out/'summary.json',report)
    print(json.dumps({'ok':True,'lifecycleRounds':len(report['lifecycle']),'captureRounds':len(report.get('captures',[]))}))
    return 0


if __name__=='__main__':raise SystemExit(main())
