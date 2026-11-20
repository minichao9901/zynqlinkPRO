"""Check concurrent RTT and sampling from a running F103ZE SRAM producer."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np

from benchmark_rtt_forward import core_read, core_write
from selectio_f103_fixture import BASE, DHCSR, ROOT, low_link


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial", default="12345678")
    ap.add_argument("--transport", choices=("jtag", "swd"), required=True)
    ap.add_argument("--slot", type=int, required=True)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--binary", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    if not args.execute:
        print("Run inside selectio_f103_fixture.py. Save core registers, run the SRAM producer and recover.")
        return
    code = args.binary.read_bytes()
    if not 0 < len(code) < 512 or args.seconds <= 0:
        ap.error("invalid SRAM producer or duration")
    args.out.mkdir(parents=True, exist_ok=False)
    rtt = args.out / "capture.rtt"
    scope = args.out / "capture.csv"
    report = dict(transport=args.transport, producer_sha256=hashlib.sha256(code).hexdigest())
    registers = [*range(17), 20]
    with low_link(args.serial) as mem:
        if not mem.word(DHCSR) & (1 << 17):
            raise RuntimeError("the enclosing fixture must halt and back up the target")
        regs = {i: core_read(mem, i) for i in registers}
        backup = mem.read(BASE, 4096)
    (args.out / "core-before.json").write_text(json.dumps(regs))
    try:
        with low_link(args.serial) as mem:
            mem.write(BASE, code)
            mem.write(BASE+0x200, struct.pack("<16sII6II", b"SEGGER RTT", 1, 0, 0, BASE+0x400, 1024, 0, 0, 0, 0))
            mem.write_word(BASE+0x820, 0x13579bdf)
            if mem.read(BASE, len(code)) != code:
                raise RuntimeError("SRAM producer differs")
            core_write(mem, 16, 0x01000000)
            core_write(mem, 20, 1)
            core_write(mem, 15, BASE+1)
            mem.write_word(DHCSR, 0xa05f0001)
        tap, idle = (16, 33) if args.transport == "jtag" else (8, 2)
        cmd = [sys.executable, "-X", "utf8", ROOT/"toolbox.py", "selectio", "--serial", args.serial,
               "combo", "--transport", args.transport, "--tap", tap, "--slot", args.slot, "--idle", idle,
               "--rtt-address", hex(BASE+0x200), "--ticks", 24000, "--var", hex(BASE+0x230),
               "--var", hex(BASE+0x820), "--seconds", args.seconds, "--rtt-out", rtt, "--scope-out", scope]
        p = subprocess.run(list(map(str, cmd)), capture_output=True)
        (args.out/"cli.log").write_bytes(p.stdout+p.stderr)
        p.check_returncode()
        report.update(json.loads(p.stdout))
        with low_link(args.serial) as mem:
            mem.write_word(DHCSR, 0xa05f0003)
            wr, rd, produced = (mem.word(BASE+i) for i in (0x224,0x228,0x230))
        count = 0
        digest = hashlib.sha256()
        with rtt.open("rb") as f:
            while block := f.read(1 << 20):
                digest.update(block)
                words = np.frombuffer(block, dtype="<u4")
                if not np.array_equal(words, np.arange(count, count+len(words), dtype="<u4")):
                    raise RuntimeError(f"RTT word sequence mismatch in block at {count}")
                count += len(words)
        if count < 256 or count*4 != report["rtt_bytes"] or rd != count*4 % 1024 or abs(count*4+(wr-rd)%1024-4*produced) > 4:
            raise RuntimeError("target ring, probe and host counts differ")
        last = -1
        groups = 0
        with scope.open(newline="") as f:
            rows = csv.reader(f)
            next(rows)
            for tick, value, guard in rows:
                if int(value) < last or int(guard) != 0x13579bdf:
                    raise RuntimeError("variable value mismatch")
                last = int(value)
                groups += 1
        if groups != report["sample_groups"] or last <= 0:
            raise RuntimeError("sample count differs")
        report.update(sequence_words=count, sha256=digest.hexdigest(), producer_counter=produced,
                      RTT_MBps=count*4/report["elapsed_seconds"]/1e6, passed=True)
    finally:
        try:
            with low_link(args.serial) as mem:
                mem.write_word(DHCSR, 0xa05f0003)
                if not mem.word(DHCSR) & (1 << 17):
                    raise RuntimeError("target halt failed during recovery")
                mem.write(BASE, backup)
                for i in [*range(15),20,16,15]:
                    core_write(mem, i, regs[i])
                if mem.read(BASE,4096) != backup or any(core_read(mem,i) != regs[i] for i in registers):
                    raise RuntimeError("producer core or SRAM restoration failed")
                report["restored"] = True
        finally:
            (args.out/"result.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
