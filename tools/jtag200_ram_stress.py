"""Stress the HPM5301 ILM via the J7 JTAG-only physical MEM-AP0 transport."""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import queue
import random
import re
import struct
import subprocess
import sys
import threading
import time

from jtag200 import PROFILES, ROOT, SCAN_TCL, alignment, bits, waveform
from verify_probe_ocm_code import read_ocm_code

sys.path.insert(0, str(ROOT / "etm-service/tools"))
from probe_ownership import Ownership

PAIR = ROOT / "prebuilt/jtag-only-200mhz-reset-release-20261118"
# Last ILM page via the HPM5301 system-bus alias. Keep guard words outside
# the payload and space for the final pipelined SBA read.
BASE = 0x0105F000
BYTES = 1024
BLOCK = 128
BASELINE = "50"
SETTINGS = {
    # IDELAY tap, capture offset in serializer slots, idle TCKs per DMI
    "50": (0, 36, 64),
    "66.667": (0, 36, 86),
    "80": (8, 35, 103),
    "100": (16, 36, 192),
    "160": (8, 37, 205),
    "200": (8, 39, 256),
}
SBA_ERROR = 0x607000
SBA_RW = 0x1F8000
ACCESS32 = 0x40000
ADDRESS = 0x39
SBCS = 0x38
DATA = 0x3C
DMCONTROL = 0x10
DMSTATUS = 0x11

TCL = r"""
connect -url tcp:127.0.0.1:3121
set serial [lindex $argv 0]
targets -set -filter [format {name =~ "APU" && jtag_cable_serial == "%s"} $serial]
proc physrd {args} {return [mrd -address-space AP0 {*}$args]}
proc physwr {args} {return [mwr -address-space AP0 -bypass-cache-sync {*}$args]}
source [lindex $argv 1]
puts "@READY"
flush stdout
while {[gets stdin cmd] >= 0} {
    if {$cmd eq "quit"} {break}
    set error [catch {uplevel #0 $cmd} result]
    puts [format "@RESULT %d %s" $error [string map [list "\n" " "] $result]]
    flush stdout
}
disconnect
"""


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class PhysicalPort:
    """Keep one scoped XSCT connection during each measurement and cleanup."""

    def __init__(self, folder, cable, sdk):
        self.folder = folder.resolve()
        self.tx = self.folder / "wire-tx.bin"
        self.rx = self.folder / "wire-rx.bin"
        helper = self.folder / "ap0.tcl"
        helper.write_text(TCL, encoding="ascii")
        self.log = (self.folder / "ap0.log").open("w", encoding="utf8", buffering=1)
        self.lines = queue.Queue()
        self.child = subprocess.Popen(
            [sys.executable, str(ROOT / "tools/run_xsct.py"), str(helper),
             cable, str(SCAN_TCL), "--sdk", str(sdk)], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf8", errors="replace", bufsize=1,
        )
        threading.Thread(target=self.collect, daemon=True).start()
        try:
            self.wait("@READY")
        except BaseException:
            self.close()
            raise

    def collect(self):
        for line in self.child.stdout:
            if line.startswith(("@READY", "@RESULT ", "JTAG200_")):
                self.lines.put(line)
            if not line.startswith("@RESULT 0"):
                self.log.write(line)
        self.lines.put(None)

    def wait(self, marker, timeout=15):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"XSCT {marker} timed out")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError(f"XSCT {marker} timed out") from error
            require(line is not None, "XSCT closed unexpectedly")
            if line.startswith(marker):
                return line.rstrip()

    def command(self, text, timeout=15):
        self.child.stdin.write(text + "\n")
        self.child.stdin.flush()
        line = self.wait("@RESULT ", timeout)
        _, status, *value = line.split(maxsplit=2)
        text = value[0] if value else ""
        require(status == "0", f"XSCT command {text}")
        return text

    def close(self):
        try:
            if self.child.poll() is None:
                try:
                    self.child.stdin.write("quit\n")
                    self.child.stdin.flush()
                    self.child.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    self.child.stdin.close()
                    self.child.wait(timeout=10)
        finally:
            self.log.close()

    def scan(self, payload, length):
        self.tx.write_bytes(payload)
        self.command(f"scan_jtag {{{self.tx.as_posix()}}} {{{self.rx.as_posix()}}} {length}")
        return self.rx.read_bytes()

    def verify_probe(self, pair):
        manifest = json.loads((pair / "manifest.json").read_text(encoding="utf8"))
        elf = pair / "application.elf"
        require(hashlib.sha256(elf.read_bytes()).hexdigest() == manifest["sha256"][elf.name],
                "Candidate ELF hash mismatch")
        blob, _, sections = read_ocm_code(elf)
        end = max(section[3] + section[5] for section in sections)
        memory = self.folder / "ocm.bin"
        self.command(f"physrd -force -bin -file {{{memory.as_posix()}}} 0 {(end+3)//4}")
        live = memory.read_bytes()
        require(all(live[s[3]:s[3]+s[5]] == blob[s[4]:s[4]+s[5]] for s in sections),
                "Running J7 executable differs from reset-release candidate")
        return {"executable_bytes": sum(s[5] for s in sections), "pair_sha256": manifest["sha256"]}


def entry(ir):
    return [1]*6 + [0,1,1,0,0,0,0,0,0,1,1,0], [0]*11 + bits(ir,5) + [0,0]


def append_data(tms, tdi, packed, size, idle):
    start = len(tms) + 3
    tms.extend([1,0,0] + [0]*(size-1) + [1,1] + [0]*(1+idle))
    tdi.extend([0]*3 + bits(packed,size) + [0]*(2+idle))
    return start


@lru_cache(maxsize=4096)
def compile_frame(half, advance, idle, operations):
    tms = []
    tdi = []
    starts = []
    for address, value in operations:
        request = address << 34 | (1 if value is None else 2) | ((value or 0) << 2)
        append_data(tms, tdi, request, 41, idle)
        starts.append(len(tms) + 3)
    append_data(tms, tdi, 0, 41, 0)
    words = waveform(tms, tdi, half, tdi_advance=advance)
    return struct.pack(f"<{len(words)}I", *words), len(words), starts


def value_at(frame, half, start, length, phase):
    position = 8 + half + 2 * half * start + phase
    value = 0
    for bit in range(length):
        slot = position + 2 * half * bit
        value |= (frame[(slot // 8) * 4] >> (slot % 8) & 1) << bit
    return value


class Target:
    def __init__(self, port):
        self.port = port
        self.frames = 0
        self.waveform_seconds = 0.0

    def scan(self, tms, tdi):
        words = waveform(tms, tdi, self.half, tdi_advance=self.advance)
        raw = self.port.scan(struct.pack(f"<{len(words)}I", *words), len(words))
        return raw[::4]

    def select(self, rate, clear_dmi=False):
        self.rate = rate
        index, self.half, self.hz = PROFILES[rate]
        self.advance = int(self.half == 2)
        tap, self.phase, self.idle = SETTINGS[rate]
        self.port.command(f"profile {index} {tap} {self.hz} {self.half}")
        for ir, expected in ((1, 0x1000563D), (16, 0x00007071)):
            if ir == 16 and clear_dmi:
                modes, data = entry(ir)
                append_data(modes, data, 1 << 16, 32, 8)
                self.scan(modes, data)
            tms, tdi = entry(ir)
            start = append_data(tms, tdi, 0, 32, 0)
            offsets = alignment(self.scan(tms, tdi), self.half, start, bits(expected, 32))
            require(self.phase in offsets, f"{rate} MHz IR {ir:#x} phases {offsets}, expected {self.phase}")
        self.scan(*entry(17))

    def operations(self, *operations):
        values = []
        for i in range(0, len(operations), 4):
            batch = operations[i:i+4]
            payload, words, starts = compile_frame(self.half, self.advance, self.idle, batch)
            response = self.port.scan(payload, words)
            self.frames += 1
            self.waveform_seconds += words * 8 / (2 * self.half * self.hz)
            for (address, _), start in zip(batch, starts):
                value = value_at(response, self.half, start, 41, self.phase)
                # HPM's upper echo bit can be sampled on the inactive boundary
                # on this setup. Check the six lower address bits and status.
                require(value & 3 == 0 and (value >> 34) & 0x3F == address & 0x3F,
                        f"{self.rate} MHz DMI {address:#x}: raw {value:#013x}")
                values.append((value >> 2) & 0xFFFFFFFF)
        return values

    def dmi(self, address, value=None):
        return self.operations((address, value))[0]

    def init(self):
        controls = self.dmi(DMCONTROL)
        require(controls in (0, 1), f"Existing DMCONTROL flags {controls:#x}")
        if not controls:
            self.dmi(DMCONTROL, 1)
        status, sbcs, address = self.operations((DMSTATUS, None), (SBCS, None), (ADDRESS, None))
        require(status & 0x8F == 0x82 and status & 0xC00 == 0xC00, f"Unexpected DMSTATUS {status:#x}")
        require(sbcs >> 29 == 1 and sbcs & 4 and not sbcs & SBA_ERROR, f"Unexpected SBCS {sbcs:#x}")
        return {"dmcontrol": controls, "dmstatus": status, "sbcs": sbcs, "sbaddress": address}

    def block_address(self, address, count):
        require(address % 4 == 0 and count % 4 == 0
                and BASE-4 <= address < address+count <= BASE+BYTES+4,
                f"Outside guarded ILM window: {address:#x}+{count}")

    def check_sba(self, expected_address):
        status, address = self.operations((SBCS, None), (ADDRESS, None))
        require(not status & SBA_ERROR, f"SBA status {status:#x}")
        require(address == expected_address, f"SBA address {address:#x}, expected {expected_address:#x}")

    def read(self, address, count):
        self.block_address(address, count)
        self.operations((SBCS, 0x158000), (ADDRESS, address))
        words = self.operations(*((DATA, None),) * (count//4))
        # Historical HPM SBA increments on the final prefetch. The extra
        # address is within ILM and the operation is a read.
        self.check_sba(address + count + 4)
        return struct.pack(f"<{count//4}I", *words)

    def write(self, address, data):
        count = len(data)
        self.block_address(address, count)
        require(BASE <= address <= BASE + BYTES - count, "Writes may not include guards")
        self.operations((SBCS, 0x50000), (ADDRESS, address))
        self.check_sba(address)
        values = struct.unpack(f"<{count//4}I", data)
        self.operations(*((DATA, value) for value in values))
        self.check_sba(address + count)

    def guards(self):
        return self.read(BASE-4, 4) + self.read(BASE+BYTES, 4)

    def memory(self):
        return b"".join(self.read(BASE+offset, BLOCK) for offset in range(0, BYTES, BLOCK))

    def rearm(self):
        """Recover known-good JTAG timing without resetting the target CPU."""
        self.select(BASELINE, clear_dmi=True)
        self.dmi(DMCONTROL, 1)
        sbcs = self.dmi(SBCS)
        require(not sbcs & (1 << 21), f"SBA still busy at recovery: {sbcs:#x}")
        self.dmi(SBCS, ACCESS32 | 0x407000)

    def cleanup(self, original):
        self.operations((SBCS, ACCESS32), (ADDRESS, original["sbaddress"]),
                        (SBCS, original["sbcs"] & SBA_RW))
        require(self.dmi(SBCS) & SBA_RW == original["sbcs"] & SBA_RW, "SBCS control restore mismatch")
        self.dmi(DMCONTROL, original["dmcontrol"])
        require(self.dmi(DMCONTROL) == original["dmcontrol"], "DMCONTROL restore mismatch")


def stress(target, rate, number, seconds, start_block=0):
    patterns = []
    random_data = random.Random(5301 + 17 * number)
    for _ in range(BYTES // BLOCK):
        data = random_data.randbytes(BLOCK)
        patterns.append((data, bytes(value ^ 0xFF for value in data)))
    counts = dict(write=0, read=0)
    times = dict(write=0.0, read=0.0)
    old_frames, old_wave = target.frames, target.waveform_seconds
    rounds = 0
    started = time.perf_counter()
    report = {"rate": rate, "round": number, "planned_seconds": seconds}
    try:
        while rounds < BYTES//BLOCK or time.perf_counter() - started < seconds:
            block = (start_block + rounds) % (BYTES//BLOCK)
            address = BASE + block * BLOCK
            expected = patterns[block][(rounds // (BYTES//BLOCK)) & 1]
            before = time.perf_counter()
            target.write(address, expected)
            times["write"] += time.perf_counter() - before
            counts["write"] += BLOCK
            before = time.perf_counter()
            data = target.read(address, BLOCK)
            times["read"] += time.perf_counter() - before
            require(data == expected, f"ILM readback mismatch at {address:#x} after {rounds} blocks")
            counts["read"] += BLOCK
            rounds += 1
    except Exception as error:
        report["error"] = str(error)
    elapsed = time.perf_counter() - started
    report.update(elapsed_s=elapsed, verified_blocks=rounds, bytes=counts, direction_seconds=times,
                  MBps={key: counts[key]/times[key]/1e6 if times[key] else 0 for key in counts},
                  combined_MBps=sum(counts.values())/elapsed/1e6,
                  waveform_frames=target.frames-old_frames,
                  calculated_waveform_seconds=target.waveform_seconds-old_wave)
    return report


def make_plan(rate):
    _, half, _ = PROFILES[rate]
    _, phase, idle = SETTINGS[rate]
    plan = [0, 0, 2 * half]
    frame_count = 0

    def add(direction, operations, credit=0):
        nonlocal frame_count
        for first in range(0, len(operations), 4):
            batch = operations[first:first+4]
            payload, length, starts = compile_frame(
                half, int(half == 2), idle, tuple((a, w) for a, w, _, _ in batch))
            completed_bytes = credit if first + len(batch) == len(operations) else 0
            plan.extend((length, len(batch), direction, completed_bytes))
            plan.extend(struct.unpack(f"<{length}I", payload))
            for (address, _, mask, value), start in zip(batch, starts):
                first_slot = 8 + half + 2 * half * start + phase
                require(first_slot + 80 * half < length * 8, "Response outside prebuilt capture")
                expected = ((address & 0x3F) << 34) | ((value & mask) << 2)
                compare = (0x3F << 34) | (mask << 2) | 3
                plan.extend((first_slot, compare & 0xFFFFFFFF, expected & 0xFFFFFFFF,
                             compare >> 32, expected >> 32))
            frame_count += 1

    def write(address, value):
        return (address, value, 0, 0)

    def read(address, mask, value):
        return (address, None, mask, value)

    def status(address):
        return (read(SBCS, SBA_ERROR, 0), read(ADDRESS, 0xFFFFFFFF, address))

    rng = random.Random(5301)
    payloads = [rng.randbytes(BLOCK) for _ in range(BYTES//BLOCK)]
    for invert in (False, True):
        for index, data in enumerate(payloads):
            if invert:
                data = bytes(value ^ 0xFF for value in data)
            address = BASE + index * BLOCK
            values = struct.unpack(f"<{BLOCK//4}I", data)
            add(1, (write(SBCS, 0x50000), write(ADDRESS, address), *status(address)))
            add(1, tuple(write(DATA, value) for value in values))
            add(1, status(address + BLOCK), credit=BLOCK)
            add(0, (write(SBCS, 0x158000), write(ADDRESS, address)))
            add(0, tuple(read(DATA, 0xFFFFFFFF, value) for value in values))
            add(0, status(address + BLOCK + 4), credit=BLOCK)
    plan[:2] = [len(plan), frame_count]
    require(len(plan) <= 524288 and frame_count <= 512, "Stress plan exceeds probe buffer")
    return struct.pack(f"<{len(plan)}I", *plan)


RUNNER = 0x2FF40


def runner_status(port):
    values = port.command(f"physrd -force -value {RUNNER:#x} 18").split()
    values = [int(value, 0) for value in values]
    require(len(values) == 18 and values[0] == 0x4A535452, f"Wrong stress mailbox: {values[:3]}")
    return values


def upload_plan(port, folder, rate):
    blob = make_plan(rate)
    source = (folder / f"plan-{rate}.bin").resolve()
    echo = (folder / "plan-upload-echo.bin").resolve()
    source.write_bytes(blob)
    length = len(blob) // 4
    port.command(f"physwr -force -bin -file {{{source.as_posix()}}} 0x03000000 {length}", timeout=90)
    port.command(f"physrd -force -bin -file {{{echo.as_posix()}}} 0x03000000 {length}", timeout=90)
    require(echo.read_bytes() == blob, "Probe DDR waveform plan readback differs")
    return hashlib.sha256(blob).hexdigest()


def probe_stress(target, rate, number, seconds, expected):
    port = target.port
    before = runner_status(port)
    require(before[1] == before[2], "Probe stress runner already active")
    seq = (before[1] + 1) & 0xFFFFFFFF
    start = time.perf_counter()
    port.command(f"physwr -force {RUNNER+12:#x} {seconds}; physwr -force {RUNNER+4:#x} {seq}")
    deadline = time.monotonic() + seconds + 30
    for _ in range(seconds+30):
        status = runner_status(port)
        if status[2] == seq:
            break
        require(time.monotonic() < deadline, "Probe runner timed out")
        time.sleep(0.75)
    require(status[2] == seq, "Probe runner did not publish completion")
    host_s = time.perf_counter() - start
    combine = lambda index: (status[index] | status[index+1] << 32)
    divisor = 333333333
    total, read, write = (combine(i)/divisor for i in (10,12,14))
    bytes_count = dict(read=status[6], write=status[7])
    wire_time = status[9] * 8 / (2 * target.half * target.hz)
    result = dict(rate=rate, round=number, planned_seconds=seconds, elapsed_s=total,
                  host_elapsed_s=host_s, verified_blocks=status[6] // BLOCK,
                  bytes=bytes_count, direction_seconds=dict(read=read, write=write),
                  MBps=dict(read=bytes_count["read"]/read/1e6 if read else 0,
                            write=bytes_count["write"]/write/1e6 if write else 0),
                  combined_MBps=sum(bytes_count.values())/total/1e6 if total else 0,
                  waveform_frames=status[8], calculated_waveform_seconds=wire_time)
    if status[4]:
        result.update(error=f"runner code {status[4]}, frame {status[5]}, DMI {combine(16):#x}",
                      failed_frame=status[5], raw_failure=hex(combine(16)))
    else:
        if total < seconds or abs(total - host_s) > 2:
            result["error"] = "A9 timer window differs from the external host time check"
        if bytes_count["read"] != bytes_count["write"] or not bytes_count["read"]:
            result["error"] = "Unbalanced data counts"
        try:
            if target.memory() != expected or target.guards() != target.expected_guard:
                result["error"] = "Independent post-window readback or guard mismatch"
        except RuntimeError as error:
            result["error"] = f"Post-window verification: {error}"
    return result


def prepare(pair, gcc):
    from shutil import copyfile

    pair.mkdir(parents=True, exist_ok=False)
    src = ROOT / "firmware/jtag200"
    app = pair / "application.elf"
    command = [gcc, "-mcpu=cortex-a9", "-marm", "-O3", "-g", "-ffreestanding", "-nostdlib",
               "-DJTAG200_STRESS", "-Wall", "-Wextra", "-Werror", "-Wl,--build-id=none",
               f"-Wl,-T,{src / 'ocm.ld'}", src / "start.S", src / "clock.c",
               ROOT / "firmware/jtag200_stress/runner.c", "-o", app]
    subprocess.run(command, check=True, cwd=ROOT)
    read_ocm_code(app)
    base = json.loads((PAIR / "manifest.json").read_text(encoding="utf8"))
    for name in ("probe.bit", "ps7_init.tcl"):
        require(hashlib.sha256((PAIR/name).read_bytes()).hexdigest() == base["sha256"][name],
                f"Baseline hash mismatch: {name}")
        copyfile(PAIR/name, pair/name)
    manifest = dict(name="J7 JTAG stress fixture", bit_source_revision=base["source_revision"],
                    firmware_source_revision=subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    flags=command[1:10], timing=base["timing"], nominal_tck_hz=base["nominal_tck_hz"],
                    sha256={name: hashlib.sha256((pair/name).read_bytes()).hexdigest()
                            for name in ("probe.bit", "ps7_init.tcl", "application.elf")})
    (pair / "manifest.json").write_text(json.dumps(manifest,indent=2)+"\n", encoding="utf8")
    print(pair)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cable-serial")
    ap.add_argument("--probe-pair", type=Path, help="Running stress fixture pair; omit for AP0 pilot")
    ap.add_argument("--prepare-pair", type=Path, help="Build the isolated OCM runner without hardware")
    ap.add_argument("--gcc", type=Path, default=Path(
        "E:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sdk", type=Path, default=Path("E:/Xilinx/SDK/2018.3"))
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--pilot", action="store_true", help="Only 50 MHz, single short round")
    args = ap.parse_args()
    if args.prepare_pair:
        prepare(args.prepare_pair.resolve(), args.gcc)
        return
    require(args.cable_serial and re.fullmatch(r"[A-Za-z0-9_.:-]+", args.cable_serial),
            "Missing or invalid cable serial")
    require(args.out is not None, "Missing --out")
    if not args.execute:
        print(f"HPM5301 ILM {BASE:#x}+{BYTES}; {args.cable_serial}; "
              f"{'50 MHz pilot' if args.pilot else 'six rates; 3x60 s at 100/200 and 3x10 s elsewhere'}")
        return

    args.out.mkdir(parents=True, exist_ok=False)
    report = {"cable": args.cable_serial, "base": hex(BASE), "bytes": BYTES, "block_bytes": BLOCK, "rates": []}
    output = args.out / "result.json"
    def save():
        temp = output.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2)+"\n", encoding="utf8")
        temp.replace(output)

    lease = Ownership()
    try:
        port = PhysicalPort(args.out, args.cable_serial, args.sdk)
        try:
            report["probe"] = port.verify_probe(args.probe_pair or PAIR)
            if args.probe_pair:
                runner_status(port)
            report["transport"] = "Zynq OCM/GP0 local runner" if args.probe_pair else "XSCT physical MEM-AP0"
            target = Target(port)
            target.select(BASELINE)
            original = target.init()
            report["debug_before"] = original
            saved = None
            changed = False
            try:
                guard = target.guards()
                saved = target.memory()
                require(saved == target.memory() and target.guards() == guard,
                        "Two backups or guard reads differ")
                (args.out / "backup.bin").write_bytes(saved)
                (args.out / "guard.bin").write_bytes(guard)
                report["backup_sha256"] = hashlib.sha256(saved).hexdigest()
                save()
                print(f"Backup verified, {BYTES} bytes: {report['backup_sha256']}", flush=True)
                target.expected_guard = guard
                rng = random.Random(5301)
                probe_after = bytes(value ^ 0xFF for value in rng.randbytes(BYTES))
                rates = [BASELINE] if args.pilot else list(PROFILES)
                for rate in rates:
                    seconds = 1 if args.pilot else 60 if rate in ("100", "200") else 10
                    if args.probe_pair:
                        report.setdefault("plan_sha256", {})[rate] = upload_plan(port, args.out, rate)
                    for number in ((1,) if args.pilot else range(4)):
                        wall_window = seconds if number else 1
                        target.select(rate)
                        changed = True
                        if args.probe_pair:
                            run = probe_stress(target, rate, number, wall_window, probe_after)
                        else:
                            run = stress(target, rate, number, wall_window)
                        report["rates"].append(run)
                        save()
                        print(json.dumps(run, separators=(",", ":")), flush=True)
                        # Continue only after proving the backup can still be
                        # restored. Failed rounds remain in the evidence.
                        if run.get("error"):
                            target.rearm()
                            for i in range(0, BYTES, BLOCK):
                                target.write(BASE+i, saved[i:i+BLOCK])
                            require(target.memory() == saved and target.guards() == guard,
                                    "Independent baseline recovery after failed round did not match")
                            run["baseline_recovery_verified"] = True
                            save()
            finally:
                if changed:
                    if args.probe_pair:
                        mailbox = runner_status(port)
                        require(mailbox[1] == mailbox[2], "Probe runner still owns scan buffers; backup retained")
                    # Keep the journal on disk before the first write and
                    # use the known-good 50 MHz path for cleanup.
                    target.rearm()
                    for i in range(0, BYTES, BLOCK):
                        target.write(BASE+i, saved[i:i+BLOCK])
                    restored = target.memory()
                    (args.out / "restored.bin").write_bytes(restored)
                    report["restored_sha256"] = hashlib.sha256(restored).hexdigest()
                    report["restored_match"] = restored == saved
                    report["guards_match"] = target.guards() == guard
                    save()
                    require(report["restored_match"] and report["guards_match"],
                            "Final ILM/guard readback differs from backup")
                target.cleanup(original)
                report["debug_state_restored"] = True
                save()
        finally:
            port.close()
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        lease.close()
        save()


if __name__ == "__main__":
    main()
