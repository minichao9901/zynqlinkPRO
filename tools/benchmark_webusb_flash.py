"""HPM6800 Flash benchmark support: explicit backup, OpenOCD comparison and restore.

Writes target Flash only in openocd/restore stages. Never writes probe QSPI or
target PLL. Private backup/readback files stay in the requested output folder.
Use --execute to run; otherwise print the plan without opening hardware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
SDK=Path('E:/sdk_env_v1.11.0')

def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['backup','openocd','restore'],required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--backup',type=Path)
    p.add_argument('--elf',type=Path,default=ROOT/'firmware/target/hpm6800_web_validation/scope/fw.elf')
    p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--riscv-clock-profile',action='store_true',help='Use the existing low-frequency RISC-V probe FCLK policy; TCK remains 10MHz')
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if a.stage=='restore' and not a.backup:p.error('--backup is required for restore')
    if not a.execute:print(json.dumps(dict(stage=a.stage,out=str(a.out),hardwareAccess=False,executeRequired=True)));return
    a.out.mkdir(parents=True,exist_ok=False)
    config=a.out/'hpm6800.cfg'
    config.write_text('source [find interface/cmsis-dap.cfg]\ncmsis_dap_backend usb_bulk\ncmsis_dap_vid_pid 0x0d28 0x0204\ntransport select jtag\nadapter speed 10000\nreset_config none\nsource [find soc/hpm6880.cfg]\nflash bank xpi0 hpm_xpi 0x80000000 0x2000000 1 1 $_TARGET0 0xF3000000 0x7\n$_TARGET0 configure -work-area-backup 1\n',encoding='utf-8')
    argv=[str(SDK/'tools/openocd/openocd.exe'),'-s',str(SDK/'tools/openocd/tcl'),'-s',str(SDK/'hpm_sdk/boards/openocd'),'-f',str(config.resolve())]
    report=dict(stage=a.stage,clockKhz=10000,probeQspiWrites=False,targetPllWrites=False,rows=[],passed=False)
    def run(name,commands):
        args=argv[:]
        for command in commands:args+=['-c',command]
        row=dict(name=name,argv=args,passed=False);report['rows'].append(row);save(a.out/'result.json',report)
        started=time.perf_counter();r=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        log=r.stdout+r.stderr;(a.out/(name+'.log')).write_text(log,encoding='utf-8')
        row.update(seconds=time.perf_counter()-started,returncode=r.returncode,
            timingsMs={k.lower():int(v) for k,v in re.findall(r'BENCH_(PREP|PROGRAM|VERIFY|RESET|TOTAL)_MS (\d+)',log)})
        save(a.out/'result.json',report)
        if r.returncode:raise RuntimeError(f'OpenOCD failed; inspect {name}.log; no automatic retry')
        return row
    def dump(path,addr,length):return f'dump_image {{{path.resolve().as_posix()}}} {addr:#x} {length}'
    if a.stage=='backup':
        from dap_pipeline_bench import open_dap,xfer,le
        from riscv_target import RiscvTarget
        import usb.util
        device,tx,rx=open_dap()
        try:
            assert xfer(tx,rx,[2,2])==b'\x02\x02'
            assert xfer(tx,rx,[0x15,1,5])==b'\x15\x00'
            assert xfer(tx,rx,[0x11]+le(10000000))==b'\x11\x00'
            target=RiscvTarget(tx,rx);target.select(1);identity=target.scan(0,32);assert identity==0x1000563d,hex(identity)
            status=target.active();running=bool(status&(1<<10));assert running or status&(1<<9)
            target.halt()
            try:report.update(initialDmstatus=hex(status),initialRunning=running,initialDcsr=target.register(0x7b0),initialDpc=target.register(0x7b1),tapIdcode=hex(identity))
            finally:
                if running:target.resume()
        finally:usb.util.release_interface(device,0);usb.util.dispose_resources(device)
        commands=['init','halt','riscv set_mem_access progbuf',dump(a.out/'flash-original.bin',0x80000000,65536),dump(a.out/'flash-repeat.bin',0x80000000,65536)]
        if running:commands+=['resume']
        row=run('backup',commands+['shutdown']);data=(a.out/'flash-original.bin').read_bytes()
        assert len(data)==65536 and data==(a.out/'flash-repeat.bin').read_bytes()
        report.update(bytes=len(data),sha256=sha(data),repeatMatches=True);row['passed']=True
    elif a.stage=='openocd':
        from elftools.elf.elffile import ELFFile
        with a.elf.open('rb') as stream:regions=sorted((int(s['p_paddr']),s.data()) for s in ELFFile(stream).iter_segments() if s['p_type']=='PT_LOAD' and s['p_filesz'] and 0x80000000<=s['p_paddr']<0x80010000)
        merged=[]
        for address,data in regions:
            if merged and merged[-1][0]+len(merged[-1][1])==address:merged[-1][1]+=data
            else:merged.append([address,data])
        regions=merged
        assert regions and all(at+len(data)<=0x80010000 for at,data in regions)
        report.update(elfSha256=sha(a.elf.read_bytes()),loadBytes=sum(len(data) for _,data in regions))
        report['verifyRegions']=[dict(address=hex(at),bytes=len(data)) for at,data in regions]
        report['riscvClockProfile']=a.riscv_clock_profile
        if a.riscv_clock_profile:
            from dap_pipeline_bench import open_dap,xfer,le
            import usb.util
            device,tx,rx=open_dap()
            try:
                assert xfer(tx,rx,[2,2])==b'\x02\x02'
                assert xfer(tx,rx,[0x8b,1])==b'\x8b\x00\x01'
                assert xfer(tx,rx,[0x11]+le(10000000))==b'\x11\x00'
            finally:usb.util.release_interface(device,0);usb.util.dispose_resources(device)
        for repeat in range(a.rounds+1):
            commands=['set begin [ms]','init','halt','echo [format {BENCH_PREP_MS %d} [expr {[ms]-$begin}]]','set phase [ms]',f'flash write_image erase {{{a.elf.resolve().as_posix()}}}','echo [format {BENCH_PROGRAM_MS %d} [expr {[ms]-$phase}]]','riscv set_mem_access progbuf','set phase [ms]']
            for i,(addr,data) in enumerate(regions):commands.append(dump(a.out/f'verify-{repeat}-{i}.bin',addr,len(data)))
            commands+=['echo [format {BENCH_VERIFY_MS %d} [expr {[ms]-$phase}]]','set phase [ms]','reset run','echo [format {BENCH_RESET_MS %d} [expr {[ms]-$phase}]]','echo [format {BENCH_TOTAL_MS %d} [expr {[ms]-$begin}]]','shutdown']
            row=run(f'round-{repeat}',commands);row['warmup']=repeat==0
            if repeat==0:
                from probe_build_info import live_clock_snapshot
                row['clockAfterWarmup']=live_clock_snapshot()
                assert abs(row['clockAfterWarmup']['actual_link_Hz']-10000000)<10
            row['byteExact']=all((a.out/f'verify-{repeat}-{i}.bin').read_bytes()==data for i,(_,data) in enumerate(regions));assert row['byteExact'];row['passed']=True
    else:
        backup=a.backup.resolve();old=json.loads((backup/'result.json').read_text(encoding='utf-8'));data=(backup/'flash-original.bin').read_bytes();assert len(data)==65536 and sha(data)==old['sha256']
        run('restore',['init','halt',f'flash write_image erase {{{(backup/"flash-original.bin").as_posix()}}} 0x80000000 bin','reset run','shutdown'])['passed']=True
        back=a.out/'readback-private.bin'
        run('readback',['init','halt','riscv set_mem_access progbuf',dump(back,0x80000000,65536),'shutdown'])['passed']=True
        report['byteExact']=back.read_bytes()==data;report['sha256']=sha(back.read_bytes());assert report['byteExact'],'Restore mismatch; target left halted'
        from dap_pipeline_bench import open_dap,xfer,le
        from riscv_target import RiscvTarget
        import usb.util
        device,tx,rx=open_dap()
        try:
            assert xfer(tx,rx,[2,2])==b'\x02\x02'
            assert xfer(tx,rx,[0x8b,0x0e])==b'\x8b\x00\x0e'
            assert xfer(tx,rx,[0x15,1,5])==b'\x15\x00'
            assert xfer(tx,rx,[0x11]+le(10000000))==b'\x11\x00'
            target=RiscvTarget(tx,rx);target.active();target.halt()
            target.register(0x7b0,old['initialDcsr']&~4);dcsr=target.register(0x7b0)
            assert dcsr&0xbe17==(old['initialDcsr']&~4)&0xbe17
            if old['initialRunning']:target.resume()
            report.update(finalDcsr=hex(dcsr),dcsrVerifiedMask='0xbe17',finalDmstatus=hex(target.dmi(0x11)))
        finally:usb.util.release_interface(device,0);usb.util.dispose_resources(device)
        report['finalState']='running original program after reset' if old['initialRunning'] else 'halted original program after reset'
    report['passed']=True;save(a.out/'result.json',report);print(json.dumps(report))

if __name__=='__main__':main()
