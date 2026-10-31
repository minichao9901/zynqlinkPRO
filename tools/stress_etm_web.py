"""AI drives real Web buttons: probe lifecycle, changed entries, capture and CDC.

No Flash programming, PLL/AHB changes or automatic retry of failed rounds.
Run against a loaded, identity-verified probe and the matching F103 target ELF.
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
from tools.f103_stream_acceptance import Streams
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
        self.set('etm','#hse','8');self.set('etm','#target-profile','stm32f103ze')
        self.set('etm','#reset-before',False);self.set('etm','#entry-before',True)
        self.set('etm','#duration',str(self.args.milliseconds));self.set('etm','#auto-decode',True)
        if self.args.sources:
            root=Path(self.args.sources)
            files=[pack_file(p,root.name+'/'+p.relative_to(root).as_posix()) for p in sorted(root.rglob('*')) if p.is_file()]
            self.page('etm','upload',selector='#sources-files',files=files)
            self.wait('etm','#sources-label','已保存本地快照');self.ready('#choose-elf')

    def connect(self):
        start=time.perf_counter();self.page('etm','click',selector='#connect');self.ready('#disconnect')
        info=self.invoke('etm','inspect',target='target')
        if info['profile']!='stm32f103ze' or info.get('clockError'):raise RuntimeError('Unexpected target: '+str(info))
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
        ports=[p.device for p in comports() if p.vid==0xf055 and p.pid==0x1031]
        if len(ports)!=1:raise ValueError('Expected one F103 CDC target, got '+str(ports))
        rows=[];functions=self.args.functions.split(',')
        for n in range(self.args.capture_rounds):
            info,opened=self.connect();function=functions[n%len(functions)];echo=None
            row={'round':n+1,'function':function,'before':info,'openSeconds':opened}
            try:
                if self.args.echo:
                    self.page('etm','click',selector='#run');self.ready('#disconnect')
                    echo=Echo(ports[0]);echo.start()
                self.set('etm','#break-command','b '+function)
                self.page('etm','click',selector='#add-break');self.ready('#start')
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
                        if sid and sid!=previous:break
                    time.sleep(.05)
                else:raise TimeoutError('Capture did not finish: '+status)
                self.invoke('etm','waitForDisplay',target='history')
                record=ROOT/'etm-service/records'/sid
                meta=json.loads((record/'session.json').read_text(encoding='utf8'))
                decoded=json.loads((record/'decoded.json').read_text(encoding='utf8'))
                quality=meta.get('captureQuality') or {}
                if quality.get('loss') or not quality.get('synced') or not quality.get('ended'):
                    raise RuntimeError('Transport quality did not pass: '+str(quality))
                if decoded['summary']['packetIssues']:raise RuntimeError('Decoder packet errors')
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
                    for session_path in (ROOT/'etm-service/records').glob('capture-*/session.json'):
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
                try:row['closeSeconds']=self.disconnect()
                except Exception as cleanup:
                    row['cleanupError']=str(cleanup)
                    try:self.invoke('etm','disconnect',target='target')
                    except Exception:pass
                rows.append(row);self.save(self.out/'captures.json',rows)
            if row.get('cleanupError') or row.get('echo',{}).get('error'):raise RuntimeError('Capture cleanup/echo failed: '+str(row))
            if self.args.echo and not row['echoInsideWindow']:raise RuntimeError('No verified echo observed inside host capture window')
            print('capture',n+1,function,row['rawBytes'],'bytes',round(row['seconds'],3),'seconds',flush=True)
        return rows


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',required=True);p.add_argument('--artifacts',required=True)
    p.add_argument('--rounds',type=int,default=30);p.add_argument('--capture-rounds',type=int,default=10)
    p.add_argument('--milliseconds',type=int,default=10);p.add_argument('--case-timeout',type=float,default=120)
    p.add_argument('--elf',default=str(ROOT/'prebuilt/golden/f103ze-cdc48.elf'))
    p.add_argument('--sources',default=str(ROOT/'prebuilt/golden/source-snapshot'))
    p.add_argument('--functions',default='cdc_poll,cdc_tx_poll');p.add_argument('--echo',action='store_true')
    a=p.parse_args(argv)
    if not 1<=a.rounds<=1000 or not 0<=a.capture_rounds<=1000 or not 1<=a.milliseconds<=1000:raise ValueError('Invalid finite campaign bounds')
    campaign=Stress(a);report={'hardware':True,'noFlash':True,'clockPolicy':'target-firmware-owned','retryFailedRounds':False}
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
