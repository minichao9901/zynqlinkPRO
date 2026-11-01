"""Run a complete SRAM CDC target for ETM clock experiments, then reboot Flash.

Clock policy stays in the target firmware. This tool only resets/loads SRAM,
checks firmware diagnostics and runs an explicit child acceptance command.
It checks the existing Flash ELF before and after, never programs Flash/QSPI.
The application restarts; its live RAM state is not preserved across resets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from elftools.elf.elffile import ELFFile
from f103_ram_image import plan
from f103_capture_entry import UsbReconnect
from dap_pipeline_bench import open_dap, setup
from test_probe_board import Memory
from benchmark_rtt_forward import core_write, core_read
import usb.util

ROOT=Path(__file__).resolve().parents[1]
DHCSR, DEMCR = 0xe000edf0, 0xe000edfc


def wait_halt(mem):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        if mem.word(DHCSR)&(1<<17):return
        time.sleep(.005)
    raise RuntimeError('Reset did not halt the target')


def reset_halt(mem):
    mem.write_word(DHCSR,0xa05f0003);wait_halt(mem)
    demcr=mem.word(DEMCR)
    mem.write_word(DEMCR,demcr|1)
    mem.write_word(0xe000ed0c,0x05fa0004)
    time.sleep(.02);wait_halt(mem)
    mem.write_word(DEMCR,demcr&~1)
    mem.write_word(0xe000ed30,0x1f)


def flash_plan(path):
    with open(path,'rb') as stream:
        elf=ELFFile(stream)
        if elf.elfclass!=32 or not elf.little_endian or elf['e_machine']!='EM_ARM':raise ValueError('Restore baseline must be ARM ELF32')
        result=[]
        for s in elf.iter_segments():
            if s['p_type']=='PT_LOAD' and s['p_filesz']:
                if not 0x08000000<=s['p_paddr']<0x08080000 or s['p_filesz']>0x08080000-s['p_paddr']:
                    raise ValueError('Restore ELF must contain only F103ZE Flash load bytes')
                result.append((s['p_paddr'],s.data()))
        if not result:raise ValueError('No Flash baseline to verify')
        return result


def verify(mem,payloads):
    rows=[]
    for address,data in payloads:
        actual=mem.read(address,len(data))
        if actual!=data:raise RuntimeError('Image mismatch at '+hex(address))
        rows.append(dict(address=address,bytes=len(data),sha256=hashlib.sha256(actual).hexdigest()))
    return rows


def connect():
    dev,out,inp=open_dap()
    try:
        sys.path.insert(0,str(ROOT/'etm-service/tools'))
        from native_probe import reset_dap_session
        reset_dap_session(dev)
        setup(out,inp,1000)
        return dev,Memory(out,inp)
    except BaseException:
        usb.util.dispose_resources(dev)
        raise


def close(dev):
    usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target-elf',type=Path,required=True)
    p.add_argument('--restore-elf',type=Path,default=ROOT/'prebuilt/golden/f103ze-cdc48.elf')
    p.add_argument('--hclk-mhz',type=int,choices=(24,48,72),required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args();command=a.command[1:] if a.command[:1]==['--'] else a.command
    if not command:p.error('An explicit child acceptance command is required')
    image=plan(a.target_elf);golden=flash_plan(a.restore_elf)
    a.output.mkdir(parents=True,exist_ok=False)
    report=dict(targetElf=str(a.target_elf.resolve()),targetSha256=hashlib.sha256(a.target_elf.read_bytes()).hexdigest(),
        command=command,flashProgrammed=False,qspiProgrammed=False,hostClockWrites=False,
        firmwareHclkHz=a.hclk_mhz*1000000,applicationRestarted=True,passed=False)
    def save():(a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    reset_started=False;save()
    try:
        dev,mem=connect()
        try:
            if mem.word(0xe0042000)&0xfff!=0x414:raise RuntimeError('F103ZE required')
            fpctrl=mem.word(0xe0002000);count=((fpctrl>>8)&0x70)|((fpctrl>>4)&15)
            if count>16:raise RuntimeError('Unexpected FPB comparator count')
            if fpctrl&1 and any(mem.word(0xe0002008+4*i)&1 for i in range(count)):
                raise RuntimeError('Remove active hardware breakpoints before resetting the RAM fixture')
            report['flashBefore']=verify(mem,golden)
            report['rccBefore']=[mem.word(x) for x in (0x40021000,0x40021004)]
            reset_started=True;reset_halt(mem)
            reconnect=UsbReconnect(mem);reconnect.disconnect()
            for address,data in image['payloads']:mem.write(address,data)
            report['sramLoaded']=verify(mem,image['payloads'])
            core_write(mem,20,0);core_write(mem,17,image['stack']);core_write(mem,13,image['stack'])
            core_write(mem,16,0x01000000);core_write(mem,15,image['entry'])
            if (core_read(mem,15)&~1)!=(image['entry']&~1):raise RuntimeError('RAM entry PC mismatch')
            reconnect.restore();mem.write_word(DHCSR,0xa05f0001)
            until=time.monotonic()+5
            while time.monotonic()<until:
                hz=mem.word(image['symbols']['g_sysclk_hz']);error=mem.word(image['symbols']['g_clock_err'])
                if hz==a.hclk_mhz*1000000 and not error:break
                time.sleep(.05)
            else:raise RuntimeError(f'Firmware clock init failed: hz={hz} error={error}')
            report['rccActive']=[mem.word(x) for x in (0x40021000,0x40021004)]
            cfgr=report['rccActive'][1]
            if (cfgr&12)!=8 or not (cfgr&(1<<16)) or cfgr&(1<<17):raise RuntimeError('Expected HSE8 PLL clock source')
            pll=8000000*min(16,((cfgr>>18)&15)+2)
            hpre=(cfgr>>4)&15
            divisor=1 if hpre<8 else (2,4,8,16,64,128,256,512)[hpre-8]
            report['rccComputedHclkHz']=pll//divisor
            report['traceClockHz']=report['rccComputedHclkHz']//2
            if report['rccComputedHclkHz']!=a.hclk_mhz*1000000:raise RuntimeError('RCC does not match firmware clock diagnostic')
            report['vtor']=mem.word(0xe000ed08)
            if report['vtor']!=0x20000000:raise RuntimeError('SRAM vectors not active')
            report['clockDiagnosticHz']=hz;report['clockError']=error;save()
        finally:close(dev)
        child=subprocess.run(command,cwd=ROOT,capture_output=True)
        (a.output/'child.log').write_bytes(child.stdout+child.stderr)
        report['childReturnCode']=child.returncode
        if child.returncode:raise RuntimeError('Child failed; original evidence retained')
        report['passed']=True
    except BaseException as error:
        report['error']=str(error);raise
    finally:
        try:
            if reset_started:
                dev,mem=connect()
                try:
                    reset_halt(mem);reconnect=UsbReconnect(mem);reconnect.disconnect()
                    report['flashAfter']=verify(mem,golden)
                    reconnect.restore();mem.write_word(DHCSR,0xa05f0001)
                    time.sleep(1)
                    report['rccRestored']=[mem.word(x) for x in (0x40021000,0x40021004)]
                    if report['rccRestored']!=report['rccBefore']:raise RuntimeError('Flash firmware clock baseline did not return')
                    report['flashFirmwareRestarted']=True
                finally:close(dev)
        except BaseException as error:
            report['passed']=False;report['restoreError']=str(error);raise
        finally:save()
    print(json.dumps(report,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
