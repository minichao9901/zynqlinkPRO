"""Pipelined CMSIS-DAP v2 bulk benchmark (matches OpenOCD's N-in-flight pattern).

OpenOCD's cmsis-dap driver submits up to MIN(DAP_PacketCount, 4) DAP commands
before reaping responses, so a single synchronous transfer is not representative.
This tool keeps --depth bulk transfers in flight using one thread per transfer.
"""
import argparse
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import libusb_package
import usb.core
import usb.util


def open_device():
    dev = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                        backend=libusb_package.get_libusb1_backend())
    if dev is None:
        raise SystemExit("CMSIS-DAP device not found")
    cfg = dev.get_active_configuration()
    intf = cfg[(0, 0)]
    usb.util.claim_interface(dev, 0)
    ep_out = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
    ep_in = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
    return dev, ep_out, ep_in


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--direction", choices=["in", "out"], required=True)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--chunk", type=int, default=512)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    dev, ep_out, ep_in = open_device()
    ep = ep_in if args.direction == "in" else ep_out
    payload = (bytes(range(256)) * ((args.chunk + 255) // 256))[:args.chunk]

    deadline = time.perf_counter() + args.seconds
    start = threading.Barrier(args.depth + 1)
    totals = [0] * args.depth
    calls = [0] * args.depth
    errors = [0] * args.depth

    def worker(idx):
        total = 0
        n = 0
        err = 0
        start.wait()
        while time.perf_counter() < deadline:
            try:
                if args.direction == "out":
                    total += ep.write(payload, timeout=2000)
                else:
                    total += len(ep.read(args.chunk, timeout=2000))
                n += 1
            except Exception:
                err += 1
                break
        totals[idx] = total
        calls[idx] = n
        errors[idx] = err

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(args.depth)]
    for t in threads:
        t.start()
    t0 = time.perf_counter()
    start.wait()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    try:
        usb.util.release_interface(dev, 0)
    except Exception:
        pass

    total = sum(totals)
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "direction": args.direction,
        "chunk": args.chunk,
        "depth": args.depth,
        "bytes": total,
        "elapsed_seconds": elapsed,
        "MB_per_second": total / elapsed / 1e6,
        "MiB_per_second": total / elapsed / 1048576,
        "calls": sum(calls),
        "calls_per_second": sum(calls) / elapsed,
        "errors": sum(errors),
        "endpoints": {"out": hex(ep_out.bEndpointAddress), "in": hex(ep_in.bEndpointAddress)},
    }
    print(json.dumps(result, indent=2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
