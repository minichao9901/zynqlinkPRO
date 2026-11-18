"""Measure the pure JTAG PL block pipeline against a guarded HPM5301 ILM window."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import time

from jtag200 import PROFILES, ROOT
from jtag200_ram_stress import BASE, BYTES, BLOCK, SETTINGS, Ownership, PhysicalPort, Target
from verify_probe_ocm_code import read_ocm_code

MAILBOX = 0x2FF40


def need(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def package(args):
    source = ROOT / "firmware/jtag200"
    timing = json.loads((args.fpga / "timing.json").read_text())
    need(timing["setup_slack_ns"] >= 0 and timing["hold_slack_ns"] >= 0, "Candidate timing failed")
    args.out.mkdir(parents=True, exist_ok=False)
    for name in ("probe.bit", "ps7_init.tcl"):
        shutil.copyfile(args.fpga / name, args.out / name)
    elf = args.out / "application.elf"
    flags = ["-mcpu=cortex-a9", "-marm", "-O3", "-g", "-ffreestanding", "-nostdlib",
             "-DJTAG200_STRESS", "-Wall", "-Wextra", "-Werror", "-Wl,--build-id=none"]
    subprocess.run([args.gcc, *flags, f"-Wl,-T,{source / 'ocm.ld'}",
                    source / "start.S", source / "clock.c",
                    ROOT / "firmware/jtag200_stress/block_runner.c", "-o", elf], check=True, cwd=ROOT)
    read_ocm_code(elf)
    manifest = {"source_revision":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                "fpga_entry":"fpga/experiments/jtag200/build.tcl", "fpga_timing":timing, "firmware_flags":flags,
                "hardware_acceptance":"pending", "sha256":{}}
    for name in ("probe.bit", "application.elf", "ps7_init.tcl"):
        manifest["sha256"][name] = hashlib.sha256((args.out/name).read_bytes()).hexdigest()
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(args.out)


class BlockBenchmark:
    def __init__(self, port, folder):
        self.port = port
        self.folder = folder
        need(int(port.command("read_word 0x40000010")) == 0x50495045, "Pipeline bit is not running")
        self.status()

    def status(self):
        line = self.port.command(f"physrd -force -value {MAILBOX:#x} 29")
        words = [int(x,0) for x in line.split()]
        need(len(words) == 29 and words[0] == 0x4A424C4B, "Pipeline runner ELF is not running")
        return words

    def configure(self, rate, idle, phase, *, advance_tms=False, advance_tdi=False):
        _, half, _ = PROFILES[rate]
        need(half == 2 or not (advance_tms or advance_tdi), "TX advance requires a two-slot pulse")
        cfg = (int(advance_tms) << 20) | (int(advance_tdi) << 19) | (idle << 10) | (phase << 3) | half
        self.port.command(f"physwr -force 0x40000014 {BASE:#x}; "
                          f"physwr -force 0x40000018 {BYTES//4}; physwr -force 0x4000001c {cfg:#x}")
        actual = int(self.port.command("read_word 0x4000001c"))
        need(cfg == actual, f"Pipeline timing readback {actual:#x} expected {cfg:#x}")

    def pattern(self, payload):
        known = (self.folder/"pattern.bin").resolve()
        check = (self.folder/"pattern-echo.bin").resolve()
        known.write_bytes(payload)
        self.port.command(f"physwr -force -bin -file {{{known.as_posix()}}} 0x03000000 {len(payload)//4}")
        self.port.command(f"physrd -force -bin -file {{{check.as_posix()}}} 0x03000000 {len(payload)//4}")
        need(check.read_bytes() == payload, "Pattern upload changed")

    def run(self, mode, seconds):
        begin = self.status()
        need(begin[1] == begin[2], "Pipeline runner is not idle")
        sequence = (begin[1]+1) & 0xffffffff
        start = time.monotonic()
        self.port.command(f"physwr -force {MAILBOX+12:#x} {seconds}; "
                          f"physwr -force {MAILBOX+20:#x} {mode}; "
                          f"physwr -force {MAILBOX+4:#x} {sequence}")
        deadline = time.monotonic()+seconds+10
        while True:
            words = self.status()
            if words[2] == sequence:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("Pipeline runner did not publish completion")
            time.sleep(0.2 if seconds else 0.01)
        def systime(index):
            return (words[index] | words[index+1]<<32)/333333333
        rd,wr,total = systime(12),systime(14),systime(10)
        row=dict(mode=mode, planned_s=seconds, seconds=total, host_s=time.monotonic()-start,
                 read_MBps=words[6]/rd/1e6 if rd else 0,
                 write_MBps=words[7]/wr/1e6 if wr else 0,
                 read_bytes=words[6], write_bytes=words[7],
                 tck_cycles=words[8], segments=words[9], completion=words[16],
                 dmi_busy=words[19], dmi_invalid=words[20], passed=words[4]==0)
        if seconds == 0 or words[4]:
            diag = words[21:29]
            row["wire_dmi"] = dict(
                flags=diag[0],
                first_response=hex(diag[1] | diag[2]<<32),
                first_sbdata=hex(diag[3] | diag[4]<<32),
                first_invalid=hex(diag[5] | diag[6]<<32),
                preceding_request=hex(diag[7]))
        if words[4]:
            row.update(error=words[4], bad_word=words[17], bad_value=hex(words[18]))
        return row


def measure(args):
    need(re.fullmatch(r"[A-Za-z0-9_.:-]+", args.cable_serial), "Invalid cable serial")
    SETTINGS["200"] = (24,39,256)
    recovery_timing = SETTINGS["50"]

    def recover(target):
        previous = SETTINGS["50"]
        SETTINGS["50"] = recovery_timing
        try:
            target.rearm()
        finally:
            SETTINGS["50"] = previous
    cases = [tuple(entry.split(":")) for entry in args.point] if args.point else [
                ("50","0","36","64"), ("200","24","39","256")]
    if not args.execute:
        print(f"Guarded HPM5301 ILM {BASE:#x}+{BYTES}, cases {cases}, queue depth 1")
        return
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"cable":args.cable_serial,"base":hex(BASE),"block_bytes":BYTES,"queue_depth":1,"rows":[]}
    dest=args.out/"result.json"
    def save():
        dest.write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")

    lock = Ownership()
    try:
        port = PhysicalPort(args.out,args.cable_serial,args.sdk)
        try:
            report["probe"] = port.verify_probe(args.pair)
            legacy = Target(port)
            bench = BlockBenchmark(port,args.out)
            legacy.select("50")
            original = legacy.init()
            backup = None
            changed = False
            try:
                backup = legacy.memory()
                guards = legacy.guards()
                need(legacy.memory() == backup and legacy.guards() == guards, "Backup or guard mismatch")
                (args.out/"backup.bin").write_bytes(backup)
                (args.out/"guards.bin").write_bytes(guards)
                report["backup_sha256"] = hashlib.sha256(backup).hexdigest()
                save()
                pattern = random.Random(530150).randbytes(BYTES)
                expected = backup
                for rate,tap,phase,idle in cases:
                    tap,phase,idle = int(tap),int(phase),int(idle)
                    need(rate in ("50","100","160","200") and 0 <= tap <= 31
                         and 16 <= phase <= 63 and 8 <= idle <= 448, "Unsupported pipeline point")
                    SETTINGS[rate] = (tap,phase,idle)
                    item = dict(rate=rate,tap=tap,phase=phase,idle=idle,runs=[],
                                advance_tms=rate=="100",advance_tdi=rate=="100")
                    report["rows"].append(item)
                    try:
                        legacy.select(rate)
                        bench.configure(rate,idle,phase,advance_tms=rate=="100",advance_tdi=rate=="100")
                        bench.pattern(expected)
                        preflight=bench.run(1,0)
                        item["runs"].append(preflight)
                        need(preflight["passed"],f"Read-only preflight {preflight}")
                        bench.pattern(pattern)
                        changed=True
                        first=bench.run(0,0)
                        item["runs"].append(first)
                        need(first["passed"],f"Single block {first}")
                        expected = pattern
                        if not args.pilot:
                            for mode in (1,2,0):
                                for _ in range(3):
                                    seconds = args.seconds
                                    # Mixed test reads every written word; isolated
                                    # write windows are compared against the last block.
                                    run=bench.run(mode,seconds)
                                    item["runs"].append(run)
                                    save()
                                    need(run["passed"], f"Pipeline benchmark {run}")
                                    if mode != 1:
                                        inverse = ((run["write_bytes"]//BYTES)-1)&1
                                        expected = bytes(x^255 for x in pattern) if inverse else pattern
                                        recover(legacy)
                                        need(legacy.memory()==expected and legacy.guards()==guards,
                                             "Independent post-window readback differs")
                                        legacy.select(rate)
                                        bench.configure(rate,idle,phase,advance_tms=rate=="100",advance_tdi=rate=="100")
                            item["passed"]=True
                        else:
                            item["passed"]=True
                    except Exception as error:
                        item["error"]=str(error)
                        state = bench.status()
                        need(state[1] == state[2], "Block runner still owns JTAG")
                        recover(legacy)
                        if changed:
                            for i in range(0,BYTES,BLOCK):
                                legacy.write(BASE+i,backup[i:i+BLOCK])
                            need(legacy.memory()==backup and legacy.guards()==guards,"Recovery readback differs")
                            item["recovered"]=True
                            expected=backup
                    save()
                    print(json.dumps(item,separators=(",",":")),flush=True)
            finally:
                if changed:
                    state=bench.status()
                    need(state[1]==state[2],"Runner still active; backup retained")
                    recover(legacy)
                    for i in range(0,BYTES,BLOCK):
                        legacy.write(BASE+i,backup[i:i+BLOCK])
                    restored = legacy.memory()
                    (args.out/"restored.bin").write_bytes(restored)
                    report["restored"]=restored==backup and legacy.guards()==guards
                    report["restored_sha256"]=hashlib.sha256(restored).hexdigest()
                    need(report["restored"],"Restored ILM differs")
                legacy.cleanup(original)
                report["debug_restored"]=True
        finally:
            port.close()
    finally:
        lock.close()
        save()
    return int(any(not r.get("passed") for r in report["rows"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action",required=True)
    build = sub.add_parser("package")
    build.add_argument("--fpga",type=Path,required=True)
    build.add_argument("--gcc",type=Path,default=Path(
        "E:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe"))
    build.add_argument("--out",type=Path,required=True)
    run = sub.add_parser("run")
    run.add_argument("--pair",type=Path,required=True)
    run.add_argument("--cable-serial",required=True)
    run.add_argument("--sdk",type=Path,default=Path("E:/Xilinx/SDK/2018.3"))
    run.add_argument("--out",type=Path,required=True)
    run.add_argument("--point",action="append",metavar="RATE:TAP:PHASE:IDLE")
    run.add_argument("--seconds",type=int,choices=range(1,61),default=3,metavar="1..60")
    run.add_argument("--pilot",action="store_true")
    run.add_argument("--execute",action="store_true")
    args = parser.parse_args()
    return package(args) if args.action=="package" else measure(args)


if __name__=="__main__":
    raise SystemExit(main())
