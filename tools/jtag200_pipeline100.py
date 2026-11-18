"""Tune and verify the 100 MHz JTAG block path on the guarded HPM5301 ILM window."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import statistics

from jtag200_pipeline import BlockBenchmark
from jtag200_ram_stress import BASE, BLOCK, BYTES, SETTINGS, Ownership, PhysicalPort, Target

RATE = "100"
START_IDLE = 384
IDLES = (384, 256, 192, 128, 96, 64, 48, 32, 24, 20, 16, 12, 8)


def need(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def run_trial(bench, idle, phase, advance, mode, seconds):
    bench.configure(RATE,idle,phase,advance_tms=bool(advance[0]),advance_tdi=bool(advance[1]))
    return bench.run(mode,seconds)


def tune(bench, target, saved, guards, args, report, save):
    bench.pattern(saved)
    point = None
    good_cal = None
    # Unchanged raw calibration identifies the target independently of the
    # block path's receive sample and launch settings.
    for tap,cal in ((16,37),(8,36),(24,37),(0,36)):
        SETTINGS[RATE]=(tap,cal,START_IDLE)
        try:
            target.rearm()
            target.select(RATE)
        except RuntimeError as error:
            report.setdefault("calibration_failures",[]).append(dict(tap=tap,error=str(error)))
            continue
        for advance in ((1,1),(0,1),(1,0),(0,0)):
            phases = (cal,cal-1,cal+1,cal-2,cal+2)
            for phase in phases:
                target.rearm()
                target.select(RATE)
                row = dict(tap=tap,raw_sample=cal,phase=phase,advance=advance,
                           idle=START_IDLE, **run_trial(bench,START_IDLE,phase,advance,1,0))
                report["phase_sweep"].append(row)
                if row["passed"]:
                    row["window"] = run_trial(bench,START_IDLE,phase,advance,1,1)
                    if row["window"]["passed"]:
                        point = (tap,phase,advance)
                        good_cal = cal
                        break
            if point:
                break
        if point:
            break
    save()
    need(point, "No 100 MHz 1 KiB read-only working point")
    tap,phase,advance = point
    print(f"100 MHz read calibration: tap {tap}, slot {phase}, TMS/TDI advance {advance}",flush=True)
    SETTINGS[RATE]=(tap,good_cal,START_IDLE)
    report["point"] = dict(tap=tap,phase=phase,raw_sample=good_cal,advance=advance)
    good_idles = []
    for idle in IDLES:
        target.rearm()
        target.select(RATE)
        first = run_trial(bench,idle,phase,advance,1,0)
        row = dict(idle=idle,short=first)
        if first["passed"]:
            row["window"] = run_trial(bench,idle,phase,advance,1,1)
            if row["window"]["passed"]:
                good_idles.append(idle)
        report["idle_sweep"].append(row)
        save()
        print("idle",idle,"matched reads",row.get("window",{}).get("read_bytes",0),
              "DMI",row.get("window",first).get("wire_dmi",{}),flush=True)

    def restore():
        mailbox = bench.status()
        need(mailbox[1]==mailbox[2],"Probe still owns JTAG; backup retained")
        target.rearm()
        for i in range(0,BYTES,BLOCK):
            target.write(BASE+i,saved[i:i+BLOCK])
        check = target.memory()
        need(check==saved and target.guards()==guards, "Target RAM restoration/readback mismatch")
        # Return independently read RAM bytes for sha256 and evidence.
        return check

    pattern = random.Random(5301100).randbytes(BYTES)
    # Test the fastest read-only points first. After each failed mixed check
    # the original bytes must be restored before any other setting is tried.
    for idle in reversed(good_idles):
        target.rearm()
        target.select(RATE)
        bench.pattern(pattern)
        report["write_started"] = True
        try:
            trial = run_trial(bench,idle,phase,advance,0,0)
            if trial["passed"]:
                trial["window"] = run_trial(bench,idle,phase,advance,0,2)
        finally:
            restored=restore()
            report["restored_sha256"] = hashlib.sha256(restored).hexdigest()
            report["ram_match"] = report["guards_match"] = True
            save()
        report["mixed_pilots"].append(dict(idle=idle,run=trial))
        save()
        if trial.get("window",{}).get("passed"):
            # Retain shorter or failed captures and retry a looser point if needed.
            long = dict(idle=idle,windows=[])
            report["long"].append(long)
            for _ in range(3):
                target.rearm()
                target.select(RATE)
                bench.pattern(pattern)
                try:
                    run=run_trial(bench,idle,phase,advance,0,args.seconds)
                    long["windows"].append(run)
                finally:
                    restored=restore()
                    report["ram_match"] = report["guards_match"] = True
                    report["restored_sha256"]=hashlib.sha256(restored).hexdigest()
                    save()
                print("mixed",idle,run,flush=True)
                if not run["passed"]:
                    break
            if len(long["windows"])==3 and all(r["passed"] for r in long["windows"]):
                report["accepted"] = dict(
                    idle=idle, read_MBps=statistics.median(r["read_MBps"] for r in long["windows"]),
                    write_MBps=statistics.median(r["write_MBps"] for r in long["windows"]))
                return
    raise RuntimeError("No stable mixed 100 MHz block point")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair",type=Path,required=True)
    parser.add_argument("--backup",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--cable-serial",required=True)
    parser.add_argument("--sdk",type=Path,default=Path("E:/Xilinx/SDK/2018.3"))
    parser.add_argument("--seconds",type=int,choices=range(1,61),default=60,metavar="1..60")
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    need(re.fullmatch(r"[A-Za-z0-9_.:-]+",args.cable_serial),"Invalid cable serial")
    if not args.execute:
        print(f"Tune 100 MHz and restore ILM {BASE:#x} + {BYTES}. Three {args.seconds} s mixed windows.")
        return
    saved=(args.backup/"backup.bin").read_bytes()
    guards=(args.backup/"guards.bin").read_bytes()
    need(len(saved)==BYTES and len(guards)==8,"Incorrect original backup lengths")
    args.out.mkdir(parents=True,exist_ok=False)
    report={"rate_MHz":100,"cable":args.cable_serial,"phase_sweep":[],"idle_sweep":[],
            "mixed_pilots":[],"long":[],"backup_sha256":hashlib.sha256(saved).hexdigest()}
    def save():
        temp=args.out/"result.tmp"
        temp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
        temp.replace(args.out/"result.json")

    lease=Ownership()
    try:
        port=PhysicalPort(args.out,args.cable_serial,args.sdk)
        try:
            report["probe"]=port.verify_probe(args.pair)
            bench=BlockBenchmark(port,args.out)
            target=Target(port)
            target.select("50")
            original=target.init()
            try:
                need(target.memory()==saved and target.guards()==guards,
                     "Target changed after preflight backup")
                tune(bench,target,saved,guards,args,report,save)
            finally:
                mailbox=bench.status()
                need(mailbox[1]==mailbox[2],"Active block runner prevented recovery")
                target.rearm()
                readback=target.memory()
                report["ram_match"]=readback==saved
                report["guards_match"]=target.guards()==guards
                report["readback_sha256"]=hashlib.sha256(readback).hexdigest()
                (args.out/"readback.bin").write_bytes(readback)
                target.cleanup(original)
                report["debug_restored"]=True
                need(report["ram_match"] and report["guards_match"],"Final independent readback differs")
        finally:
            port.close()
    except Exception as error:
        report["error"]=str(error)
        raise
    finally:
        lease.close()
        save()


if __name__ == "__main__":
    main()
