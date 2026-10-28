"""Preserved-SRAM frequency acceptance, with actual clock/CFG recorded per point."""
from pathlib import Path
import argparse,hashlib,json,random,struct,time
import usb.util
from dap_pipeline_bench import open_dap,setup,xfer
from dap_transport_control import snapshot,engine_snapshot
from test_probe_board import Memory
from probe_build_info import provenance,swd_clock_details

def recover(dev,inp):
    assert bytes(dev.ctrl_transfer(0xc0,0x5a,0x4441,0x5052,4,timeout=3000))==b'DAP\0'
    dev.clear_halt(0x81);dev.clear_halt(0x02)
    for _ in range(64):
        try:inp.read(4096,timeout=30)
        except Exception as exc:
            if isinstance(exc,__import__('usb.core',fromlist=['USBTimeoutError']).USBTimeoutError):break
            raise

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speeds',default='250,500,1000,2000,5000,10000,15000,20000,25000,30000,35000,40000,50000,60000')
    ap.add_argument('--loops',type=int,default=3);ap.add_argument('--size',type=int,default=1024)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--bit',type=Path);ap.add_argument('--elf',type=Path)
    a=ap.parse_args();assert 0<a.size<=4096 and a.loops>0
    a.output.parent.mkdir(parents=True,exist_ok=True)
    dev,out,inp=open_dap();mem=Memory(out,inp);backup=initial=None;base=0x20004000
    report=dict(artifacts=provenance(a.bit,a.elf),address=hex(base),size=a.size,loops=a.loops,rows=[])
    try:
        setup(out,inp,50000);initial=mem.word(0xe000edf0)
        if not initial&(1<<17):mem.write_word(0xe000edf0,0xa05f0003)
        report['CPUID']=hex(mem.word(0xe000ed00));report['RCC_before']=[hex(mem.word(0x40021000)),hex(mem.word(0x40021004))]
        backup=mem.read(base,a.size);a.output.with_suffix('.backup.bin').write_bytes(backup)
        report['backup_sha256']=hashlib.sha256(backup).hexdigest()
        for speed in map(int,a.speeds.split(',')):
            row=dict(requested_kHz=speed,passed=False)
            try:
                row['idcode_reply']=setup(out,inp,speed).hex()
                diag=xfer(out,inp,[0x80,255]);row['diagnostic']=diag.hex()
                hz,cfg=struct.unpack_from('<II',diag,4);row.update(FCLK_Hz=hz,cfg=hex(cfg),phase=(cfg>>17)&1,rx_boundary=(cfg>>18)&1,**swd_clock_details(hz,cfg))
                t=time.perf_counter()
                for i in range(a.loops):
                    pattern=random.Random(0x20261028+speed*31+i).randbytes(a.size)
                    mem.write(base,pattern);assert mem.read(base,a.size)==pattern,'SRAM byte mismatch'
                row.update(passed=True,bytes_each_direction=a.loops*a.size,roundtrip_seconds=time.perf_counter()-t)
            except Exception as exc:
                row['error']=repr(exc);row['engine_state']=engine_snapshot(dev)
                try:
                    diag=xfer(out,inp,[0x80,255]);hz,cfg=struct.unpack_from('<II',diag,4)
                    row.update(FCLK_Hz=hz,cfg=hex(cfg),phase=(cfg>>17)&1,rx_boundary=(cfg>>18)&1,**swd_clock_details(hz,cfg))
                except Exception as diag_exc:row['diagnostic_error']=repr(diag_exc)
            finally:
                # Always restore at the known high-speed baseline, even when a
                # low-speed ACK/parity failure left the target out of framing.
                recover(dev,inp);setup(out,inp,50000)
                mem.write(base,backup);row['restore_match']=mem.read(base,a.size)==backup
                assert row['restore_match'],'SRAM restore mismatch'
                report['rows'].append(row);a.output.write_text(json.dumps(report,indent=2));print(json.dumps(row),flush=True)
        report['RCC_after']=[hex(mem.word(0x40021000)),hex(mem.word(0x40021004))]
        assert report['RCC_before']==report['RCC_after'],'Target RCC changed'
    except Exception as exc:
        report['fatal_error']=repr(exc)
        raise
    finally:
        try:
            recover(dev,inp);setup(out,inp,50000)
            if backup is not None:
                mem.write(base,backup);report['restore_match']=mem.read(base,a.size)==backup
                assert report['restore_match']
            if initial is not None and not initial&(1<<17):mem.write_word(0xe000edf0,0xa05f0001)
        finally:
            a.output.write_text(json.dumps(report,indent=2));usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
    if any(not row['passed'] for row in report['rows']):raise SystemExit(1)
if __name__=='__main__':main()
