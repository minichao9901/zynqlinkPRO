"""Print each CMSIS-DAP handshake step so a failing SWD bring-up is visible."""
import libusb_package
import usb.core
import usb.util

PKT = 1024
SWD_ACTIVATION = [0x9E, 0xE7] + [0xFF] * 8 + [0x00]


def le(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


dev = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                    backend=libusb_package.get_libusb1_backend())
intf = dev.get_active_configuration()[(0, 0)]
usb.util.claim_interface(dev, 0)
ep_out = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
ep_in = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)


def xfer(payload):
    buf = bytes(payload)
    ep_out.write(buf, timeout=2000)
    if len(buf) % 512 == 0:
        ep_out.write(b"", timeout=2000)
    return bytes(ep_in.read(PKT, timeout=2000))


def show(name, r):
    print(f"{name:24s} -> {r[:16].hex(' ')}  ({len(r)} bytes)")


show("Connect", xfer([0x02, 0x01]))
show("SWJ_Clock 10M", xfer([0x11] + le(10_000_000)))
show("SWD_Configure", xfer([0x13, 0x00]))
show("SWJ_Sequence 88", xfer([0x12, 88] + SWD_ACTIVATION))
show("TransferConfigure", xfer([0x04, 0x00, 0xE8, 0x03, 0x00, 0x00]))
show("read IDCODE", xfer([0x05, 0x00, 0x01, 0x02]))
show("write CSW", xfer([0x05, 0x00, 0x01, 0x01] + le(0x23000052)))
show("write TAR", xfer([0x05, 0x00, 0x01, 0x05] + le(0x20000000)))
show("block read 4", xfer([0x06, 0x00, 0x04, 0x00, 0x0F]))
usb.util.release_interface(dev, 0)
