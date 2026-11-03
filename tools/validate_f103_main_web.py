"""Sequential F103 main Web acceptance. Hardware actions require --execute.

Use a verified idle probe, a full private target Flash backup and a live toolbox
browser worker. Never writes probe QSPI or target clock registers directly.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.f103_web_acceptance import Acceptance
from tools.f103_stream_acceptance import symbol
from toolbox import pack_file


class Web(Acceptance):
    def invoke(self, page, method, *args, target='view'):
        return self.page(page, 'invoke', method=method, args=list(args), target=target)

    def set(self, page, selector, value):
        return self.page(page, 'set', selector=selector, value=value)

    def download(self, page, path):
        items=self.page(page,'downloads');assert items
        item=items[-1];raw=bytearray()
        while len(raw)<item['bytes']:
            v=self.page(page,'download',id=item['id'],offset=len(raw),length=min(1<<20,item['bytes']-len(raw)))
            raw.extend(base64.b64decode(v['base64']))
        path.write_bytes(raw);self.page(page,'discard',id=item['id'])
        return bytes(raw)

    def flash(self):
        self.page('flash','show')
        self.page('flash','describe')
        self.set('flash','#f-chip','stm32f103')
        self.set('flash','#f-speed','10000')
        self.set('flash','#f-verify',True);self.set('flash','#f-reset',True)
        self.page('flash','upload',selector='@file:view._fileInput',files=[pack_file(self.args.elf)])
        rows=[]
        for repeat in range(self.args.rounds):
            begin=time.perf_counter();self.invoke('flash','flash')
            state=self.invoke('flash','summary')
            elapsed=time.perf_counter()-begin
            assert not state['busy'] and '校验通过' in state['result'] and '已复位运行' in state['result'],state
            rows.append(dict(repeat=repeat,wallSeconds=elapsed,state=state))
            self.save(self.out/'results.json',dict(rows=rows))
        self.invoke('flash','readIdcode')
        log=self.page('flash','read',selector='#f-log')['text']
        assert '0x414' in log and '512' in log,log
        return dict(passed=True,rows=rows,medianSeconds=statistics.median(r['wallSeconds'] for r in rows),log=log)

    def debug(self):
        self.page('dbg','show');self.page('dbg','describe')
        self.set('dbg','#d-backend','webusb');self.set('dbg','#d-clock','10000')
        self.invoke('dbg','loadElfBuffer',dict(kind='buffer',**pack_file(self.args.elf)),Path(self.args.elf).name)
        rows=[];connected=False
        try:
            self.invoke('dbg','connect');connected=bool(self.invoke('dbg','summary')['connected'])
            assert connected,'Debug connection failed; inspect page log'
            self.page('dbg','describe',target='session')
            self.invoke('dbg','halt',target='session');self.invoke('dbg','refreshAll')
            state=self.invoke('dbg','summary');assert state['connected'] and state['halted'],state
            old=self.invoke('dbg','readReg','r12',target='session')
            try:
                self.invoke('dbg','writeReg','r12',old^0x55aa55aa,target='session')
                assert self.invoke('dbg','readReg','r12',target='session')==old^0x55aa55aa
            finally:
                self.invoke('dbg','writeReg','r12',old,target='session')
                assert self.invoke('dbg','readReg','r12',target='session')==old
            address=0x20008000;length=16384
            original=bytes(self.invoke('dbg','memRead',address,length,target='session')['$bytes'])
            data=bytes((i*13+29)&255 for i in range(length))
            try:
                for repeat in range(self.args.rounds):
                    start=time.perf_counter()
                    self.invoke('dbg','memWrite',address,{'$base64':base64.b64encode(data).decode()},target='session')
                    written=time.perf_counter()-start
                    start=time.perf_counter();read=bytes(self.invoke('dbg','memRead',address,length,target='session')['$bytes'])
                    elapsed=time.perf_counter()-start;assert read==data
                    rows.append(dict(repeat=repeat,bytes=length,readSeconds=elapsed,writeSeconds=written,readMBps=length/elapsed/1e6,writeMBps=length/written/1e6,byteExact=True))
                    self.save(self.out/'sram-results.json',rows)
            finally:
                self.invoke('dbg','memWrite',address,{'$base64':base64.b64encode(original).decode()},target='session')
                assert bytes(self.invoke('dbg','memRead',address,length,target='session')['$bytes'])==original
            pc=self.invoke('dbg','readReg','pc',target='session')
            self.invoke('dbg','step',target='session');self.invoke('dbg','refreshAll')
            stepped=self.invoke('dbg','readReg','pc',target='session')
            assert self.invoke('dbg','summary')['halted']
            self.invoke('dbg','backtrace',target='session');self.invoke('dbg','locals',target='session')
            entry=symbol(self.args.elf,'cdc_poll')&~1
            self.invoke('dbg','bpClear',target='session');self.invoke('dbg','bpAdd',entry,'main hardware validation',target='session')
            self.invoke('dbg','cont',target='session')
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                self.invoke('dbg','refreshAll');state=self.invoke('dbg','summary')
                if state['halted']:break
                time.sleep(.05)
            assert state['halted'],state
            hit=self.invoke('dbg','readReg','pc',target='session');assert hit==entry,(hex(hit),hex(entry))
            return dict(passed=True,rows=rows,registerRestored=True,sramRestored=True,pcBefore=pc,pcAfterStep=stepped,breakpointPc=hit,state=state)
        finally:
            if connected:
                self.invoke('dbg','bpClear',target='session');self.invoke('dbg','cont',target='session');self.invoke('dbg','disconnect')

    def serial(self):
        from serial.tools.list_ports import comports
        port=next(p.device for p in comports() if p.vid==0xf055 and p.pid==0x1031)
        self.page('serial','show');self.page('serial','describe')
        self.set('serial','#s-ts',False);self.set('serial','#s-dtr',True);self.set('serial','#s-eol','none')
        self.invoke('serial','refreshPorts')
        options=next(c['options'] for c in self.page('serial','describe')['controls'] if c['selector']=='#s-port')
        chosen=[c for c in options if port in c['label']];assert len(chosen)==1,options
        self.set('serial','#s-port',chosen[0]['value']);self.invoke('serial','connect')
        rows=[]
        try:
            assert self.invoke('serial','send','FLUSH_LINE\n');time.sleep(.1)
            for command,expected in [('PING\n','PONG'),('INFO\n','sysclk=48000000')]:
                self.page('serial','click',selector='#s-clear');assert self.invoke('serial','send',command)
                answer=self.wait('serial','#s-rx',expected)['text'];rows.append(dict(command=command,answer=answer))
            payload='ABCDEFGHIJKLMNOP0123456789abcdef'*256
            for repeat in range(self.args.rounds):
                self.page('serial','click',selector='#s-clear')
                start=time.perf_counter();assert self.invoke('serial','send',payload)
                deadline=time.monotonic()+10
                while True:
                    text=self.page('serial','read',selector='#s-rx')['text']
                    if len(text)>=len(payload):break
                    assert time.monotonic()<deadline,(len(text),len(payload))
                elapsed=time.perf_counter()-start
                self.invoke('serial','save');raw=self.download('serial',self.out/f'echo-{repeat}.txt')
                assert raw==payload.encode(),(len(raw),len(payload))
                rows.append(dict(repeat=repeat,bytes=len(raw),wallSeconds=elapsed,MBps=len(raw)/elapsed/1e6,byteExact=True))
            assert self.invoke('serial','send','FLUSH_LINE\n');time.sleep(.1)
            self.page('terminal','show');self.page('terminal','describe')
            self.page('terminal','click',selector='#t-clear')
            self.invoke('serial','send','PING\n')
            time.sleep(.2);self.invoke('terminal','save')
            terminal=self.download('terminal',self.out/'terminal.txt');assert b'PONG' in terminal,terminal
            return dict(passed=True,rows=rows,terminalReceivedPong=True,terminalExportBytes=len(terminal))
        finally:self.invoke('serial','close',target='session')

    def rtt(self):
        import struct
        from f103_ram_fixture import Fixture
        from dap_pipeline_bench import open_dap,setup,xfer
        from test_probe_board import Memory
        import usb.util
        rows=[]
        with Fixture(self.out/'fixture') as f:
            up=b'F103_REAL_WEB_RTT_UP_0123456789abcdef\n'*100
            down=b'F103_REAL_WEB_RTT_DOWN_89abcdef'
            cb=struct.pack('<16sII',b'SEGGER RTT',1,1)+struct.pack('<6I',0,0x20001000,8192,len(up),0,0)+struct.pack('<6I',0,0x20003000,4096,0,0,0)
            f.mem.write(0x20000200,cb);f.mem.write(0x20001000,up)
            assert xfer(f.tx,f.rx,[3])==b'\x03\x00';f.release_dap()
            self.page('rtt','show');self.page('rtt','describe')
            self.set('rtt','#r-target','swd');self.set('rtt','#r-usb-clock','10000')
            self.set('rtt','#r-addr','0x20000200');self.set('rtt','#r-poll','5')
            start=time.perf_counter();self.invoke('rtt','connectProbe')
            try:
                deadline=time.monotonic()+10
                while True:
                    state=self.invoke('rtt','summary')
                    assert state['connected'] and state['running'],state
                    if state['stats']['bytes']>=len(up):break
                    assert time.monotonic()<deadline,state
                    time.sleep(.02)
                elapsed=time.perf_counter()-start
                self.page('rtt','describe',target='rtt')
                self.invoke('rtt','writeDown',0,{'$base64':base64.b64encode(down).decode()},target='rtt')
                exported=self.invoke('rtt','saveRaw');raw=self.download('rtt',self.out/'up.bin')
                assert raw==up and not state['stats']['lost'] and not state['stats'].get('corrupt',0),(len(raw),state)
                rows.append(dict(upBytes=len(up),upExact=True,downBytes=len(down),connectAndDrainSeconds=elapsed,state=state))
            finally:self.invoke('rtt','disconnect')
            d,tx,rx=open_dap()
            try:
                setup(tx,rx,10000);m=Memory(tx,rx)
                assert m.word(0x2000023c)==len(down)
                assert m.read(0x20003000,len(down))==down
                rows[-1]['downExact']=True
            finally:usb.util.dispose_resources(d)
        return dict(passed=True,rows=rows)


def cli_flash(a,out):
    exe=ROOT/'prebuilt/golden/host/openocd/openocd.exe'
    scripts=exe.parent/'scripts';rows=[]
    cfg=out/'stm32.cfg'
    cfg.write_text('source [find interface/cmsis-dap.cfg]\ncmsis_dap_backend usb_bulk\ncmsis_dap_vid_pid 0x0d28 0x0204\ntransport select swd\nsource [find target/stm32f1x.cfg]\nadapter speed 10000\nreset_config none\n$_TARGETNAME configure -work-area-backup 1\n')
    for repeat in range(a.rounds):
        argv=[str(exe),'-s',str(scripts),'-f',str(cfg),'-c',f'program {{{a.elf.resolve().as_posix()}}} verify reset exit']
        start=time.perf_counter();r=subprocess.run(argv,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        elapsed=time.perf_counter()-start;(out/f'round-{repeat}.log').write_text(r.stdout+r.stderr,encoding='utf-8')
        rows.append(dict(repeat=repeat,wallSeconds=elapsed,returncode=r.returncode,argv=argv))
        (out/'results.json').write_text(json.dumps(rows,indent=2))
        assert r.returncode==0,r.stderr
    return dict(passed=True,rows=rows,medianSeconds=statistics.median(r['wallSeconds'] for r in rows))


def cli_memory(a,out):
    from dap_pipeline_bench import open_dap,setup
    from test_probe_board import Memory
    from target_snapshot import snapshot
    import usb.util
    d,tx,rx=open_dap();m=Memory(tx,rx);backup=None;initial=None;report=dict(rows=[])
    try:
        setup(tx,rx,10000);initial=m.word(0xe000edf0);report['clockBefore']=snapshot(m)
        m.write_word(0xe000edf0,0xa05f0003);address=0x20008000;length=16384
        backup=m.read(address,length);(out/'sram-private.bin').write_bytes(backup)
        data=bytes((i*13+29)&255 for i in range(length))
        for repeat in range(a.rounds):
            start=time.perf_counter();m.write(address,data);written=time.perf_counter()-start
            start=time.perf_counter();raw=m.read(address,length);elapsed=time.perf_counter()-start
            assert raw==data
            report['rows'].append(dict(repeat=repeat,bytes=length,readSeconds=elapsed,writeSeconds=written,readMBps=length/elapsed/1e6,writeMBps=length/written/1e6,byteExact=True))
        report['passed']=True
    finally:
        if backup is not None:
            m.write(address,backup);report['sramRestored']=m.read(address,length)==backup;assert report['sramRestored']
        report['clockAfter']=snapshot(m);assert report['clockBefore']==report['clockAfter']
        if initial is not None and not initial&(1<<17):m.write_word(0xe000edf0,0xa05f0001)
        usb.util.dispose_resources(d)
        (out/'result.json').write_text(json.dumps(report,indent=2))
    return report


def cli_serial(a,out):
    import serial
    from serial.tools.list_ports import comports
    port=next(p.device for p in comports() if p.vid==0xf055 and p.pid==0x1031)
    rows=[];payload=('ABCDEFGHIJKLMNOP0123456789abcdef'*256).encode()
    with serial.Serial(port,115200,timeout=.05) as com:
        com.dtr=True
        for repeat in range(a.rounds):
            com.reset_input_buffer();start=time.perf_counter();com.write(payload);raw=bytearray()
            while len(raw)<len(payload) and time.perf_counter()-start<10:raw.extend(com.read(len(payload)-len(raw)))
            elapsed=time.perf_counter()-start;assert raw==payload,(len(raw),len(payload))
            rows.append(dict(repeat=repeat,bytes=len(raw),wallSeconds=elapsed,MBps=len(raw)/elapsed/1e6,byteExact=True))
    return dict(passed=True,rows=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['cli-flash','cli-memory','cli-serial','web-flash','web-debug','web-serial','web-rtt'],required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--runtime')
    p.add_argument('--elf',type=Path,default=ROOT/'prebuilt/golden/f103ze-cdc48.elf')
    p.add_argument('--rounds',type=int,default=3);p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not a.execute:print(json.dumps(dict(stage=a.stage,hardwareAccess=False)));return
    if a.stage.startswith('web-') and not a.runtime:p.error('Web stages require --runtime')
    if a.stage.startswith('cli-'):
        a.out.mkdir(parents=True,exist_ok=False);result=globals()[a.stage.replace('-','_')](a,a.out)
    else:
        w=Web(SimpleNamespace(runtime=a.runtime,artifacts=a.out,case_timeout=240,elf=a.elf,rounds=a.rounds))
        try:result=getattr(w,a.stage[4:])()
        except BaseException as exc:
            w.save(w.out/'failure.json',dict(error=repr(exc)));raise
    (a.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
