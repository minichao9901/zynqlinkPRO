"""Compare an external SPI master's payload with the existing USB CDC stream."""
import argparse
from contextlib import contextmanager, nullcontext
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

import serial
from serial.tools.list_ports import comports

from selectio_native import native_connection
from selectio_f103_fixture import BASE, ROOT, low_link
from selectio_running_test import core_read, core_write


@contextmanager
def f103_source(args, report):
    # The enclosing SRAM guard verifies the original target and recovery.
    fixture = args.out.with_suffix(".fixture")
    fixture.mkdir(exist_ok=False)
    elf, binary = fixture / "source.elf", fixture / "source.bin"
    subprocess.run(["arm-none-eabi-gcc", "-mcpu=cortex-m3", "-mthumb", "-nostdlib",
                    f"-Wl,-Ttext={BASE:#x},-e,spi_source", ROOT / "firmware/target/f103_spi_cdc_source.S",
                    "-o", elf], check=True)
    subprocess.run(["arm-none-eabi-objcopy", "-O", "binary", "-j", ".text", elf, binary], check=True)
    code = binary.read_bytes()
    if len(code) > 0x200:
        raise RuntimeError("SPI producer overlaps its state")
    config = BASE + 0x200
    size = 0x220
    dhcsr, dcrdr, demcr, dwt, count = 0xe000edf0, 0xe000edf8, 0xe000edfc, 0xe0001000, 0xe0001004
    registers = (*range(15), 20, 16, 15)
    expected = fixture / "expected.bin"
    expected.write_bytes(bytes((i ^ (i >> 3)) & 255 for i in range(args.f103_source)))
    with low_link(args.serial) as target:
        if not target.word(dhcsr) & (1 << 17) or target.word(0x40021004) != 0x51040a:
            raise RuntimeError("require the guarded and halted F103 CDC48 fixture")
        backup = target.read(BASE, size)
        original_trace = {addr: target.word(addr) for addr in (dcrdr, demcr, dwt, count)}
        regs = {r: core_read(target, r) for r in registers}
    (fixture / "restore.bin").write_bytes(backup)
    (fixture / "restore.json").write_text(json.dumps(dict(registers=regs, trace=original_trace)), encoding="utf-8")
    started = False
    report["target_restored"] = False
    try:
        with low_link(args.serial) as target:
            target.write(BASE, code)
            target.write(config, struct.pack("<8I", args.mode, args.f103_source, 0, 0, 0, 0, 0, 0))
            if target.read(BASE, len(code)) != code:
                raise RuntimeError("SPI producer SRAM verification failed")
            target.write_word(demcr, original_trace[demcr] | (1 << 24))
            target.write_word(dwt, original_trace[dwt] | 1)
            core_write(target, 16, 0x01000000)
            core_write(target, 20, 1)
            core_write(target, 15, BASE | 1)
            started = True
            target.write_word(dhcsr, 0xa05f0001)
        yield expected
    finally:
        # Allow the SRAM source to return the SWJ pins before using DAP again.
        deadline = time.monotonic() + 4
        restoring = False
        while True:
            try:
                with low_link(args.serial) as target:
                    result = struct.unpack("<8I", target.read(config, 32))
                    if started and result[2] != 0x53504944:
                        raise RuntimeError("SPI source has not released the bus")
                    restoring = True
                    io_restored = True
                    if started:
                        apb2, crh, odr, mapr = result[4:]
                        io_restored = target.word(0x40021018) == apb2
                        if apb2 & 4:
                            io_restored &= (target.word(0x40010804), target.word(0x4001080c)) == (crh, odr)
                        if apb2 & 1:
                            io_restored &= ((target.word(0x40010004) ^ mapr) & ~0x07000000) == 0
                    target.write_word(dhcsr, 0xa05f0003)
                    if not target.word(dhcsr) & (1 << 17):
                        raise RuntimeError("could not halt the SPI source")
                    target.write(BASE, backup)
                    for addr in (count, dwt, demcr):
                        target.write_word(addr, original_trace[addr])
                    for reg in registers:
                        core_write(target, reg, regs[reg])
                    core_restored = all(core_read(target, r) == regs[r] for r in registers)
                    target.write_word(dcrdr, original_trace[dcrdr])
                    report["target_restored"] = (io_restored and core_restored and
                                                 target.read(BASE, size) == backup and
                                                 all(target.word(addr) == original_trace[addr] for addr in (dcrdr, demcr, dwt)))
                    if not report["target_restored"]:
                        raise RuntimeError("SPI source restoration differs")
                    if started and result[3]:
                        report["source_average_sck_hz"] = args.f103_source * 8 * 48e6 / result[3]
                    break
            except Exception:
                if restoring or time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)


def cdc_status(native):
    names = ("bound", "claimed", "baud", "dtr", "pending_out",
             "overflow", "framing_errors", "rx_available")
    reply = native.exchange(0, 4)
    if len(reply) != 4 * len(names):
        raise RuntimeError("unexpected CDC status length")
    return {name: int.from_bytes(reply[4*i:4*i+4], "little") for i, name in enumerate(names)}


def wait_for_claim(native, expected, seconds=3):
    deadline = time.monotonic() + seconds
    while True:
        status = cdc_status(native)
        if status["claimed"] == expected:
            return status
        if time.monotonic() >= deadline:
            raise RuntimeError(f"CDC arm/release timed out: {status}")
        time.sleep(0.02)


def capture(port, expected, timeout):
    start = time.monotonic()
    first = None
    total = 0
    digest = hashlib.sha256()
    with expected.open("rb") as stream:
        while want := stream.read(65536):
            received = bytearray()
            while len(received) < len(want):
                data = port.read(min(len(want) - len(received), port.in_waiting or 1))
                if data and first is None:
                    first = time.monotonic()
                received.extend(data)
                if time.monotonic() > start + timeout:
                    raise RuntimeError(f"timed out after {total+len(received)} bytes")
            if received != want:
                offset = next(i for i, (a, b) in enumerate(zip(received,want)) if a != b)
                raise RuntimeError(f"byte {total+offset}: got {received[offset]:02x}, expected {want[offset]:02x}")
            total += len(received)
            digest.update(received)
    end = time.monotonic()
    return dict(bytes=total, sha256=digest.hexdigest(), receive_seconds=end-first,
                command_window_seconds=end-start)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="12345678")
    parser.add_argument("--mode", type=int, choices=range(4), required=True)
    parser.add_argument("--tap", type=int, choices=range(32), default=0)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--expected", type=Path, help="exact external MOSI payload in wire order")
    source.add_argument("--f103-source", type=int, metavar="BYTES", help="guarded CDC48 SRAM GPIO source")
    parser.add_argument("--seconds", type=float, default=65, help="deadline including the source's start delay")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if not args.execute:
        print("Open the probe COM and compare an independent source's SPI payload, then release the bus.")
        return
    if args.f103_source is not None and not 1 <= args.f103_source <= 262144:
        parser.error("--f103-source must be in 1..262144 bytes")
    if args.expected is not None and (not args.expected.is_file() or not args.expected.stat().st_size):
        parser.error("--expected must be a nonempty binary file")
    matches = [p.device for p in comports() if p.serial_number == args.serial]
    if len(matches) != 1:
        raise RuntimeError(f"expected a unique probe COM for {args.serial}: {matches}")
    report = dict(serial=args.serial, com=matches[0], mode=args.mode, tap=args.tap, passed=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as evidence:
        try:
            with native_connection(args.serial) as native:
                native.info()
                if cdc_status(native)["bound"]:
                    raise RuntimeError("the probe COM already has a binding")
                fixture = f103_source(args, report) if args.f103_source else nullcontext(args.expected)
                with serial.Serial(matches[0], baudrate=115200, timeout=0.05) as port, fixture as expected:
                    source_started = time.monotonic()
                    native.exchange(0, 3, bytes((3, args.mode, args.tap)))
                    try:
                        report["armed"] = wait_for_claim(native, 1)
                        print(f"ARMED {matches[0]} mode={args.mode}. Send the expected SPI payload now.", flush=True)
                        report.update(capture(port, expected, args.seconds))
                        if port.read(1):
                            raise RuntimeError("extra CDC data after expected payload")
                        status = cdc_status(native)
                        report["final"] = status
                        if status["overflow"] or status["framing_errors"] or status["rx_available"]:
                            raise RuntimeError(f"SPI receive did not finish cleanly: {status}")
                    except Exception:
                        if args.f103_source:
                            # Keep the probe pads released while the timed source finishes.
                            remaining = 2.2 + args.f103_source * 512 / 48e6 - (time.monotonic() - source_started)
                            if remaining > 0:
                                time.sleep(remaining)
                        raise
                    finally:
                        native.exchange(0, 3, b"\0")
                        report["released"] = wait_for_claim(native, 0)
            report["passed"] = True
        except Exception as error:
            report["error"] = str(error)
            raise
        finally:
            json.dump(report, evidence, indent=2)
            evidence.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
