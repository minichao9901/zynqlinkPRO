"""F103ZE session/flight acceptance. Explicit execution; no Flash/QSPI writes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import base64
import secrets
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'etm-service/tools')]


def preflight(out):
    from dap_pipeline_bench import open_dap,setup
    from test_probe_board import Memory
    from probe_stream import Probe
    from target_snapshot import snapshot
    import usb.util
    dev,tx,rx=open_dap();probe=None
    try:
        probe=Probe()
        streams={}
        for name,cmd in [('rtt',0x31),('hss',0x32)]:
            rc,w=probe.action(cmd,2);streams[name]=dict(rc=rc,words=list(w))
            if w[0]&1:raise RuntimeError(name+' active: refusing to take over')
        import struct
        ddr=struct.unpack('<44I',bytes(dev.ctrl_transfer(0xc0,0x63,0,0x4554,176,timeout=2000)))
        if ddr[4+2]&17 or ddr[42]&0xffff:raise RuntimeError('DDR/DMA/download active')
        setup(tx,rx,10000);m=Memory(tx,rx)
        clock=snapshot(m);assert clock['name']=='STM32F103'
        fpctrl=m.word(0xe0002000);comparators=((fpctrl>>4)&15)|((fpctrl>>8)&0x70)
        comparators+=(fpctrl>>8)&15
        assert comparators<=128
        fpb=m.read(0xe0002000,8+4*comparators)
        flash=m.read(0x08000000,512<<10)
        assert m.read(0x08000000,len(flash))==flash
        (out/'flash-private.bin').write_bytes(flash)
        (out/'fpb-private.bin').write_bytes(fpb)
        report=dict(passed=True,streams=streams,ddr=list(ddr),clock=clock,
            dhcsr=hex(m.word(0xe000edf0)),demcr=hex(m.word(0xe000edfc)),
            fpbBytes=len(fpb),fpbSha256=hashlib.sha256(fpb).hexdigest(),
            flashSha256=hashlib.sha256(flash).hexdigest(),flashBytes=len(flash),time=time.time())
        return report
    finally:
        if probe:probe.close()
        usb.util.dispose_resources(dev)


def service_memory(a):
    sys.path.insert(0,str(ROOT))
    from toolbox import Client
    from f103_ram_fixture import Fixture
    from dap_pipeline_bench import setup,xfer
    from test_probe_board import Memory
    client=Client(a.runtime,30);owner=secrets.token_hex(16);epoch=None
    rows=[];data=bytes((i*17+11)&255 for i in range(16384));address=0x20001000
    def rpc(action,**value):
        r=client.native('usb',action,dict(owner=owner,resourceEpoch=epoch,**value))
        assert r['ok'],r
        return r['value']
    class Tx:
        def write(self,data,timeout=None):return rpc('write',endpoint=2,data=base64.b64encode(bytes(data)).decode())['bytesWritten']
    class Rx:
        def read(self,length,timeout=None):
            result=rpc('read',endpoint=0x81,length=length,commandPending=timeout is None or timeout>80)
            if result['timedOut']:
                import usb.core
                raise usb.core.USBTimeoutError('service read timeout')
            return base64.b64decode(result['data'])
    with Fixture(a.out/'fixture') as f:
        setup(f.tx,f.rx,10000)
        for repeat in range(a.rounds):
            start=time.perf_counter();f.mem.write(address,data);write=time.perf_counter()-start
            start=time.perf_counter();raw=f.mem.read(address,len(data));read=time.perf_counter()-start
            assert raw==data;rows.append(dict(path='direct',repeat=repeat,readSeconds=read,writeSeconds=write))
        f.release_dap()
        try:
            opened=rpc('open');epoch=opened['resourceEpoch'];rpc('claim',number=0)
            tx,rx=Tx(),Rx();setup(tx,rx,10000)
            for repeat in range(a.rounds):
                start=time.perf_counter();rpc('memory-write',transport='swd',address=address,data=base64.b64encode(data).decode());write=time.perf_counter()-start
                start=time.perf_counter();raw=base64.b64decode(rpc('memory-read',transport='swd',address=address,length=len(data))['data']);read=time.perf_counter()-start
                assert raw==data;rows.append(dict(path='service',repeat=repeat,readSeconds=read,writeSeconds=write))
            for i in range(a.switches):
                old=epoch;rpc('close');epoch=rpc('open')['resourceEpoch'];rpc('claim',number=0)
                setup(tx,rx,10000)
                assert Memory(tx,rx).word(0xe000ed00)==0x411fc231
                try:
                    client.native('usb','memory-write',dict(owner=owner,resourceEpoch=old,transport='swd',address=address,data='AAAAAA=='))
                except RuntimeError:pass
                else:raise AssertionError('stale epoch accepted')
                if i%100==0:print('session cycles',i,flush=True)
            assert base64.b64decode(rpc('memory-read',transport='swd',address=address,length=len(data))['data'])==data
        finally:rpc('close')
    return dict(passed=True,rows=rows,switches=a.switches,bytes=len(data),swdHz=10000000,restored=f.report)


def board_control(a):
    import struct
    from f103_ram_fixture import Fixture
    from dap_pipeline_bench import setup,send,xfer
    from benchmark_probe_stream import HssReader
    from test_probe_board import stop,drain_hss
    report={'rows':[]}
    with Fixture(a.out/'fixture') as f:
        def stop_hss():
            for _ in range(200):
                rc,_=f.probe.action(0x32,0)
                if rc==0:return
                assert rc==-7,rc
                time.sleep(.005)
            raise RuntimeError('HSS STOP did not drain through its reader')
        assert f.probe.control.correlated,'new HID nonce protocol required'
        setup(f.tx,f.rx,10000)
        base=0x20004000;before=f.mem.read(base,64);f.mem.address(base)
        queued=bytes([126,1,5,0,1,13])+struct.pack('<I',0x12345678)
        for _ in range(16):send(f.tx,queued)
        for _ in range(16):assert bytes(f.rx.read(4096,timeout=2000))==b'\xff'
        assert f.mem.read(base,64)==before
        report['fullQueueRejectedWithoutWrites']=True
        pattern=bytes((i*29+3)&255 for i in range(4096));f.mem.write(base,pattern)
        for speed in (10000000,50000000,60000000):
            setup(f.tx,f.rx,speed//1000)
            assert f.probe.action(0x31,7,struct.pack('<IHBB',speed,1024,0,1))[0]==0
            period=24000
            cfg=struct.pack('<IBB',period,0,8)+b''.join(struct.pack('<IBB',base+4*i,4,4) for i in range(8))
            assert f.probe.action(0x32,10,cfg)[0]==0
            reader=HssReader(f.dev,pattern[:32],period);reader.start()
            try:
                assert f.probe.action(0x32,1)[0]==0
                time.sleep(.25)
                for _ in range(100):assert f.mem.word(0xe000ed00)==0x411fc231
                time.sleep(.25)
                stop_hss()
                time.sleep(.1);reader.quit.set();reader.join(2);drain_hss(f.dev,reader.consume)
                assert reader.error is None,reader.error
                rc,metrics=f.probe.action(0x32,11)
                assert rc==0 and reader.samples==metrics[3]
                assert reader.samples>100
                report['rows'].append(dict(speedHz=speed,samples=reader.samples,skipped=metrics[4],
                    timelineSkipped=reader.timeline_skips,yields=metrics[7],cadenceGridExact=True,valuesExact=True))
                # Full reconnect gracefully terminates the old stream before
                # the first link-changing command; no resume mid-handshake.
                reader2=HssReader(f.dev,pattern[:32],period);reader2.start()
                try:
                    assert f.probe.action(0x32,1)[0]==0;time.sleep(.05)
                    setup(f.tx,f.rx,10000)
                    assert f.mem.word(0xe000ed00)==0x411fc231
                    assert not f.probe.action(0x32,2)[1][0]&1
                finally:
                    stop_hss();time.sleep(.1);reader2.quit.set();reader2.join(2)
                assert reader2.error is None,reader2.error
                report['rows'][-1]['fullReconnectStoppedOldStream']=True
            finally:
                stop(f.probe,f.dev);reader.quit.set();reader.join(2)
    report.update(passed=True,restored=f.report);return report


def rtt_reconnect(a):
    import struct,serial,serial.tools.list_ports
    from f103_ram_fixture import Fixture
    from dap_pipeline_bench import setup
    from benchmark_rtt_forward import Reader
    ports=[p.device for p in serial.tools.list_ports.comports() if (p.vid,p.pid)==(0x0d28,0x0204)]
    assert len(ports)==1,ports
    report={'rows':[]}
    with Fixture(a.out/'fixture') as f:
        for speed in (50000000,60000000):
            for repeat in range(a.rounds):
                f.prepare_rtt();reader=None
                with serial.Serial(ports[0],115200,timeout=.025) as com:
                    com.reset_input_buffer();reader=Reader(com);reader.start()
                    try:
                        config=struct.pack('<IHBB',speed,1024,0,1)
                        start=struct.pack('<IIB',0x20000200,256,0)
                        assert f.probe.action(0x31,7,config)[0]==0
                        assert f.probe.action(0x31,1,start)[0]==0
                        f.resume();time.sleep(.3)
                        setup(f.tx,f.rx,10000)
                        rc,stopped=f.probe.action(0x31,2)
                        assert rc==0 and not stopped[0]&1 and stopped[3]>0,stopped
                        assert f.mem.word(0xe000ed00)==0x411fc231
                        assert f.probe.action(0x31,7,config)[0]==0
                        assert f.probe.action(0x31,1,start)[0]==0
                        time.sleep(.3);published=f.halt_producer()
                        until=time.monotonic()+5
                        while reader.count<published and reader.error is None and time.monotonic()<until:time.sleep(.01)
                        assert f.probe.action(0x31,0)[0]==0
                        time.sleep(.05);reader.quit.set();reader.join(2)
                        assert reader.error is None and reader.count==published and not reader.pending,(reader.error,reader.count,published)
                        report['rows'].append(dict(speedHz=speed,repeat=repeat,published=published,received=reader.count,
                            sequenceExact=True,oldStreamStopped=True,restartedWithoutReload=True,hidCorrelated=f.probe.control.correlated))
                    finally:
                        f.mem.write_word(0xe000edf0,0xa05f0003);f.probe.action(0x31,0)
                        reader.quit.set();reader.join(2)
    report.update(passed=True,restored=f.report);return report


def web_memory(a):
    from types import SimpleNamespace
    sys.path.insert(0,str(ROOT))
    from tools.validate_f103_main_web import Web
    from toolbox import pack_file
    from f103_ram_fixture import Fixture
    report={'rows':[]};address=0x20001000;data=bytes((i*13+29)&255 for i in range(16384))
    w=Web(SimpleNamespace(runtime=a.runtime,artifacts=a.out/'web',case_timeout=120,elf=ROOT/'prebuilt/golden/f103ze-cdc48.elf'))
    with Fixture(a.out/'fixture') as f:
        f.release_dap();connected=False
        try:
            w.page('dbg','show');w.page('dbg','describe')
            w.set('dbg','#d-backend','webusb');w.set('dbg','#d-clock','10000')
            w.invoke('dbg','loadElfBuffer',dict(kind='buffer',**pack_file(w.args.elf)),w.args.elf.name)
            w.invoke('dbg','connect');connected=True;w.page('dbg','describe',target='session')
            for repeat in range(a.rounds):
                start=time.perf_counter();w.invoke('dbg','memWrite',address,{'$base64':base64.b64encode(data).decode()},target='session');written=time.perf_counter()-start
                start=time.perf_counter();value=bytes(w.invoke('dbg','memRead',address,len(data),target='session')['$bytes']);read=time.perf_counter()-start
                assert value==data
                report['rows'].append(dict(repeat=repeat,bytes=len(data),writeSeconds=written,readSeconds=read,
                    writeMBps=len(data)/written/1e6,readMBps=len(data)/read/1e6,byteExact=True))
        finally:
            if connected:w.invoke('dbg','disconnect')
    report.update(passed=True,restored=f.report,swdHz=10000000,scope='real Web debugger memRead/memWrite including page CLI dispatch; write includes existing verification');return report


def trace_address_guard(a):
    from f103_ram_fixture import Fixture
    from zynq_la import Session,CaptureError
    report={'rows':[]}
    with Fixture(a.out/'fixture') as f:
        base=0x20004000;before=f.mem.read(base,64)
        for operation in ('read','write'):
            sent=[]
            class CorruptedOut:
                def write(self,data,timeout=None):
                    data=bytes(data)
                    # Transport fault fixture: truncate only the initial
                    # address setup. Real PS preflight returns FF.
                    actual=b'\x05' if not sent else data
                    sent.append(actual.hex());return f.tx.write(actual,timeout=timeout)
            f.mem.address(base);s=Session();s.out=CorruptedOut();s.inp=f.rx
            try:
                if operation=='read':s._dap_read32(0xe000ed04)
                else:s._dap_write32(0xe000edf0,0xa05f0001)
            except CaptureError as error:assert 'TAR' in str(error)
            else:raise AssertionError('failed address setup was ignored')
            assert sent==['05'],sent
            assert f.mem.read(base,64)==before
            report['rows'].append(dict(operation=operation,sent=sent,noDrwIssued=True,sramUnchanged=True))
    report.update(passed=True,restored=f.report,injection='host adapter truncates address command; real PS response; not electrical fault')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['preflight','service-memory','board-control','rtt-reconnect','web-memory','trace-address-guard'],required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--runtime');p.add_argument('--rounds',type=int,default=3);p.add_argument('--switches',type=int,default=0)
    a=p.parse_args()
    if not a.execute:print(json.dumps(dict(stage=a.stage,hardwareAccess=False)));return
    a.out.mkdir(parents=True,exist_ok=False)
    result=preflight(a.out) if a.stage=='preflight' else {'board-control':board_control,'rtt-reconnect':rtt_reconnect,'web-memory':web_memory,'service-memory':service_memory,'trace-address-guard':trace_address_guard}[a.stage](a)
    (a.out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('ddr','streams')},ensure_ascii=False))


if __name__=='__main__':main()
