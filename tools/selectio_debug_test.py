"""Exercise standard OpenOCD over the selected live CMSIS-DAP link on F103ZE."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from benchmark_rtt_forward import core_read,core_write
from selectio_f103_fixture import BASE,DHCSR,ROOT,low_link


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--transport",choices=("swd","jtag"),required=True)
    ap.add_argument("--slot",type=int,required=True)
    ap.add_argument("--clock",type=int,choices=(50000000,73000000,100000000),default=100000000)
    ap.add_argument("--idle",type=int)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--execute",action="store_true")
    a=ap.parse_args()
    if not a.execute:return print("Run OpenOCD inside the halted F103ZE guard; step two SRAM instructions.")
    a.out.mkdir(parents=True,exist_ok=False)
    report={"transport":a.transport,"requested_hz":a.clock,"passed":False}
    with low_link(a.serial) as m:
        if not m.word(DHCSR)&(1<<17):raise RuntimeError("requires halted target")
        scratch=m.word(0xe000edf8)
        regs={i:core_read(m,i) for i in [*range(17),20]}
        page=m.read(BASE,16)
        fp=0xe0002000;dwt=0xe0001000
        fpc=m.word(fp);dwtc=m.word(dwt)
        addresses=[0xe000edfc,0xe0042004,fp]
        addresses += [fp+8+4*i for i in range(((fpc>>4)&15)+((fpc>>8)&0x70)+((fpc>>8)&15))]
        addresses += [dwt+0x20+16*i+offset for i in range(dwtc>>28) for offset in (0,4,8)]
        saved={addr:m.word(addr) for addr in addresses}
    try:
        with low_link(a.serial) as m:
            m.write(BASE,bytes.fromhex("2a200130fee700bf"))
            core_write(m,16,0x01000000);core_write(m,20,1);core_write(m,15,BASE+1)
        tap,idle=(8,2) if a.transport=="swd" else (16,33)
        if a.idle is not None:idle=a.idle
        subprocess.run([sys.executable,"-X","utf8",str(ROOT/"toolbox.py"),"selectio","--serial",a.serial,"profile",
                        "--transport",a.transport,"--tap",str(tap),"--slot",str(a.slot),"--idle",str(idle)],check=True)
        subprocess.run([sys.executable,"-X","utf8",str(ROOT/"toolbox.py"),"selectio","--serial",a.serial,
                        "identify","--transport",a.transport,"--clock","1000000"],check=True)
        commands=[
            'gdb port disabled','tcl port disabled','telnet port disabled','reset_config none',
            'stm32f1x.cpu configure -event examine-end {}','adapter speed 1000','init',
            'poll','halt','wait_halt 2000','poll',f'adapter speed {a.clock//1000}','set id [lindex [read_memory 0xe000ed00 32 1] 0]',
            'if {$id != 0x411fc231} {error "Cortex identity differs"}',
            'echo BEFORE_STEP','stm32f1x.cpu curstate','mdw 0xe000edf0','reg pc force',
            'step','wait_halt 2000','poll','echo AFTER_FIRST','reg pc force',
            'step','wait_halt 2000','poll','set r [get_reg {r0 pc}]',
            'if {[dict get $r r0] != 43 || [dict get $r pc] != 0x20008004} {error "SRAM single step differs: $r"}',
            'bp 0x08000000 2 hw','rbp 0x08000000','echo SELECTIO_OPENOCD_PASS','shutdown']
        cmd=['openocd','-d3','-f','interface/cmsis-dap.cfg','-c',f'adapter serial {a.serial}',
             '-c','cmsis-dap backend usb_bulk','-c',f'transport select {a.transport}','-f','target/stm32f1x.cfg']
        for c in commands:cmd+=['-c',c]
        p=subprocess.run(cmd,capture_output=True,timeout=40)
        text=(p.stdout+p.stderr).decode(errors='replace')
        (a.out/'openocd.log').write_text(text)
        if p.returncode or 'SELECTIO_OPENOCD_PASS' not in text:raise RuntimeError(text[-1700:])
        report["passed"]=True
    finally:
        try:
            with low_link(a.serial) as m:
                m.write_word(DHCSR,0xa05f0003);m.write(BASE,page)
                # Restore debug comparators while disabled, then restore the global enable.
                m.write_word(fp,2)
                for addr,value in saved.items():
                    if addr!=fp:m.write_word(addr,value)
                m.write_word(fp,(fpc&1)|2)
                for i in [*range(15),20,16,15]:core_write(m,i,regs[i])
                for addr,value in saved.items():
                    if m.word(addr)!=value:raise RuntimeError(f"debug register recovery failed at {addr:#x}")
                if m.read(BASE,16)!=page or any(core_read(m,i)!=v for i,v in regs.items()):
                    raise RuntimeError("core or SRAM recovery differs")
                m.write_word(0xe000edf8,scratch)
                if m.word(0xe000edf8)!=scratch:raise RuntimeError("DCRDR recovery differs")
                report["restored"]=True
        finally:(a.out/'result.json').write_text(json.dumps(report,indent=2))
    print(report)


if __name__=="__main__":
    main()
