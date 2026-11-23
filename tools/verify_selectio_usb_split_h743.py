"""Check the split USB pipes with a guarded H743 AXI-SRAM fixture."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import time

import numpy as np
import usb.util

from benchmark_rtt_forward import core_read, core_write
from dap_pipeline_bench import cmd, open_dap, setup
from selectio_native import native_connection
from selectio_rtt import Ring
from selectio_scope import export_scope
from target_snapshot import same_clock_configuration, snapshot
from test_probe_board import Memory

BASE = 0x24040000
SIZE = 0x5000
CONTROL_BLOCK = BASE + 0x200
SAMPLES = BASE + 0x800
VALUES = tuple(0x13579bdf ^ (i * 0x1234567) for i in range(8))
DHCSR, CCR = 0xe000edf0, 0xe000ed14
PROFILE = (1, 8, 24, 4)
HZ = 50_000_000


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def halt(mem):
    mem.write_word(DHCSR, 0xa05f0003)
    for _ in range(100):
        if mem.word(DHCSR) & (1 << 17):
            return
    raise RuntimeError("H743 core did not halt")


def fixture(producer=b""):
    data = bytearray(SIZE)
    data[:len(producer)] = producer
    struct.pack_into("<16sII", data, 0x200, b"SEGGER RTT", 1, int(not producer))
    struct.pack_into("<6I", data, 0x218, 0, BASE + 0x1000, 8192, 0, 0, 0)
    if not producer:
        struct.pack_into("<6I", data, 0x230, 0, BASE + 0x3000, 128, 126, 126, 0)
    struct.pack_into("<8I", data, 0x800, *VALUES)
    return data


def build_producer(folder):
    gcc = shutil.which("arm-none-eabi-gcc")
    require(gcc is not None, "arm-none-eabi-gcc missing")
    gcc = Path(gcc)
    objcopy = gcc.with_name("arm-none-eabi-objcopy" + gcc.suffix)
    elf, binary = folder / "producer.elf", folder / "producer.bin"
    source = Path(__file__).resolve().parents[1] / "firmware/target/probe_rtt_ram.S"
    subprocess.run([gcc, "-mcpu=cortex-m3", "-mthumb", "-nostdlib", "-Wl,--build-id=none",
                    f"-Wl,-Ttext={BASE:#x}", f"-Wa,--defsym,FIXTURE_BASE={BASE:#x}",
                    "-Wa,--defsym,RTT_FROM_DESCRIPTOR=1", "-Wl,-e,producer", source, "-o", elf], check=True)
    subprocess.run([objcopy, "-O", "binary", "-j", ".text", elf, binary], check=True)
    data = binary.read_bytes()
    require(0 < len(data) < 0x200, "unexpected producer length")
    return data


def memory_and_down(native, mem):
    addr = BASE + 0x3020
    size = 4032
    pattern = hashlib.shake_256(b"split-axi-sram").digest(size)
    with native.memory(*PROFILE, HZ):
        require(native.bulk(addr, size, pattern) == b"", "missing write completion")
        require(native.bulk(addr, size) == pattern, "native SRAM read mismatch")
        clock = native.memory_clock(1, 200_000_000, HZ)
    require(mem.read(addr, size) == pattern, "independent SRAM readback mismatch")
    # The two directions of EP7 carry the terminal transactions, including wrap.
    with native.memory(*PROFILE, HZ, rtt=True):
        down = Ring(native, CONTROL_BLOCK, 0, True)
        payload = b"split-RTT-DOWN"
        sent = down.send(payload)
        sent += down.send(payload[sent:])
    require(sent == len(payload) and mem.read(BASE + 0x307e, 2) + mem.read(BASE + 0x3000, 12) == payload,
            "RTT DOWN wrap mismatch")
    return dict(read_write_bytes=size, rtt_down=sent, clock=clock)


def scope_only(native, folder, seconds):
    native.exchange(0, 2, bytes(PROFILE))
    channel = 3
    record = folder / "scope.hss"

    def control(op, data=b"", busy=False):
        rc, state = native.control(channel, op, data)
        require(rc == 0 or (busy and rc == -7), f"HSS action {op} failed: {rc}, {state}")
        return rc, state

    native.exchange(channel, 0, b"\1")
    started = False
    try:
        control(12, b"\1")
        control(3, struct.pack("<I", HZ))
        plan = struct.pack("<IBB", 24000, 0, 8)
        plan += b"".join(struct.pack("<IBB", SAMPLES + 4*i, 4, 4) for i in range(8))
        control(10, plan)
        control(1)
        started = True
        with record.open("xb") as fh:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                fh.write(native.exchange(channel, 1))
            stop_end = time.monotonic() + 3
            while control(0, busy=True)[0]:
                require(time.monotonic() < stop_end, "HSS STOP did not retire")
                fh.write(native.exchange(channel, 1))
            started = False
            while data := native.exchange(channel, 1):
                fh.write(data)
        state = control(2)[1]
        check = export_scope(record, expected=struct.pack("<8I", *VALUES))
        require(state[2] == check["groups"] and check["groups"] > 0, "HSS STOP group total mismatch")
        return check
    finally:
        if started:
            native.control(channel, 0)
        native.exchange(channel, 0, b"\0")


def combo(native, mem, folder, seconds, sample_hz):
    args = struct.pack("<4BIIBBBB8I", *PROFILE, CONTROL_BLOCK, 24_000_000 // sample_hz, 8, 0, 1, 0,
                       *(SAMPLES + 4*i for i in range(8)))
    groups = received = 0
    layout = struct.Struct("<9I")
    data = folder / "rtt.bin"

    def save_pair(payload, values, sink, writer):
        nonlocal received, groups
        require(len(values) % layout.size == 0, "partial HSS group")
        sink.write(payload)
        received += len(payload)
        for row in layout.iter_unpack(values):
            require(row[1:] == VALUES, "combined sampling value mismatch")
            writer.writerow(row)
            groups += 1

    native.exchange(6, 0, args)
    stopped = False
    try:
        start = time.monotonic()
        with data.open("xb") as sink, (folder / "combo.csv").open("x", newline="") as scope:
            writer = csv.writer(scope)
            writer.writerow(["tick_24mhz", *(f"sample_{i}" for i in range(8))])
            # Leave EP8 unread while EP5 replies and EP7 are independently drained.
            time.sleep(.050)
            scope_seq = native._write(6, 2, b"")
            check = struct.unpack("<8I", native.exchange(6, 4))
            require(check[0] and not check[1], "control response while EP8 was unread failed")
            save_pair(native.exchange(6, 1), native._read(6, 2, scope_seq), sink, writer)
            end = start + seconds
            while time.monotonic() < end:
                save_pair(*native.pull_combo(True), sink, writer)
            native.exchange(6, 3)
            stopped = True
            while True:
                payload, values = native.pull_combo(True)
                if not (payload or values):
                    break
                save_pair(payload, values, sink, writer)
        state = struct.unpack("<8I", native.exchange(6, 4))
        elapsed = time.monotonic()-start
        native.exchange(6, 5)
        require(state[:2] == (0, 0) and state[3:7] == (received, received, groups, groups),
                f"combined STOP totals mismatch: {state}")
        require(received >= 4096 and groups > 0 and received % 4 == 0, "insufficient combined data")
        words = np.memmap(data, dtype="<u4", mode="r")
        for offset in range(0, len(words), 1 << 18):
            end_word = min(offset + (1 << 18), len(words))
            require(np.array_equal(words[offset:end_word], np.arange(offset, end_word, dtype="<u4")),
                    f"RTT sequence mismatch at {offset}")
        del words
        halt(mem)
        return dict(bytes=received, groups=groups, skipped=state[7], sample_hz=sample_hz,
                    skipped_fraction=state[7]/(groups+state[7]), duration_seconds=elapsed,
                    control_while_scope_unread=True, stop=list(state))
    finally:
        if not stopped:
            native.exchange(6, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="12345678")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--combo-hz", type=int, default=250, help="combined RTT/HSS sample groups per second")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0 or not 1<=args.combo_hz<=24000:
        parser.error("seconds must be positive and combo-hz must be 1..24000")
    if not args.execute:
        print("H743 AXI SRAM read/write, RTT DOWN wrap, eight-variable HSS, concurrent RTT/HSS and STOP, with state restoration.")
        return 0
    args.out.mkdir(parents=True, exist_ok=False)
    producer = build_producer(args.out)
    report = {}
    dev, out, inp = open_dap(args.serial)
    mem = Memory(out, inp)
    original = registers = clocks = None
    initial = dcrdr = None
    try:
        setup(out, inp, 1000, "swd")
        clocks = report["target"] = snapshot(mem)
        require(clocks["cpuid"] == "0x411fc271" and clocks["device"] == "0x20036450", "unexpected target")
        require(mem.word(CCR) & (1 << 16) == 0, "AXI SRAM fixture requires D-cache disabled")
        initial = mem.word(DHCSR)
        halt(mem)
        dcrdr = mem.word(0xe000edf8)
        registers = {i: core_read(mem, i) for i in (*range(19), 20)}
        require(not registers[16] & 0x1ff, "fixture requires Thread mode")
        original = mem.read(BASE - 4, SIZE + 8)
        require(original == mem.read(BASE - 4, SIZE + 8), "unstable backup")
        (args.out / "backup.bin").write_bytes(original)
        recovery = dict(base=BASE-4, sha256=hashlib.sha256(original).hexdigest(),
                        registers=registers, dhcsr=initial, dcrdr=dcrdr, clocks=clocks)
        (args.out / "recovery.json").write_text(json.dumps(recovery, indent=2)+"\n", encoding="utf8")
        with native_connection(args.serial, dev) as native:
            native.info()
            require(native.split, "expected split-endpoint firmware")
            report["usb"] = native.usb_descriptors()
            mem.write(BASE, fixture())
            report["memory"] = memory_and_down(native, mem)
            report["scope"] = scope_only(native, args.out, args.seconds)
            mem.write(BASE, fixture(producer))
            core_write(mem, 16, 0x01000000)
            core_write(mem, 20, 1)
            core_write(mem, 15, BASE + 1)
            mem.write_word(DHCSR, 0xa05f0001)
            report["combo"] = combo(native, mem, args.out, args.seconds, args.combo_hz)
        report["passed"] = True
    except BaseException as error:
        report["failure"] = str(error)
        raise
    finally:
        try:
            if initial is not None:
                setup(out, inp, 1000, "swd")
                halt(mem)
                if original is not None:
                    mem.write(BASE - 4, original)
                    require(mem.read(BASE - 4, SIZE + 8) == original, "SRAM restoration differs")
                if registers is not None:
                    for i, value in registers.items():
                        core_write(mem, i, value)
                    require(all(core_read(mem, i) == value for i, value in registers.items()), "core restoration differs")
                if dcrdr is not None:
                    mem.write_word(0xe000edf8, dcrdr)
                require(same_clock_configuration(clocks, snapshot(mem)), "target clock state differs")
                mem.write_word(DHCSR, 0xa05f0000 | (initial & 0x2f))
                report["restored"] = bool(mem.word(DHCSR) & (1 << 17)) == bool(initial & (1 << 17))
                require(report["restored"], "initial run/halt state differs")
                cmd(out, inp, [3])
        finally:
            (args.out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
            usb.util.dispose_resources(dev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
