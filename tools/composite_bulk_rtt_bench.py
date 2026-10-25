"""DAP_Transfer-like request/response benchmark for the composite bench.

OpenOCD sends one DAP_Transfer command per USB transfer and then reads the
response, so a real memory read costs one OUT + one IN per packet.  This tool
replays that pattern with the command/response sizes OpenOCD computes from the
probe-reported packet size:
    N = (packet_size - 4) / 5          # queued register transfers
    command  = 3 + N                   # 0x05, DAP index, count, N x register
    response = 3 + 4 * N               # 0x05, count, status, N x 32-bit data
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import libusb_package
import usb.core
import usb.util


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-size", type=int, default=512)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    n = (args.packet_size - 4) // 5
    cmd = bytes([0x05, 0x00, n & 0xFF]) + bytes([0x00]) * n
    resp = 3 + 4 * n

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

    payload = 0
    cycles = 0
    t0 = time.perf_counter()
    try:
        deadline = t0 + args.seconds
        while time.perf_counter() < deadline:
            ep_out.write(cmd, timeout=2000)
            payload += len(ep_in.read(resp, timeout=2000))
            cycles += 1
    finally:
        try:
            usb.util.release_interface(dev, 0)
        except Exception:
            pass
    elapsed = time.perf_counter() - t0
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "packet_size": args.packet_size,
        "transfers_per_packet": n,
        "command_bytes": len(cmd),
        "response_bytes": resp,
        "payload_bytes": payload,
        "elapsed_seconds": elapsed,
        "cycles": cycles,
        "cycles_per_second": cycles / elapsed,
        "payload_MB_per_second": payload / elapsed / 1e6,
        "payload_MiB_per_second": payload / elapsed / 1048576,
    }
    print(json.dumps(result, indent=2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
