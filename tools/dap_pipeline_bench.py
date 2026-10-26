"""Measure CMSIS-DAP block throughput: sequential vs pipelined requests.

Pipelining means queueing several 0x06 requests before draining the IN
responses, so the device executes the next block while the previous
response is still being transferred.
"""
import argparse
import json
import struct
import time

import libusb_package
import usb.core
import usb.util

PKT = 4096


def le(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def open_dap():
    dev = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                        backend=libusb_package.get_libusb1_backend())
    if dev is None:
        raise RuntimeError("DAP not found")
    intf = dev.get_active_configuration()[(0, 0)]
    usb.util.claim_interface(dev, 0)
    out = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(
            e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
    inp = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(
            e.bEndpointAddress) == usb.util.ENDPOINT_IN)
    return dev, out, inp


def drain(inp):
    n = 0
    while True:
        try:
            inp.read(PKT, timeout=80)
            n += 1
        except usb.core.USBTimeoutError:
            return n


def send(out, payload):
    b = bytes(payload)
    out.write(b, timeout=3000)
    if len(b) % 512 == 0:
        out.write(b"", timeout=3000)


def xfer(out, inp, payload):
    send(out, payload)
    return bytes(inp.read(PKT, timeout=5000))


def cmd(out, inp, payload):
    r = xfer(out, inp, payload)
    if not r or r[0] != payload[0]:
        raise RuntimeError("cmd 0x%02x -> %s" % (payload[0], r[:16].hex(" ")))
    return r


def setup(out, inp, speed_khz):
    drain(inp)
    cmd(out, inp, [0x02, 0x01])
    cmd(out, inp, [0x11] + le(speed_khz * 1000))
    cmd(out, inp, [0x13, 0x00])
    cmd(out, inp, [0x12, 152] + [0xFF] * 8 + [0x9E, 0xE7] + [0xFF] * 8 + [0x00])
    cmd(out, inp, [0x04, 0x00, 0x40, 0x00, 0x00, 0x00])
    r = cmd(out, inp, [0x05, 0x00, 0x01, 0x02])
    if len(r) < 7 or r[2] != 0x01:
        raise RuntimeError("IDCODE read failed: %s" % r.hex(" "))
    cmd(out, inp, [0x05, 0x00, 0x01, 0x04] + le(0x50000000))
    cmd(out, inp, [0x05, 0x00, 0x01, 0x08] + le(0x00000000))
    cmd(out, inp, [0x05, 0x00, 0x01, 0x01] + le(0x23000052))
    cmd(out, inp, [0x05, 0x00, 0x01, 0x05] + le(0x20000000))
    return r


def read_exact(inp, n):
    buf = b''
    while len(buf) < n:
        chunk = bytes(inp.read(PKT, timeout=5000))
        if not chunk:
            break
        buf += chunk
    return buf


def block_read_req(words):
    # CMSIS-DAP TransferBlock: command, DAP index, count(2), request.
    return [0x06, 0x00, words & 0xFF, (words >> 8) & 0xFF, 0x0F]


def bench_sequential(out, inp, words, loops):
    t0 = time.perf_counter()
    for _ in range(loops):
        send(out, block_read_req(words))
        r = read_exact(inp, 4 + words * 4)
        if len(r) < 4 + words * 4:
            raise RuntimeError("short read %d" % len(r))
    dt = time.perf_counter() - t0
    return dt, loops * words * 4


def bench_pipelined(out, inp, words, loops, depth):
    total = 0
    t0 = time.perf_counter()
    done = 0
    while done < loops:
        n = min(depth, loops - done)
        for _ in range(n):
            send(out, block_read_req(words))
        for _ in range(n):
            r = read_exact(inp, 4 + words * 4)
            if len(r) < 4 + words * 4:
                raise RuntimeError("short read %d" % len(r))
        done += n
    dt = time.perf_counter() - t0
    return dt, loops * words * 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=int, default=60000)
    ap.add_argument("--words", type=int, default=770)
    ap.add_argument("--loops", type=int, default=50)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    dev, out, inp = open_dap()
    try:
        setup(out, inp, args.speed)
        xfer(out, inp, block_read_req(args.words))  # warm up
        rows = []
        for name, fn in (("sequential", lambda: bench_sequential(out, inp, args.words, args.loops)),
                         ("pipelined", lambda: bench_pipelined(out, inp, args.words, args.loops, args.depth))):
            fn()  # warm up each mode
            dt, nbytes = fn()
            rate = nbytes / dt / 1e6
            rows.append({"mode": name, "seconds": dt, "bytes": nbytes,
                         "MB_s": round(rate, 3)})
            print("%-10s %8.1f ms  %8.3f MB/s" % (name, dt * 1e3, rate))
        out_doc = {"speed_khz": args.speed, "words": args.words,
                   "loops": args.loops, "depth": args.depth, "rows": rows}
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out_doc, f, indent=2)
    finally:
        usb.util.release_interface(dev, 0)


if __name__ == "__main__":
    main()

