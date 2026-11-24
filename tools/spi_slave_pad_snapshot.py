"""Capture raw J7 SPI input samples from a --spi-pad-diagnostic build."""
import argparse
from collections import Counter
import json
from itertools import groupby
from pathlib import Path
import struct
import time

import serial
from serial.tools.list_ports import comports

from h743_spi_accept import Fixture, H743_USB, release, require, spi_config
from probe_flash import Session
from selectio_native import native_connection
from zynq_memory import PhysicalMemory

AUX_MARKER = 0x80020038
SAMPLE_RAM = 0x80024000
MOSI_TAP = 0x8000000C
SCK_NSS_TAP = 0x80010018
SNAPSHOT_WORDS = 1024
BURST_BYTES = 4096


def run_lengths(samples):
    return [Counter(len(list(group)) for sample, group in groupby(samples) if sample == level)
            for level in (0, 1)]


def summarize(words):
    # AXI words are little-endian. Within each nibble bit 0 is earliest.
    lanes = {name: [(word >> (offset + bit)) & 1 for word in words for bit in range(4)]
             for name, offset in (("mosi", 0), ("sck", 4), ("nss", 8))}
    transitions = lambda values: sum(a != b for a, b in zip(values, values[1:]))
    return {"total_slots": len(lanes["sck"]),
            "transitions": {line: transitions(values) for line, values in lanes.items()},
            "nss_high_slots": sum(lanes["nss"]),
            "sck_low_high_run_lengths": run_lengths(lanes["sck"]),
            "nss_low_high_run_lengths": run_lengths(lanes["nss"])}


def read_words(phy, output):
    phy.run(f'physrd -force -bin -file {{{output.as_posix()}}} {SAMPLE_RAM:#x} {SNAPSHOT_WORDS}')
    data = output.read_bytes()
    require(len(data) == SNAPSHOT_WORDS * 4, "incomplete raw pad capture")
    return struct.unpack(f"<{SNAPSHOT_WORDS}I", data)


def restore_tap(phy, address, tap):
    phy.run(f"physwr -force {address:#x} {tap}")
    require(phy.read_words(address) == [tap], f"delay tap readback differs at {address:#x}")


def capture(args, phy, report):
    ports = [p.device for p in comports() if (p.vid, p.pid, p.serial_number) == H743_USB]
    require(len(ports) == 1, f"expected the H743 SPI fixture, found {ports}")
    with serial.Serial(ports[0], 115200, timeout=0.05, write_timeout=2) as port:
        target = Fixture(port)
        fixture_info = target.identify()
        independent = "revision=4" in fixture_info
        require(independent or "revision=3" in fixture_info, "expected the revision 3 or 4 H743 SPI fixture")
        require(independent or (args.edge is None and args.fill is None), "EDGE/FILL requires revision 4")
        original_drive = int(fixture_info.split("drive=")[1])
        target.state("SPI STOP")
        original_edge = target.command("SPI EDGE").split("=")[1] if independent else None
        original_fill = target.command("SPI FILL").split("=")[1] if independent else None
        try:
            if args.edge:
                edge = ",".join(map(str, args.edge))
                require(target.command("SPI EDGE " + edge.replace(",", " ")) == f"SPI edge={edge}", "edge setup failed")
            else:
                require(target.command(f"SPI DRIVE {args.drive}") == f"SPI drive={args.drive}", "drive setup failed")
            if args.fill is not None:
                require(target.command(f"SPI FILL {args.fill}") == f"SPI fill={args.fill}", "fill setup failed")
            with native_connection(args.serial) as probe:
                info = probe.info()
                require(info["dedicated_pipes"], "expected the ABI 2 J7 SPI path")
                sck = target.kernel // args.divider
                report.update(reference_hz_before_arm=info["reference_hz"], source_hz=sck)
                probe.exchange(4, 0, spi_config(3, args.mode, sck, tap=args.mosi_tap))
                try:
                    target.state(f"SPI MASTER TX {args.mode} {args.divider} {BURST_BYTES} 1 2000 0x6731 0")
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        status = target.state()
                        if status["state"] != "active":
                            break
                        time.sleep(0.002)
                    report["target"] = status
                    require(status["state"] == "done" and status["sck_hz"] == sck and
                            status["tx_dma"] == BURST_BYTES, "source burst incomplete")
                    probe.exchange(4, 3)
                    count = 0
                    while data := probe.exchange(4, 1):
                        count += len(data)
                    counters = struct.unpack("<5I", probe.exchange(4, 4))
                    report["decoded"] = dict(bytes=count, pending=counters[0], dropped=counters[1], errors=counters[2])
                finally:
                    release(target, probe)
        finally:
            if independent:
                require(target.command("SPI EDGE " + original_edge.replace(",", " ")) ==
                        f"SPI edge={original_edge}", "edge restoration failed")
                fill = "PATTERN" if original_fill == "-1" else original_fill
                require(target.command(f"SPI FILL {fill}") == f"SPI fill={original_fill}", "fill restoration failed")
            else:
                require(target.command(f"SPI DRIVE {original_drive}") == f"SPI drive={original_drive}", "drive restoration failed")
    require(phy.read_words(AUX_MARKER) == [0x53504401], "diagnostic snapshot did not complete")
    report["sample_summary"] = summarize(read_words(phy, args.out / "samples.bin"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--serial", default="12345678")
    parser.add_argument("--cable-serial", required=True)
    parser.add_argument("--sdk", default=Path("E:/Xilinx/SDK/2018.3"), type=Path)
    parser.add_argument("--mode", type=int, choices=range(4), default=0)
    parser.add_argument("--drive", type=int, choices=range(4), default=3)
    parser.add_argument("--edge", type=int, choices=range(4), nargs=3, metavar=("SCK", "DATA", "NSS"))
    parser.add_argument("--fill", type=lambda value: int(value, 0), choices=range(256), metavar="BYTE")
    parser.add_argument("--divider", type=int, choices=(2, 4, 8, 16, 32, 64, 128, 256), default=2)
    parser.add_argument("--mosi-tap", type=int, choices=range(32), default=0)
    parser.add_argument("--sck-nss-tap", type=int, choices=range(32))
    args = parser.parse_args()
    args.out = args.out.resolve()
    require("}" not in args.out.as_posix() and "{" not in args.out.as_posix(), "ambiguous Tcl path")
    args.out.mkdir(parents=True, exist_ok=False)
    session = Session(args.out, args.sdk, "tcp:127.0.0.1:3121", cable_serial=args.cable_serial)
    phy = PhysicalMemory(session, cable_serial=args.cable_serial)
    require(phy.read_words(AUX_MARKER)[0] & ~1 == 0x53504400, "J7 diagnostic bitstream is absent")
    saved_mosi = phy.read_words(MOSI_TAP)[0]
    saved_clock = phy.read_words(SCK_NSS_TAP)[0]
    report = dict(mode=args.mode, drive=args.drive, edge=args.edge, fill=args.fill, mosi_tap=args.mosi_tap,
                  sck_nss_tap=saved_clock if args.sck_nss_tap is None else args.sck_nss_tap)
    try:
        if args.sck_nss_tap is not None:
            restore_tap(phy, SCK_NSS_TAP, args.sck_nss_tap)
        capture(args, phy, report)
    finally:
        try:
            restore_tap(phy, MOSI_TAP, saved_mosi)
            if args.sck_nss_tap is not None:
                restore_tap(phy, SCK_NSS_TAP, saved_clock)
            report["delay_restored"] = True
        finally:
            (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
