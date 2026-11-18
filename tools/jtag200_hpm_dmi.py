"""Read-only HPM5301 DMI tracing for the isolated J7 block pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from jtag200_pipeline import BlockBenchmark
from jtag200_ram_stress import BASE, BYTES, SETTINGS, Ownership, PhysicalPort, Target, append_data, entry

DMSTATUS = 0x11


def need(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def wire_replay(port, split, expected_dmstatus):
    """Compare one uninterrupted TAP command with the same segments padded."""
    slots = [6] * 8
    positions = []

    def append(tms, tdi, gap):
        for mode, data in zip(tms, tdi):
            data = mode << 1 | data << 2
            slots.extend((data, data | 1))
        if split:
            slots.extend([6] * ((-len(slots) % 8) + 8*gap))

    mode, data = entry(17)
    # The RTL's reset segment includes five reset clocks plus Run-Test/Idle.
    # entry() emits six reset clocks; drop the first for an exact comparison.
    mode, data = mode[1:], data[1:]
    cuts = ((0, 6, 4), (6, 10, 4), (10, 15, 4), (15, 17, 3))
    for lo, hi, gap in cuts:
        append(mode[lo:hi], data[lo:hi], gap)

    for value in ((0x10 << 34) | (1 << 2) | 2, 0, (DMSTATUS << 34) | 1, 0):
        tms, tdi = [], []
        shift = append_data(tms, tdi, value, 41, 256)
        positions.append(len(slots) + 2 * shift + 1)
        append(tms, tdi, 4)
    slots.extend([6] * (64 + (-len(slots) % 8)))
    words = [sum((slots[start + bit] >> lane & 1) << (lane * 8 + bit)
                 for lane in range(3) for bit in range(8))
             for start in range(0, len(slots), 8)]
    need(len(words) <= 512, "Replay exceeds raw waveform buffer")
    words[-1] |= 1 << 24
    raw = port.scan(struct.pack(f"<{len(words)}I", *words), len(words))[::4]
    lookup = []
    for phase in range(35, 45):
        values = []
        for pos in positions:
            value = 0
            for bit in range(41):
                slot = pos + phase + 2*bit
                value |= (raw[slot // 8] >> (slot % 8) & 1) << bit
            values.append(value)
        lookup.append(dict(slot=phase, responses=[hex(v) for v in values],
                           match_dmstatus=values[-1] & 3 == 0 and
                               (values[-1] >> 2) & 0xffffffff == expected_dmstatus))
    return lookup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "diagnose", "verify"))
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, default=Path("E:/Xilinx/SDK/2018.3"))
    parser.add_argument("--cable-serial", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    need(re.fullmatch(r"[A-Za-z0-9_.:-]+",args.cable_serial), "Invalid cable serial")
    need(args.action == "snapshot" or args.backup is not None, "Pass the preflight backup directory")
    if not args.execute:
        print(f"{args.action}: {BASE:#x}+{BYTES}, read only, cable {args.cable_serial}")
        return
    expected = checked_guards = None
    if args.backup is not None:
        expected = (args.backup/"backup.bin").read_bytes()
        checked_guards = (args.backup/"guards.bin").read_bytes()
        need(len(expected)==BYTES and len(checked_guards)==8,"Unexpected backup sizes")
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"action":args.action,"rows":[]}
    lock = Ownership()
    try:
        port = PhysicalPort(args.out, args.cable_serial, args.sdk)
        try:
            report["probe"] = port.verify_probe(args.pair)
            target = Target(port)
            target.select("50")
            original = target.init()
            report["debug_before"] = original
            runner = None
            try:
                data = target.memory()
                guards = target.guards()
                if args.action == "snapshot":
                    need(data==target.memory() and guards==target.guards(),"Double-read backup changed")
                    (args.out/"backup.bin").write_bytes(data)
                    (args.out/"guards.bin").write_bytes(guards)
                    expected,checked_guards=data,guards
                else:
                    need((data,guards)==(expected,checked_guards),"Existing backup does not match target")
                report["backup_sha256"] = hashlib.sha256(expected).hexdigest()
                if args.action == "diagnose":
                    runner = BlockBenchmark(port,args.out)
                    runner.pattern(expected)
                    runner.configure("50",64,36)
                    baseline=runner.run(1,0)
                    report["at_50"]=baseline
                    need(baseline["passed"], "50 MHz block baseline did not pass")
                    for tap, calibration in ((24,39), (8,38), (16,39)):
                        SETTINGS["200"]=(tap,calibration,256)
                        target.rearm()
                        expected_dmstatus=target.dmi(DMSTATUS)
                        target.select("200")
                        raw_row = {"tap":tap}
                        for split in (False,True):
                            raw_row["split" if split else "contiguous"] = wire_replay(port,split,expected_dmstatus)
                        report.setdefault("raw_replay",[]).append(raw_row)
                        for sample in range(37,44):
                            for idle in (256,20):
                                target.rearm()
                                target.select("200")
                                runner.configure("200",idle,sample)
                                row=dict(tap=tap,slot=sample,idle=idle,**runner.run(1,0))
                                report["rows"].append(row)
                                # No data write follows a mismatched read. Logs
                                # retain both DMI status and first failing word.
                                print(json.dumps(row,separators=(",",":")),flush=True)
                    need(runner.status()[1]==runner.status()[2],"Block runner has not released JTAG")
            finally:
                if runner is not None:
                    mailbox = runner.status()
                    need(mailbox[1] == mailbox[2], "Block runner still owns JTAG")
                try:
                    target.rearm()
                    readback=target.memory()
                    guard_readback=target.guards()
                    if args.action != "snapshot":
                        (args.out/"readback.bin").write_bytes(readback)
                    if expected is not None:
                        report["ram_match"] = readback==expected
                        report["guards_match"] = guard_readback==checked_guards
                        report["readback_sha256"] = hashlib.sha256(readback).hexdigest()
                        need(report["ram_match"] and report["guards_match"],"Final RAM or guard data differs")
                finally:
                    target.cleanup(original)
                    report["debug_restored"] = True
        finally:
            port.close()
    finally:
        lock.close()
        (args.out/"result.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")


if __name__=="__main__":
    main()
