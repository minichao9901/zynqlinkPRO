"""Run two SRAM-only firmwares: Zynq B19 -> F103 PA15 -> invert -> PB3 -> A20.

Uses the current probe bitstream's GPIO mux, and restores the probe ELF plus
F103 SRAM/core/GPIO state. Neither target nor Zynq flash is programmed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import usb.util

from dap_pipeline_bench import open_dap,setup
from test_probe_board import Memory,stop
from probe_stream import Probe
from benchmark_rtt_forward import core_read,core_write,DHCSR

ROOT=Path(__file__).resolve().parents[1]
BSP=Path('E:/zynqlinkPRO/reference/legacy_zynq/ZYNQ_DAPLINK_RTL_100TO50MHz/'
         'ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0')
PS_GCC=Path('E:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe')

def run(cmd):
    return subprocess.run(list(map(str,cmd)),cwd=ROOT,check=True,capture_output=True,text=True)

def build(dest,bsp):
    gcc=Path(shutil.which('arm-none-eabi-gcc'))
    ext='.exe' if gcc.suffix=='.exe' else ''
    target=dest/'f103_gpio.elf';binary=dest/'f103_gpio.bin'
    run([gcc,'-mcpu=cortex-m3','-mthumb','-O2','-g','-ffreestanding','-nostdlib',
         '-Wl,-Ttext=0x20000000','-Wl,-e,probe_io_target',
         ROOT/'firmware/target/probe_jtag_gpio.c','-o',target])
    run([gcc.with_name('arm-none-eabi-objcopy'+ext),'-O','binary',target,binary])
    nm=run([gcc.with_name('arm-none-eabi-nm'+ext),target]).stdout
    entry=int(re.search(r'^([0-9a-fA-F]+) T probe_io_target$',nm,re.M)[1],16)
    ps=dest/'zynq_gpio.elf';src=ROOT/'firmware/xusbps_daplink_dma'
    r=run([PS_GCC,'-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-O2','-g',
         '-Wall','-Wextra','-I',bsp/'include','-specs='+str(src/'Xilinx.spec'),
         '-Wl,-build-id=none','-Wl,-T,'+str(src/'lscript.ld'),'-L'+str(bsp/'lib'),
         ROOT/'firmware/diagnostics/probe_jtag_gpio_zynq.c','-o',ps,
         '-Wl,--start-group','-lxil','-lgcc','-lc','-Wl,--end-group'])
    (dest/'build.log').write_text(r.stdout+r.stderr)
    nm=run([PS_GCC.with_name('arm-none-eabi-nm.exe'),ps]).stdout
    result_addr=int(re.search(r'^([0-9a-fA-F]+) [A-Za-z] io_result$',nm,re.M)[1],16)
    return binary,entry,ps,result_addr

def ps_test(dest,elf,result_addr,restore_elf,restore_bit):
    script=dest/'run_zynq_gpio.tcl'
    script.write_text('''connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM*#0"}
configparams force-mem-access 1
set failure [catch {
 stop
 rst -processor
 dow -chunksize 4096 {TEST_ELF}
 con
 set complete 0
 for {set retry 0} {$retry<150} {incr retry} {
  after 100
  if {[mrd -value RESULT_DONE]==1} {set complete 1;break}
 }
 if {!$complete} {error "Zynq GPIO fixture timeout"}
 for {set i 0} {$i<64} {incr i} {
  puts [format "IO_WORD_%d=%08x" $i [mrd -value [expr {RESULT_ADDR+4*$i}]]]
 }
} failure_text]
catch {stop}
disconnect
if {$failure} {error $failure_text}
exit
'''.replace('TEST_ELF',elf.as_posix())
        .replace('RESULT_DONE',hex(result_addr+4)).replace('RESULT_ADDR',hex(result_addr)))
    try:
        r=subprocess.run([str(Path(shutil.which('python'))),str(ROOT/'tools/run_xsct.py'),str(script)],
                         cwd=ROOT,capture_output=True,text=True,timeout=60)
    finally:
        # A processor-only restart leaves the active USB controller/dTDs alive.
        # Reload the complete preserved probe pair to restore USB reliably.
        restored=run([shutil.which('python'),ROOT/'tools/run_xsct.py',
                      ROOT/'tools/download_dap_fpga.tcl',restore_elf,restore_bit])
        (dest/'probe_restore.log').write_text(restored.stdout+restored.stderr)
    (dest/'zynq_run.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(r.stdout+r.stderr)
    words={int(k):int(v,16) for k,v in re.findall(r'IO_WORD_(\d+)=([0-9a-fA-F]+)',r.stdout)}
    assert len(words)==64 and words[0]==0x494f5a31 and words[1]==1,words
    return [words[i] for i in range(64)]

def connect():
    dev,out,inp=open_dap()
    try:setup(out,inp,50000)
    except BaseException:
        usb.util.dispose_resources(dev)
        raise
    return dev,out,inp,Memory(out,inp)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=ROOT/'results/jtag/gpio_continuity.json')
    ap.add_argument('--probe-elf',type=Path,default=ROOT/'build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf')
    ap.add_argument('--probe-bit',type=Path,required=True,help='The currently loaded probe bitstream, restored after the PS fixture')
    ap.add_argument('--bsp',type=Path,default=BSP)
    a=ap.parse_args();a.output=a.output.resolve();a.output.parent.mkdir(parents=True,exist_ok=True)
    dest=ROOT/'build/jtag_gpio';dest.mkdir(parents=True,exist_ok=True)
    restore_elf=dest/'restore_probe.elf';shutil.copy2(a.probe_elf,restore_elf)
    restore_bit=dest/'restore_probe.bit';shutil.copy2(a.probe_bit,restore_bit)
    binary,entry,ps,result_addr=build(dest,a.bsp)
    report={'wiring':{'B19':'F103 PA15 input','A20':'F103 PB3 inverted output'},
            'target_bin_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'zynq_elf_sha256':hashlib.sha256(ps.read_bytes()).hexdigest(),
            'probe_restore_sha256':hashlib.sha256(restore_elf.read_bytes()).hexdigest()}
    report['probe_bit_sha256']=hashlib.sha256(restore_bit.read_bytes()).hexdigest()
    dev=p=None;saved=regs=initial=None;started=False
    try:
        p=Probe();dev,out,inp,m=connect();stop(p,dev)
        initial=m.word(DHCSR);m.write_word(DHCSR,0xa05f0003)
        regs={i:core_read(m,i) for i in list(range(19))+[20]}
        saved=m.read(0x20000000,20480)
        a.output.with_suffix('.backup.bin').write_bytes(saved)
        report.update(registers_before=regs,initial_DHCSR=initial,
                      ram_before_sha256=hashlib.sha256(saved).hexdigest())
        a.output.write_text(json.dumps(report,indent=2))
        m.write(0x20000000,binary.read_bytes());m.write(0x20004000,bytes(128))
        core_write(m,16,0x01000000);core_write(m,20,1)
        core_write(m,17,0x20004ff0);core_write(m,13,0x20004ff0);core_write(m,15,entry|1)
        m.write_word(DHCSR,0xa05f0001);started=True
        # Reframe SWD after releasing PA15/PB3 from the JTAG pin function.
        time.sleep(.02);setup(out,inp,50000)
        ready=m.read(0x20004000,8)
        assert struct.unpack('<2I',ready)==(0x494f4631,1),ready.hex()
        p.close();p=None;usb.util.dispose_resources(dev);dev=None
        print('Both temporary firmwares built; F103 inverted echo is running.',flush=True)
        z=ps_test(dest,ps,result_addr,restore_elf,restore_bit)
        report['zynq_words']=z
        report['phases']=[dict(output_mux='jtag' if i>=3 else 'gpio',settle_us=z[16+i*4],checks=z[17+i*4],errors=z[18+i*4]) for i in range(6)]
        report.update(checks=z[2],errors=z[3],B19_low_checks=z[4],B19_high_checks=z[5],B19_pad_readback_errors=z[11])
        print(json.dumps({k:report[k] for k in ['checks','errors','phases']}),flush=True)
    finally:
        try:
            if p is not None:p.close()
            if dev is not None:usb.util.dispose_resources(dev)
            if saved is not None:
                # PS test restores the normal USB probe even when its checks fail.
                dev=out=inp=m=None
                for attempt in range(8):
                    try:dev,out,inp,m=connect();break
                    except Exception:
                        if dev is not None:usb.util.dispose_resources(dev)
                        time.sleep(.5)
                if m is None:raise RuntimeError('Cannot reconnect to restored probe; backups saved beside report')
                if started:
                    report['target_words']=list(struct.unpack('<32I',m.read(0x20004000,128)))
                    m.write_word(0x20004008,1)
                    for _ in range(100):
                        if m.word(0x20004004)==2:break
                        time.sleep(.01)
                    else:raise RuntimeError('F103 GPIO fixture did not restore its pin configuration')
                    before=report['target_words'][12:17]
                    m.write_word(0x40021018,before[0]|0xd)
                    restored_gpio=[m.word(addr) for addr in [0x40010004,0x40010804,0x40010c00,0x40010c0c]]
                    m.write_word(0x40021018,before[0])
                    report['gpio_after']=[m.word(0x40021018)]+restored_gpio
                    report['gpio_restore_match']=report['gpio_after']==before
                m.write_word(DHCSR,0xa05f0003)
                m.write(0x20000000,saved)
                report['ram_restore_match']=m.read(0x20000000,20480)==saved
                assert report['ram_restore_match']
                for i,v in regs.items():core_write(m,i,v)
                report['registers_after']={i:core_read(m,i) for i in regs}
                report['registers_restore_match']=report['registers_after']==regs
                assert report['registers_restore_match']
                if not initial&(1<<17):m.write_word(DHCSR,0xa05f0001)
                usb.util.dispose_resources(dev)
        finally:a.output.write_text(json.dumps(report,indent=2))
    t=report['target_words']
    assert report.get('gpio_restore_match'),report.get('gpio_after')
    assert report['errors']==0 and report['B19_pad_readback_errors']==0 and report['checks']==44400,report
    assert t[0]==0x494f4631 and t[1]==1 and t[5] and t[6] and t[8]>20000 and t[9]>20000,t
    print('PASS B19 -> PA15 and PB3 -> A20: 44,400 inverted-echo checks; RAM/core/GPIO/probe restored.',flush=True)

if __name__=='__main__':main()
