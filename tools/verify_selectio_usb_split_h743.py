"""Check the split USB pipes with guarded H743 AXI SRAM and DTCM fixtures."""
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
from selectio_native import NativeStatusError, native_connection
from selectio_pipeline_bench import measure_window
from selectio_rtt import Ring
from selectio_scope import export_scope
from target_snapshot import same_clock_configuration, snapshot
from test_probe_board import Memory

AXI_BASE = 0x24040000
DTCM_BASE = 0x20008000
SIZE = 0x5000
CONTROL_OFFSET = 0x200
SAMPLES_OFFSET = 0x800
VALUES = tuple(0x13579bdf ^ (i * 0x1234567) for i in range(8))
DHCSR, CCR = 0xe000edf0, 0xe000ed14
DEFAULT_PROFILES = {"swd": (1, 8, 24, 4), "jtag": (2, 16, 28, 33)}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def halt(mem):
    mem.write_word(DHCSR, 0xa05f0003)
    for _ in range(100):
        if mem.word(DHCSR) & (1 << 17):
            return
    raise RuntimeError("H743 core did not halt")


def fixture(base, running=False):
    data = bytearray(SIZE)
    struct.pack_into("<16sII", data, 0x200, b"SEGGER RTT", 1, int(not running))
    struct.pack_into("<6I", data, 0x218, 0, base + 0x1000, 8192, 0, 0, 0)
    if not running:
        struct.pack_into("<6I", data, 0x230, 0, base + 0x3000, 128, 126, 126, 0)
    struct.pack_into("<8I", data, 0x800, *VALUES)
    return data


def build_producer(folder, code_base, data_base):
    gcc = shutil.which("arm-none-eabi-gcc")
    require(gcc is not None, "arm-none-eabi-gcc missing")
    gcc = Path(gcc)
    objcopy = gcc.with_name("arm-none-eabi-objcopy" + gcc.suffix)
    elf, binary = folder / "producer.elf", folder / "producer.bin"
    source = Path(__file__).resolve().parents[1] / "firmware/target/probe_rtt_ram.S"
    subprocess.run([gcc, "-mcpu=cortex-m3", "-mthumb", "-nostdlib", "-Wl,--build-id=none",
                    f"-Wl,-Ttext={code_base:#x}", f"-Wa,--defsym,FIXTURE_BASE={data_base:#x}",
                    "-Wa,--defsym,RTT_FROM_DESCRIPTOR=1", "-Wl,-e,producer", source, "-o", elf], check=True)
    subprocess.run([objcopy, "-O", "binary", "-j", ".text", elf, binary], check=True)
    data = binary.read_bytes()
    require(0 < len(data) < 0x200, "unexpected producer length")
    return data


def memory_and_down(native, mem, profile, clock_hz, base):
    addr = base + 0x3020
    size = 4032
    pattern = hashlib.shake_256(b"split-axi-sram").digest(size)
    denied = None
    with native.memory(*profile, clock_hz):
        if profile[0] == 2:
            request = struct.pack("<BBHI", 0, 0, 1, 0x24043000).ljust(16, b"\0")
            try:
                native.exchange(1, 6, request)
            except NativeStatusError as error:
                denied = error.status
            require(denied == 1, "JTAG invalid AXI page was not rejected")
        require(native.bulk(addr, size, pattern) == b"", "missing write completion")
        require(native.bulk(addr, size) == pattern, "native SRAM read mismatch")
        clock = native.memory_clock(profile[0], 200_000_000, clock_hz)
    require(mem.read(addr, size) == pattern, "independent SRAM readback mismatch")
    # The two directions of EP7 carry the terminal transactions, including wrap.
    with native.memory(*profile, clock_hz, rtt=True):
        down = Ring(native, base + CONTROL_OFFSET, 0, True)
        payload = b"split-RTT-DOWN"
        sent = down.send(payload)
        sent += down.send(payload[sent:])
    require(sent == len(payload) and mem.read(base + 0x307e, 2) + mem.read(base + 0x3000, 12) == payload,
            "RTT DOWN wrap mismatch")
    return dict(address=hex(addr), read_write_bytes=size, rtt_down=sent, clock=clock, invalid_axi_status=denied)


def rtt_only(native, mem, profile, clock_hz, base):
    payload = hashlib.shake_256(b"H743 isolated RTT UP").digest(257)
    ring, length, tail = base + 0x1000, 8192, 129
    mem.write(ring + length - tail, payload[:tail])
    mem.write(ring, payload[tail:])
    mem.write(base + CONTROL_OFFSET + 36, struct.pack("<II", len(payload) - tail, length - tail))
    result, received = capture_rtt(native, profile, clock_hz, base, 3, limit=len(payload))
    require(received == payload, "RTT UP wrap mismatch")
    return {name: result[name] for name in ("bytes", "sha256", "stop")}


def capture_rtt(native, profile, clock_hz, base, seconds, limit=None, chunk=1024):
    native.exchange(0, 2, bytes(profile))
    channel = 2
    native.exchange(channel, 0, b"\1")
    started = False
    try:
        for op, data in ((12, bytes((profile[0],))), (7, struct.pack("<IHBB", clock_hz, chunk, 0, 1)),
                         (1, struct.pack("<IIB", base + CONTROL_OFFSET, 256, 0))):
            rc, _ = native.control(channel, op, data)
            require(rc == 0, f"RTT UP control {op}: {rc}")
        started = True
        received = bytearray()
        start = time.monotonic()
        while time.monotonic() < start + seconds and (limit is None or len(received) < limit):
            received.extend(native.exchange(channel, 1))
        elapsed = time.monotonic() - start
        window_bytes = len(received)
        stop_end = time.monotonic() + 3
        while True:
            rc, status = native.control(channel, 0)
            if rc == 0:
                break
            require(rc == -7 and time.monotonic() < stop_end, f"RTT UP STOP: {rc}, {status}")
            received.extend(native.exchange(channel, 1))
        started = False
        while data := native.exchange(channel, 1):
            received.extend(data)
        require(status[3] == len(received) and not status[5], f"RTT UP STOP totals: {status}")
        return dict(bytes=len(received), window_bytes=window_bytes, seconds=elapsed, chunk_bytes=chunk,
                    MBps=window_bytes / elapsed / 1e6, sha256=hashlib.sha256(received).hexdigest(),
                    stop=list(status)), received
    finally:
        if started:
            native.control(channel, 0)
        native.exchange(channel, 0, b"\0")


def scope_only(native, folder, seconds, profile, clock_hz, count, base, ticks=24000):
    native.exchange(0, 2, bytes(profile))
    channel = 3
    record = folder / f"scope-{count}.hss"

    def control(op, data=b"", busy=False):
        rc, state = native.control(channel, op, data)
        require(rc == 0 or (busy and rc == -7), f"HSS action {op} failed: {rc}, {state}")
        return rc, state

    native.exchange(channel, 0, b"\1")
    started = False
    try:
        control(12, bytes((profile[0],)))
        control(3, struct.pack("<I", clock_hz))
        plan = struct.pack("<IBB", ticks, 0, count)
        plan += b"".join(struct.pack("<IBB", base + SAMPLES_OFFSET + 4*i, 4, 4) for i in range(count))
        control(10, plan)
        control(1)
        started = True
        with record.open("xb") as fh:
            start = time.monotonic()
            while time.monotonic() < start + seconds:
                fh.write(native.exchange(channel, 1))
            elapsed = time.monotonic() - start
            stop_end = time.monotonic() + 3
            while control(0, busy=True)[0]:
                require(time.monotonic() < stop_end, "HSS STOP did not retire")
                fh.write(native.exchange(channel, 1))
            started = False
            while data := native.exchange(channel, 1):
                fh.write(data)
        state = control(2)[1]
        check = export_scope(record, expected=struct.pack(f"<{count}I", *VALUES[:count]))
        require(state[2] == check["groups"] and check["groups"] > 0, "HSS STOP group total mismatch")
        groups = check["groups"]
        skipped = check["stat"]["skipped"]
        check.update(requested_ticks=ticks, window_seconds=elapsed, host_groups_per_second=groups / elapsed,
                     skipped_fraction=skipped / (groups + skipped))
        return check
    finally:
        if started:
            native.control(channel, 0)
        native.exchange(channel, 0, b"\0")


def combo(native, mem, folder, seconds, sample_hz, profile, clock_hz, base):
    args = struct.pack("<4BIIBBBB8I", *profile, base + CONTROL_OFFSET, 24_000_000 // sample_hz, 8, 0,
                       int(clock_hz == 50_000_000), 0,
                       *(base + SAMPLES_OFFSET + 4*i for i in range(8)))
    if clock_hz not in (50_000_000, 100_000_000):
        args += struct.pack("<I", clock_hz)
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


def sram_throughput(native, mem, profile, clock_hz, base, seconds):
    address, n, depth = base + 0x3020, 4032, 4
    guards = (mem.word(address - 4), mem.word(address + n))
    rows = {}
    for direction in ("read", "write"):
        expected = hashlib.shake_256(direction.encode()).digest(n)
        with native.memory(*profile, clock_hz):
            native.bulk(address, n, expected)
            require(native.bulk(address, n) == expected, "speed test prefill failed")
            before = native.memory_stats()
            count, elapsed, _, _, expected = measure_window(
                native, direction, address, n, depth, seconds, 0, 0, expected)
            after = native.memory_stats()
            clock = native.memory_clock(profile[0], 200_000_000, clock_hz)
        require(after[f"{direction}_bytes"] - before[f"{direction}_bytes"] == count * n,
                "SRAM counter differs from host")
        require(mem.read(address, n) == expected, "SRAM performance readback differs")
        require((mem.word(address - 4), mem.word(address + n)) == guards, "SRAM performance guard differs")
        rows[direction] = dict(clock=clock, requests=count, transaction_bytes=n, depth=depth,
                               seconds=elapsed, MBps=count * n / elapsed / 1e6)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="12345678")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--transport", choices=DEFAULT_PROFILES, default="swd")
    parser.add_argument("--clock", type=int, default=50_000_000, help="requested debug wire clock in Hz")
    parser.add_argument("--tap", type=int, choices=range(32))
    parser.add_argument("--slot", type=int, choices=range(64))
    parser.add_argument("--idle", type=int, choices=range(256))
    parser.add_argument("--combo-hz", type=int, default=250, help="combined RTT/HSS sample groups per second")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--performance", action="store_true", help="time verified SRAM and standalone RTT")
    mode.add_argument("--scope-only", action="store_true", help="validate only the guarded single/eight-variable HSS streams")
    mode.add_argument("--data-only", action="store_true", help="time only verified SRAM and standalone RTT")
    parser.add_argument("--rtt-chunk", type=int, choices=(1024, 2048), default=1024,
                        help="standalone performance RTT maximum reads per dequeue in bytes")
    parser.add_argument("--scope-ticks", type=int, nargs=2, default=(24000, 24000), metavar=("ONE", "EIGHT"),
                        help="24 MHz sample period ticks for single and eight variable plans")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0 or not 1 <= args.combo_hz <= 24000 or not 50_000_000 <= args.clock <= 100_000_000:
        parser.error("seconds must be positive, combo-hz must be 1..24000, clock must be 50..100 MHz")
    if any(not 1 <= ticks <= 0xffffffff for ticks in args.scope_ticks):
        parser.error("scope ticks must be positive u32 values")
    port, tap, slot, idle = DEFAULT_PROFILES[args.transport]
    profile = (port, tap if args.tap is None else args.tap,
               slot if args.slot is None else args.slot, idle if args.idle is None else args.idle)
    if port == 1 and profile[3] > 15 or port == 2 and (profile[2] < 16 or profile[3] % 2 == 0):
        parser.error("SWD requires idle 0..15; JTAG requires slot >=16 and odd idle")
    if not args.execute:
        print("H743 SRAM read/write, RTT UP/DOWN wrap, one/eight-variable HSS and concurrent RTT/HSS with state restoration.")
        return 0
    performance = args.performance or args.data_only
    args.out.mkdir(parents=True, exist_ok=False)
    base = AXI_BASE if port == 1 else DTCM_BASE
    # Execute the producer from AXI SRAM while JTAG serves DTCM data.
    code_base = base if port == 1 else 0x24050000
    producer = None if args.scope_only else build_producer(args.out, code_base, base)
    report = dict(transport=args.transport, requested_hz=args.clock, tap=profile[1], slot=profile[2], idle=profile[3])
    dev, out, inp = open_dap(args.serial)
    mem = Memory(out, inp)
    original = original_code = registers = clocks = None
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
        original = mem.read(base - 4, SIZE + 8)
        require(original == mem.read(base - 4, SIZE + 8), "unstable backup")
        (args.out / "backup.bin").write_bytes(original)
        recovery = dict(base=base-4, sha256=hashlib.sha256(original).hexdigest(),
                        registers=registers, dhcsr=initial, dcrdr=dcrdr, clocks=clocks)
        if producer is not None and code_base != base:
            original_code = mem.read(code_base, 512)
            require(original_code == mem.read(code_base, 512), "unstable producer backup")
            (args.out / "backup-code.bin").write_bytes(original_code)
            recovery.update(code_base=code_base, code_sha256=hashlib.sha256(original_code).hexdigest())
        (args.out / "recovery.json").write_text(json.dumps(recovery, indent=2)+"\n", encoding="utf8")
        with native_connection(args.serial, dev) as native:
            native.info()
            require(native.split, "expected split-endpoint firmware")
            report["usb"] = native.usb_descriptors()
            mem.write(base, fixture(base))
            if port == 2:
                setup(out, inp, 1000, "jtag")
            if not args.scope_only:
                report["memory"] = memory_and_down(native, mem, profile, args.clock, base)
            if performance:
                report["sram_performance"] = sram_throughput(native, mem, profile, args.clock, base, args.seconds)
            if not args.data_only:
                # Match the public CLI's fresh DAP connection for each standalone scope session.
                for count, key, ticks in zip((1, 8), ("scope_single", "scope"), args.scope_ticks):
                    cmd(out, inp, [3])
                    setup(out, inp, 1000, args.transport)
                    report[key] = scope_only(native, args.out, args.seconds, profile, args.clock, count, base, ticks)
            if producer is None:
                report["passed"] = True
                return 0
            cmd(out, inp, [3])
            setup(out, inp, 1000, args.transport)
            report["rtt_up"] = rtt_only(native, mem, profile, args.clock, base)
            mem.write(base, fixture(base, running=True))
            mem.write(code_base, producer)
            require(mem.read(code_base, len(producer)) == producer, "RTT producer readback differs")
            if mem.word(CCR) & (1 << 17):
                mem.write_word(0xe000ef50, 0)
            core_write(mem, 16, 0x01000000)
            core_write(mem, 20, 1)
            core_write(mem, 15, code_base + 1)
            mem.write_word(DHCSR, 0xa05f0001)
            if performance:
                rate, data = capture_rtt(native, profile, args.clock, base, args.seconds, chunk=args.rtt_chunk)
                require(len(data) >= 4096 and len(data) % 4 == 0, "insufficient continuous RTT data")
                words = np.frombuffer(data, dtype="<u4")
                require(np.array_equal(words, np.arange(len(words), dtype="<u4")), "RTT producer sequence differs")
                report["rtt_performance"] = rate
                halt(mem)
            else:
                report["combo"] = combo(native, mem, args.out, args.seconds, args.combo_hz, profile, args.clock, base)
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
                    mem.write(base - 4, original)
                    require(mem.read(base - 4, SIZE + 8) == original, "SRAM restoration differs")
                if original_code is not None:
                    mem.write(code_base, original_code)
                    require(mem.read(code_base, len(original_code)) == original_code, "producer SRAM restoration differs")
                if original is not None and mem.word(CCR) & (1 << 17):
                    mem.write_word(0xe000ef50, 0)
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
