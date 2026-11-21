"""Hold F103ZE CDC48 around a native CLI test, with independent RAM recovery."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import usb.util
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from board_acceptance_target import elf_contents
from dap_pipeline_bench import open_dap, setup, xfer
from run_f103_jtag_fixture import APB2ENR,DHCSR,MAPR,SWJ_MASK
from target_snapshot import snapshot
from test_probe_board import Memory


ROOT=Path(__file__).resolve().parents[1]
BASE=0x20008000
SIZE=4096
ELF=ROOT/"prebuilt/golden/f103ze-cdc48.elf"


@contextmanager
def low_link(serial):
    end=time.monotonic()+60
    while True:
        try:
            device,tx,rx=open_dap(serial)
            break
        except RuntimeError:
            if time.monotonic()>=end:raise
            time.sleep(.25)
    try:
        setup(tx,rx,1000,"swd")
        mem=Memory(tx,rx)
        if mem.word(0xe0042000)!=0x10036414 or mem.word(0xe000ed00)!=0x411fc231:
            raise RuntimeError("expected the high-density F103ZE")
        yield mem
    finally:
        try:xfer(tx,rx,[3])
        finally:usb.util.dispose_resources(device)


def save(path,state):
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state,indent=2)+"\n",encoding="utf8")
    until=time.monotonic()+5
    while True:
        try:tmp.replace(path);return
        except PermissionError:
            if time.monotonic()>=until:raise
            time.sleep(.05)


def restore(directory,state):
    size=state.get("size",SIZE)
    if size not in (4096,16384): raise RuntimeError("unknown saved SRAM extent")
    with low_link(state["serial"]) as mem:
        if not mem.word(DHCSR)&(1<<17):
            raise RuntimeError("fixture recovery expects a halted target; restore any test producer core registers first")
        if "backup_sha256" in state:
            data=(directory/"backup.bin").read_bytes()
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=state["backup_sha256"]:
                raise RuntimeError("saved SRAM backup identity differs")
            if mem.read(BASE,size)!=data:mem.write(BASE,data)
            if mem.read(BASE,size)!=data or [mem.word(BASE-4),mem.word(BASE+size)]!=state["guards"]:
                raise RuntimeError("SRAM or guards differ after recovery")
        if "mapr" in state:
            mem.write_word(MAPR,state["mapr"]|(2<<24))
            if mem.word(MAPR)&~SWJ_MASK!=state["mapr"]:raise RuntimeError("AFIO readback differs")
        if "apb2" in state:
            mem.write_word(APB2ENR,state["apb2"])
            if mem.word(APB2ENR)!=state["apb2"]:raise RuntimeError("APB2 readback differs")
        if snapshot(mem)!=state["target"]:raise RuntimeError("target or RCC differs after test")
        mem.write_word(DHCSR,0xa05f0000|(state["dhcsr"]&0x2f))
        final=mem.word(DHCSR)
        if (final^state["dhcsr"])&(1<<17):raise RuntimeError("target run/halt state differs")
        state.update(restored=True,final_dhcsr=hex(final))
    save(directory/"state.json",state)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial",default="12345678")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--restore",action="store_true")
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("command",nargs=argparse.REMAINDER)
    parser.add_argument("--size",type=int,choices=(4096,16384),default=SIZE)
    args=parser.parse_args()
    size=args.size
    cmd=args.command[1:] if args.command[:1]==["--"] else args.command
    directory=args.out.resolve()
    if not args.execute:
        print(f"F103ZE CDC48 guarded SRAM {BASE:#x} + {size}; backup and restore RCC/AFIO/core run state; child {cmd}")
        return
    if args.restore:
        state=json.loads((directory/"state.json").read_text(encoding="utf8"))
        if state["serial"]!=args.serial:parser.error("recovery probe serial differs")
        return restore(directory,state)
    if not cmd:parser.error("supply a child command following --")
    directory.mkdir(parents=True,exist_ok=False)
    state=dict(size=size,serial=args.serial,command=cmd,elf_sha256=hashlib.sha256(ELF.read_bytes()).hexdigest())
    halted=False
    try:
        with low_link(args.serial) as mem:
            _,segments=elf_contents(ELF)
            if any(mem.read(a,len(data))!=data for a,data,_ in segments):
                raise RuntimeError("running application differs from F103ZE CDC48")
            if mem.word(0x40021004)!=0x0051040a:raise RuntimeError("target is not at the CDC48 clock profile")
            state.update(target=snapshot(mem),dhcsr=mem.word(DHCSR))
            save(directory/"state.json",state)
            mem.write_word(DHCSR,0xa05f0003);halted=True
            if not mem.word(DHCSR)&(1<<17):raise RuntimeError("halt not confirmed")
            data=mem.read(BASE,size)
            if mem.read(BASE,size)!=data:raise RuntimeError("unstable fixture SRAM")
            (directory/"backup.bin").write_bytes(data)
            state.update(backup_sha256=hashlib.sha256(data).hexdigest(),guards=[mem.word(BASE-4),mem.word(BASE+size)],apb2=mem.word(APB2ENR))
            save(directory/"state.json",state)
            mem.write_word(APB2ENR,state["apb2"]|1)
            state["mapr"]=mem.word(MAPR)&~SWJ_MASK
            save(directory/"state.json",state)
            mem.write_word(MAPR,state["mapr"])
        subprocess.run(cmd,cwd=ROOT,check=True)
    except BaseException as error:
        state["error"]=repr(error)
        raise
    finally:
        try:save(directory/"state.json",state)
        finally:
            if halted:
                # WinUSB may retain the old device instance in this process
                # across a JTAG reload. Reopen using a fresh libusb context.
                subprocess.run([sys.executable,"-X","utf8",str(Path(__file__).resolve()),
                                "--restore","--execute","--serial",args.serial,"--out",str(directory)],check=True)


if __name__=="__main__":
    main()
