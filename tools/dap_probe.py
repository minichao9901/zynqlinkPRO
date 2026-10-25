"""Minimal CMSIS-DAP v2 probe: send one command, print the raw response."""
import argparse
import sys
import time

import libusb_package
import usb.core
import usb.util


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", default="00 01", help="hex bytes to send")
    ap.add_argument("--read", type=int, default=512)
    ap.add_argument("--timeout", type=int, default=1000)
    args = ap.parse_args()
    payload = bytes.fromhex(args.cmd)

    dev = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                        backend=libusb_package.get_libusb1_backend())
    if dev is None:
        sys.exit("device 0D28:0204 not found")
    intf = dev.get_active_configuration()[(0, 0)]
    usb.util.claim_interface(dev, 0)
    ep_out = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
    ep_in = usb.util.find_descriptor(
        intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
    print(f"ep_out=0x{ep_out.bEndpointAddress:02X} ep_in=0x{ep_in.bEndpointAddress:02X}")

    t0 = time.perf_counter()
    n = ep_out.write(payload, timeout=args.timeout)
    print(f"OUT {n} bytes in {(time.perf_counter()-t0)*1e3:.2f} ms")
    try:
        data = bytes(ep_in.read(args.read, timeout=args.timeout))
        print(f"IN {len(data)} bytes in {(time.perf_counter()-t0)*1e3:.2f} ms: {data[:32].hex(' ')}")
    except usb.core.USBTimeoutError:
        print(f"IN timeout after {args.timeout} ms (no response)")
        return 2
    finally:
        try:
            usb.util.release_interface(dev, 0)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
