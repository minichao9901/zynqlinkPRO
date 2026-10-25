"""Measure DAP_TransferBlock (0x06) throughput, i.e. what OpenOCD master uses.

OpenOCD v0.12 never sends 0x06, so it only exercises the firmware's slow
per-register DAP_Transfer path.  This tool measures the RTL batch engine path
that a newer OpenOCD would use.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import libusb_package
import usb.core
import usb.util

PKT = 1024
SWD_ACTIVATION = [0x9E, 0xE7] + [0xFF] * 8 + [0x00]


def le(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x20000000)
    ap.add_argument("--words", type=int, default=255)
    ap.add_argument("--loops", type=int, default=20)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    dev = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                        backend=libusb_package.get_libusb1_backend())
    if dev is None:
        raise SystemExit("CMSIS-DAP device not found")
    intf = dev.get_active_configuration()[(0, 0)]
    usb.util.claim_interface(dev, 0)
    ep_out = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
    ep_in = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)

    def xfer(payload):
        buf = bytes(payload)
        ep_out.write(buf, timeout=2000)
        if len(buf) % 512 == 0:
            ep_out.write(b"", timeout=2000)
        return bytes(ep_in.read(PKT, timeout=2000))

    xfer([0x02, 0x01])                       # connect SWD
    xfer([0x11] + le(10_000_000))            # SWJ clock
    xfer([0x13, 0x00])                       # SWD configure
    xfer([0x12, 88] + SWD_ACTIVATION)        # line reset
    xfer([0x04, 0x00, 0xE8, 0x03, 0x00, 0x00])
    xfer([0x05, 0x00, 0x01, 0x01] + le(0x23000052))  # CSW: 32-bit auto-increment
    xfer([0x05, 0x00, 0x01, 0x05] + le(args.addr))   # TAR

    first = xfer([0x06, 0x00, (args.words >> 0) & 0xFF, (args.words >> 8) & 0xFF, 0x0F])
    preview = [int.from_bytes(first[4 + i * 4:8 + i * 4], "little") for i in range(4)]
    xfer([0x05, 0x00, 0x01, 0x05] + le(args.addr))   # reset TAR after the preview block

    # TAR auto-increments, so keep the whole run inside the 20 KiB SRAM
    loops = args.loops
    t0 = time.perf_counter()
    total = 0
    for _ in range(loops):
        r = xfer([0x06, 0x00, (args.words >> 0) & 0xFF, (args.words >> 8) & 0xFF, 0x0F])
        total += args.words * 4
    elapsed = time.perf_counter() - t0

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "addr": hex(args.addr),
        "words_per_block": args.words,
        "blocks": loops,
        "bytes": total,
        "elapsed_seconds": elapsed,
        "MB_per_second": total / elapsed / 1e6,
        "MiB_per_second": total / elapsed / 1048576,
        "first_words": [f"{w:08x}" for w in preview],
    }
    print(json.dumps(result, indent=2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
