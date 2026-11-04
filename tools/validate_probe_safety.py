"""RAM-only F103 validation for checked DAP and PS failure quarantine.

Caller loads and physically verifies the explicit bit/PS ELF first. Faults use
the separately built diagnostic ELF; malformed-request tests also run on the
production ELF. No MCU Flash/QSPI or target clock-register writes.
"""
import argparse,hashlib,json,random,struct,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from f103_ram_fixture import Fixture
from dap_pipeline_bench import xfer,send,setup,le
from benchmark_probe_stream import HssReader,drain_hss
from probe_flash import Session
from zynq_memory import PhysicalMemory
from probe_build_info import provenance

class Diagnostics:
    def __init__(self,elf,out):
        self.symbols={}
        for line in subprocess.check_output(['arm-none-eabi-nm','--defined-only',str(elf)],text=True).splitlines():
            parts=line.split()
            if len(parts)==3:
                try:self.symbols[parts[2]]=int(parts[0],16)
                except ValueError:pass
        out.mkdir();self.physical=PhysicalMemory(Session(out,Path('E:/Xilinx/SDK/2018.3'),'tcp:127.0.0.1:3121'))
    def read(self,name,n=1):return self.physical.read_words(self.symbols[name],n)
    def arm(self,**values):
        body=''
        for name,value in values.items():
            address=self.symbols[name];assert 0x39000000<=address<0x39100000
            body+=f'physwr -force {address:#x} {value:#x}\n'
        self.physical.run(body+'puts ARMED')

def read_ap(f,request):
    r=xfer(f.tx,f.rx,bytes([5,0,2,request,14]));assert r[:3]==bytes([5,2,1]),r.hex()
    return int.from_bytes(r[-4:],'little')
def set_tar(f,address):
    r=xfer(f.tx,f.rx,bytes([5,0,1,5])+struct.pack('<I',address));assert r==bytes([5,1,1]),r.hex()
def reconnect(f):
    r=xfer(f.tx,f.rx,b'\x02\x01');assert r==b'\x02\x01',r.hex()
    setup(f.tx,f.rx,1000)

def malformed(f,report):
    base=0x20004000;pattern=random.Random(111).randbytes(4096)
    f.mem.write(base,pattern);assert f.mem.read(base,4096)==pattern
    cases=[('short-clock',b'\x11'),('short-transfer',b'\x05\x00\x01\x0d'),
           ('read-overflow-1024',b'\x06\x00\x00\x04\x02'),
           ('read-overflow-65535',b'\x06\x00\xff\xff\x02'),
           ('write-truncated-1023',b'\x06\x00\xff\x03\x0d'+bytes(4091)),
           ('nested-execute',bytes([127,1,127,0])),('nested-queue',bytes([127,1,126,0])),
           ('truncated-swd-sequence',bytes([29,2,128,0])),
           ('truncated-jtag-sequence',bytes([20,1,128])),('truncated-ddr-vendor',bytes([140,1,69,68])),
           ('compound-write-then-overflow',bytes([127,2,5,0,1,13])+struct.pack('<I',0xdeadbeef)+bytes([6,0,0,4,2])),
           ('compound-cumulative-overflow',bytes([127,2,6,0,88,2,15,6,0,88,2,15])),
           ('compound-write-then-short-vendor',bytes([127,2,5,0,1,13])+struct.pack('<I',0xdeadbeef)+bytes([140]))]
    for name,request in cases:
        set_tar(f,base);tar_before=read_ap(f,7)
        reply=xfer(f.tx,f.rx,request);assert reply==b'\xff',(name,reply.hex())
        assert read_ap(f,7)==tar_before,name
        assert f.mem.read(base,4096)==pattern,name
        report['rows'].append(dict(case=name,requestBytes=len(request),reply=reply.hex(),tarUnchanged=True,sramUnchanged=True))
        print(name,'rejected before side effect',flush=True)
    # The largest legal read fills exactly one 4096-byte USB response.
    set_tar(f,base);reply=xfer(f.tx,f.rx,bytes([6,0,255,3,15]))
    tar_after=read_ap(f,7)
    # ADIv5 guarantees at least a 1KiB TAR window; this F103 can advance
    # linearly within 4KiB. Determine the observed boundary independently.
    assert tar_after in [base+1020,base+4092],hex(tar_after)
    window=1024 if tar_after==base+1020 else 4096
    expected=(pattern[:window]*4)[:4092]
    assert reply[:4]==bytes([6,255,3,1])and reply[4:]==expected,(reply[:8].hex(),len(reply))
    report['rows'].append(dict(case='legal-read-1023',responseBytes=len(reply),allValuesExact=True,tarAfter=hex(tar_after),dataSha256=hashlib.sha256(reply[4:]).hexdigest()))
    # Largest write fitting in a 4096-byte request, then exact SRAM check.
    set_tar(f,base);payload=struct.pack('<I',0x12345678)*1022
    reply=xfer(f.tx,f.rx,bytes([6,0,254,3,13])+payload)
    assert reply==bytes([6,254,3,1]),reply.hex()
    expected=bytearray(pattern)
    for i in range(1022):expected[(i*4)%window:(i*4)%window+4]=struct.pack('<I',0x12345678)
    actual=f.mem.read(base,4096);assert actual==expected
    report['rows'].append(dict(case='legal-write-1022',requestBytes=4093,allValuesExact=True))

def restore_failure(f,diag,report):
    base=0x20004000;pattern=random.Random(112).randbytes(4096)
    f.mem.write(base,pattern);assert f.mem.read(base,4096)==pattern
    for stage in [2,3]:
        set_tar(f,base+128);original_csw=read_ap(f,3);original_tar=read_ap(f,7)
        assert f.probe.action(0x31,10,b'\0')[0]==0
        assert f.probe.action(0x32,3,struct.pack('<I',20000000))[0]==0
        cfg=struct.pack('<IBBIBB',24000,0x21,1,base+256,4,4)
        assert f.probe.action(0x32,10,cfg)[0]==0
        drain_hss(f.dev);reader=HssReader(f.dev,pattern[256:260],24000);reader.start()
        try:
            assert f.probe.action(0x32,1)[0]==0;time.sleep(.1)
            before=diag.read('dap_context_snapshot',6);assert before[0]==3,before
            diag.arm(dap_validation_restore_stage=stage,dap_validation_restore_arm=0x112115a5)
            # This target write must NOT execute after the preceding handoff
            # fails. Either possible TAR lies within the backed-up SRAM area.
            request=bytes([5,0,1,13])+struct.pack('<I',0xdeadbeef)
            reply=xfer(f.tx,f.rx,request);assert reply==b'\xff',reply.hex()
            failed=diag.read('dap_context_snapshot',6);assert failed[0]==7,failed
            assert failed[3:]==before[3:] and failed[1]==before[1]+1
            assert xfer(f.tx,f.rx,bytes([5,0,1,15]))==b'\xff'
            recovered=xfer(f.tx,f.rx,b'\x02\x01');assert recovered==b'\x02\x01',recovered.hex()
            after=diag.read('dap_context_snapshot',6);assert after[0]==0,after
            assert read_ap(f,3)==original_csw and read_ap(f,7)==original_tar
            assert f.mem.read(base,4096)==pattern
            report['rows'].append(dict(case='restore-failure',stage=stage,before=before,failed=failed,after=after,
                rejectedTargetWrite=True,rejectedCachedRead=True,originalApContextRestored=True,sramUnchanged=True))
            print('restore stage',stage,'quarantined; explicit Connect restores verified context',flush=True)
        finally:
            reader.quit.set();reader.join(2);assert not reader.is_alive()
            drain_hss(f.dev)
            assert reader.error is None,reader.error
            # Explicit cleanup, even if a prior assertion stopped the test.
            reconnect(f);f.probe.action(0x32,0)

def wait_failures(f,diag,report,kinds=None):
    for kind in kinds or ['scalar-timeout','swj-timeout','scalar-abort','scalar-usb-epoch']:
        reconnect(f)
        write_saved=None
        if kind=='scalar-write-timeout':
            write_saved=f.mem.read(0x20004080,8);set_tar(f,0x20004080)
        before=diag.read('dap_wait_failures')[0]
        diag.arm(dap_validation_wait_mask=1,dap_validation_wait_ms=2000 if kind in ['scalar-abort','scalar-usb-epoch']else 40,
                 dap_validation_wait_arm=0x112115a5)
        request=bytes([18,0])+bytes([255])*32 if kind=='swj-timeout'else bytes([5,0,1,2])
        if write_saved is not None:request=bytes([5,0,1,13])+struct.pack('<I',0xdeadbeef)
        row=dict(case=kind);result={}
        def transact():
            try:
                t=time.perf_counter();send(f.tx,request)
                result['reply']=bytes(f.rx.read(4096,timeout=1500));result['seconds']=time.perf_counter()-t
            except BaseException as exc:result['error']=repr(exc)
            finally:result['finishedPerf']=time.perf_counter()
        thread=threading.Thread(target=transact);thread.start()
        epoch_reset=False;cancel_sent=None
        try:
            if kind in ['scalar-abort','scalar-usb-epoch']:
                # Physical observation proves that this transaction consumed
                # the one-shot hook. A sleep alone does not prove it started.
                deadline=time.monotonic()+1.5
                while diag.read('dap_validation_wait_arm')[0]:
                    assert thread.is_alive() and time.monotonic()<deadline,result
                assert thread.is_alive(),result
                cancel_sent=time.perf_counter()
                if kind=='scalar-abort':send(f.tx,b'\x07')
                else:
                    # WinUSB may absorb SET_CONFIGURATION(1) when already
                    # configured. Use the existing EP0 recovery operation,
                    # which actually advances the firmware's DAP USB epoch.
                    acknowledged=bytes(f.dev.ctrl_transfer(0xc0,0x5a,0x4441,0x5052,4))
                    assert acknowledged==b'DAP\0',acknowledged
                    epoch_reset=True
            thread.join(3);assert not thread.is_alive(),result
            reason=diag.read('dap_wait_last_reason')[0]
            expected=3 if kind.endswith('epoch')else 2 if kind.endswith('abort')else 1
            assert reason==expected,(kind,reason,result)
            if kind.endswith('epoch'):
                assert 'error'in result,'old-epoch reply must not be published'
                f.dev.clear_halt(0x81);f.dev.clear_halt(2)
                from dap_pipeline_bench import drain
                drain(f.rx);epoch_reset=False
            else:
                reply=result['reply'];assert reply==(bytes([18,255])if kind=='swj-timeout'else bytes([5,0,8])),reply.hex()
                if cancel_sent is None:assert result['seconds']<.4,result
                else:assert result['finishedPerf']-cancel_sent<.4,result
                assert diag.read('dap_context_snapshot',6)[0]&4
                assert xfer(f.tx,f.rx,bytes([5,0,1,15]))==b'\xff'
            reconnect(f)
            assert f.mem.word(0xe000ed00)==0x411fc231
            if write_saved is not None:
                assert f.mem.read(0x20004080,8)==struct.pack('<I',0xdeadbeef)+write_saved[4:]
                f.mem.write(0x20004080,write_saved);assert f.mem.read(0x20004080,8)==write_saved
                row['targetWriteCommittedOnceDespiteError']=True;row['noAutomaticReplay']=True
            row.update(reason=reason,failuresAdded=diag.read('dap_wait_failures')[0]-before,
                responseHex=result.get('reply',b'').hex(),responseSeconds=result.get('seconds'),
                oldEpochError=result.get('error'),explicitRecoveryPassed=True)
            report['rows'].append(row);print(kind,'bounded failure/recovery passed',flush=True)
        finally:
            thread.join(3);assert not thread.is_alive()
            if epoch_reset:
                # Match the existing EP0 recovery contract: reset the host's
                # endpoint toggles too, then discard retired-session input.
                f.dev.clear_halt(0x81);f.dev.clear_halt(2)
                from dap_pipeline_bench import drain
                drain(f.rx)
            reconnect(f)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['malformed','faults','write-fault'],required=True);p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--bit',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--repeats',type=int,choices=range(1,11),default=1)
    a=p.parse_args()
    if not a.execute:print(json.dumps(dict(hardwareAccess=False,stage=a.stage)));return
    a.out.mkdir(parents=True,exist_ok=False);report=dict(stage=a.stage,rows=[],passed=False,identity=provenance(a.bit,a.elf),targetFlashWrites=False,probeQspiWrites=False)
    try:
        diag=Diagnostics(a.elf,a.out/'physical')
        if a.stage!='malformed':assert 'dap_validation_wait_arm'in diag.symbols,'Diagnostic ELF required'
        with Fixture(a.out/'fixture')as f:
            if a.stage=='malformed':malformed(f,report)
            else:
                for repeat in range(a.repeats):
                    start=len(report['rows'])
                    if a.stage=='write-fault':wait_failures(f,diag,report,['scalar-write-timeout'])
                    else:restore_failure(f,diag,report);wait_failures(f,diag,report)
                    for row in report['rows'][start:]:row['repeat']=repeat
        report['passed']=True
    except BaseException as exc:report['error']=repr(exc);raise
    finally:(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
