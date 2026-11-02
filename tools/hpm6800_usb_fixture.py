"""Install/control/restore a temporary HPM6880 RAM-only monotonic-u32 RTT fixture.

No Flash/reset/PLL writes. Stop this task's Web streams before install/restore.
Private SRAM backups must stay in the named state directory, outside Git.
"""
import argparse,json,hashlib,struct,subprocess,time
from pathlib import Path
import usb.util
from dap_pipeline_bench import open_dap,drain
from benchmark_hpm5301 import setup
from probe_stream import Probe
from riscv_target import RiscvTarget
from validate_hpm6800_performance import SramMemory,target_clocks,recover_link
ROOT=Path(__file__).resolve().parents[1]
STATE=0xf0400000;CB=STATE+0x200;CODE=0x10000
def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def cb_bytes(ring,size):return struct.pack('<16sII6I',b'SEGGER RTT',1,0,0,ring,size,0,0,2)
def stop_producer(mem):
    mem.write_word(STATE+64,0)
    for _ in range(100):
        if mem.word(STATE+68)==1:return mem.word(STATE+24)
        time.sleep(.002)
    raise RuntimeError('Producer STOP acknowledgement missing')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('install','restore','start','stop','reset','status'))
    p.add_argument('--state',type=Path,required=True);p.add_argument('--batch',type=int,default=13);p.add_argument('--memory',choices=('ahb16','axi32'),default='ahb16')
    p.add_argument('--axi-noncacheable-confirmed',action='store_true',help='Caller verified target PMA: AXI 0x01240000..0x0127ffff is noncached, as in the retained scope/RTT fixtures; this tool does not configure PMA')
    a=p.parse_args();assert 1<=a.batch<=2048;meta=a.state/'state.json'
    if a.action=='install'and a.memory=='axi32'and not a.axi_noncacheable_confirmed:p.error('AXI fixture requires the verified noncached target mapping; use AHB16 otherwise')
    if a.action=='install':a.state.mkdir(parents=True,exist_ok=False);report=dict(phase='installing',registers={},regions=[],no_flash=True,no_reset=True)
    else:
        report=json.loads(meta.read_text())
        assert report['phase']=='installed' or a.action=='restore' and report['phase']=='installing',report['phase']
    cb=report.get('cb',0x01240000 if a.memory=='axi32' else CB)
    ring=report.get('ring',0x012400b8 if a.memory=='axi32' else STATE+0x1000)
    ring_size=report.get('ring_bytes',32768 if a.memory=='axi32' else 16384)
    dev,tx,rx=open_dap();probe=Probe();mem=SramMemory(tx,rx)
    try:
        if a.action in ('install','restore'):
            for service in (0x31,0x32):
                rc,words=probe.action(service,2);assert rc==0 and not words[0]&1,(service,rc,words)
        drain(rx)
        # Live producer control must use ordinary memory transfers. Repeating
        # Connect/IR/TAP initialization here is the known full-reconnect RTT
        # interference case, not part of a START/STOP flag write.
        if a.action in ('install','restore'):
            setup(tx,rx,10_000_000,0,connect=True);target=RiscvTarget(tx,rx);target.active()
        if a.action=='install':
            report['initial_dmstatus']=target.dmi(0x11);target.halt()
            report['registers']={str(n):target.register(n)for n in [0x7b0,0x7b1,0x300]+list(range(0x1001,0x1020))}
            report['cache_control']=target.register(0x7ca);report['clocks']=target_clocks(target)
            save(meta,report)
            regions=[(CODE,256),(STATE,0x8000)]
            if a.memory=='axi32':regions.append((0x01240000,0x10000))
            for address,size in regions:
                data=mem.read(address,size);assert mem.read(address,size)==data
                name=f'backup-{address:08x}.bin';(a.state/name).write_bytes(data)
                report['regions'].append(dict(address=address,size=size,file=name,sha256=sha(data)));save(meta,report)
            gcc=Path('E:/sdk_env_v1.11.0/toolchains/rv32imac_zicsr_zifencei_multilib_b_ext-win/bin/riscv32-unknown-elf-gcc.exe')
            elf=a.state/'producer.elf';binary=a.state/'producer.bin'
            subprocess.run([str(gcc),*(['-DHPM_USB_AXI_RING=1']if a.memory=='axi32'else[]),'-march=rv32imac_zicsr_zifencei','-mabi=ilp32','-nostdlib','-Wl,-Ttext=0x10000','-Wl,-e,producer',str(ROOT/'firmware/target/hpm6800_usb_ram/producer.S'),'-o',str(elf)],check=True)
            subprocess.run([str(gcc.with_name('riscv32-unknown-elf-objcopy.exe')),'-O','binary',str(elf),str(binary)],check=True)
            code=binary.read_bytes();assert len(code)<256
            mem.write(CODE,code);assert mem.read(CODE,len(code))==code
            mem.write(STATE,bytes(0x8000))
            if a.memory=='axi32':mem.write(0x01240000,bytes(0x10000))
            mem.write_word(STATE+72,a.batch);mem.write(cb,cb_bytes(ring,ring_size))
            mem.write(0x0124c000 if a.memory=='axi32'else STATE+0x6000,struct.pack('<8I',*[0x68000000+i*0x10203 for i in range(8)]))
            target.register(0x7b0,(report['registers'][str(0x7b0)]&~7)|3);target.register(0x7b1,CODE);target.resume()
            time.sleep(.02);assert mem.word(STATE)==0x48504d50
            report.update(phase='installed',producer_sha256=sha(code),producer_elf_sha256=sha(elf.read_bytes()),cb=cb,ring=ring,ring_bytes=ring_size,ahb_sram_bytes=32768,memory=a.memory);save(meta,report)
        elif a.action=='restore':
            recover_link(dev,tx,rx)
            if report['phase']=='installed':stop_producer(mem)
            target.halt();matches=[]
            for row in report['regions']:
                data=(a.state/row['file']).read_bytes();assert sha(data)==row['sha256']
                if row['address']==STATE and len(data)>0x8000:
                    # Recover the initial invalid geometry experiment without
                    # writing its unmapped AHB tail again (SDK: SRAM is 32KiB).
                    report['unmapped_tail_skipped']=len(data)-0x8000;data=data[:0x8000]
                mem.write(row['address'],data);matches.append(mem.read(row['address'],len(data))==data)
            assert all(matches);assert target.register(0x7ca)==report['cache_control'];assert target_clocks(target)==report['clocks']
            regs={int(k):v for k,v in report['registers'].items()}
            for n,value in regs.items():target.register(n,value)
            after={n:target.register(n)for n in regs}
            assert all((after[n]&~0x1c0 if n==0x7b0 else after[n])==(v&~0x1c0 if n==0x7b0 else v)for n,v in regs.items())
            if report['initial_dmstatus']&(1<<10):target.resume()
            report.update(phase='restored',memory_restored=matches,registers_restored=True,dmstatus=hex(target.dmi(0x11)));save(meta,report)
        elif a.action=='reset':
            stop_producer(mem);mem.write_word(STATE+24,0);mem.write_word(STATE+72,a.batch);mem.write(cb,cb_bytes(ring,ring_size));print('reset')
        elif a.action=='start':mem.write_word(STATE+64,1);print('started')
        elif a.action=='stop':print(json.dumps(dict(published_bytes=stop_producer(mem))))
        else:print(json.dumps(dict(enable=mem.word(STATE+64),ack=mem.word(STATE+68),published_bytes=mem.word(STATE+24))))
    finally:
        probe.close();usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
if __name__=='__main__':main()
