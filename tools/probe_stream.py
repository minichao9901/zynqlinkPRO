"""Control probe RTT/CDC and RTL HSS using the superlink HID envelopes.

Examples:
  python tools/probe_stream.py info
  python tools/probe_stream.py rtt --address 0x20000000 --size 65536 --port COM33 --seconds 3
  python tools/probe_stream.py hss --var 0x20000020:4:4 --period 100 --seconds 3 --output capture.hss
Requires hidapi; capture additionally uses pyserial or pyusb + libusb-package.
"""
import argparse
import json
from pathlib import Path
import struct
import time

import hid


class Probe:
    def __init__(self, serial=None):
        matches = [d for d in hid.enumerate(0x0D28, 0x0204)
                   if d['usage_page'] == 0xFF00 and (not serial or d['serial_number'] == serial)]
        if len(matches) != 1:
            raise RuntimeError(f'Expected one probe HID, found {len(matches)}; use --serial')
        self.device = hid.device()
        self.device.open_path(matches[0]['path'])

    def close(self):
        self.device.close()

    def request(self, command, data=b''):
        packet = bytes([1, 1+len(data), command])+data
        if len(packet) > 64:
            raise ValueError('HID request exceeds 64 bytes')
        self.device.write(packet.ljust(64, b'\0'))
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            reply = bytes(self.device.read(64, 200))
            if len(reply) == 64 and reply[0] == 2 and reply[2] == command:
                return reply
        raise TimeoutError(f'HID command {command:#x} timed out')

    def action(self, command, action, data=b''):
        reply = self.request(command, bytes([action])+data)
        return struct.unpack_from('b', reply, 3)[0], struct.unpack_from('<12I', reply, 4)


def variable(value):
    fields = [int(s, 0) for s in value.split(':')]
    if len(fields) != 3 or fields[1] not in (1, 2, 4, 8) or not 0 <= fields[2] <= 7:
        raise argparse.ArgumentTypeError('Use address:size:type, size=1/2/4/8, type=0..7')
    return fields


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--serial', help='USB serial when multiple probes are attached')
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('info')
    status = sub.add_parser('status')
    status.add_argument('--service', choices=['rtt', 'hss'], default='hss')
    stop = sub.add_parser('stop')
    stop.add_argument('--service', choices=['rtt', 'hss'], default='hss')
    for name in ['rtt', 'hss']:
        p = sub.add_parser(name)
        p.add_argument('--clock', type=int, default=50_000_000)
        p.add_argument('--seconds', type=float, default=3)
        p.add_argument('--output', type=Path)
        if name == 'rtt':
            p.add_argument('--address', type=lambda s: int(s, 0), default=0x20000000)
            p.add_argument('--size', type=lambda s: int(s, 0), default=65536)
            p.add_argument('--channel', type=int, default=0)
            p.add_argument('--port', required=True)
        else:
            p.add_argument('--var', type=variable, action='append', required=True)
            p.add_argument('--period', type=int, default=100)
            p.add_argument('--ticks', action='store_true', help='Period in 24 MHz ticks; emit HSS v2')
    args = ap.parse_args()
    probe = Probe(args.serial)
    try:
        if args.command == 'info':
            for cmd in [0x10, 0x11, 0x13]:
                r = probe.request(cmd)
                print(r[3:2+r[1]].decode(errors='replace'))
            return
        command = 0x31 if getattr(args, 'service', args.command) == 'rtt' else 0x32
        if args.command in ('stop', 'status'):
            rc, words = probe.action(command, 0 if args.command == 'stop' else 2)
            print(json.dumps({'rc': rc, 'words': words}))
            return
        if not 1_000_000 <= args.clock <= 60_000_000:
            ap.error('--clock must be between 1000000 and 60000000')
        sink = args.output.open('wb') if args.output else None
        count = 0
        started = False
        resource = None
        try:
            if args.command == 'rtt':
                import serial
                resource = serial.Serial(args.port, baudrate=115200, timeout=0.1)
                rc, _ = probe.action(0x31, 7, struct.pack('<IHBB', args.clock, 1024, 0, 1))
                if rc:
                    raise RuntimeError(f'RTT CONFIG failed: {rc}')
                rc, _ = probe.action(0x31, 1, struct.pack('<IIB', args.address, args.size, args.channel))
            else:
                import libusb_package
                import usb.core
                import usb.util
                if len(args.var) > 8:
                    ap.error('At most 8 variables are supported')
                rc, _ = probe.action(0x32, 3, struct.pack('<I', args.clock))
                if rc:
                    raise RuntimeError(f'HSS CLOCK failed: {rc}')
                config = struct.pack('<IBB', args.period, 0, len(args.var))
                config += b''.join(struct.pack('<IBB', *v) for v in args.var)
                rc, _ = probe.action(0x32, 10 if args.ticks else 7, config)
                if rc:
                    raise RuntimeError(f'HSS CONFIG failed: {rc}')
                resource = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                                         serial_number=args.serial if args.serial else None,
                                         backend=libusb_package.get_libusb1_backend()) if args.serial else usb.core.find(
                                             idVendor=0x0D28, idProduct=0x0204,
                                             backend=libusb_package.get_libusb1_backend())
                usb.util.claim_interface(resource, 0)
                # Drain the previous stopped session before resetting sequence numbers.
                while True:
                    try:
                        resource.read(0x87,512,timeout=20)
                    except usb.core.USBTimeoutError:
                        break
                rc, _ = probe.action(0x32, 1)
            if rc:
                raise RuntimeError(f'{args.command.upper()} START failed: {rc}')
            started = True
            deadline = time.monotonic()+args.seconds
            while time.monotonic() < deadline:
                try:
                    data = (resource.read(65536) if args.command == 'rtt'
                            else bytes(resource.read(0x87, 512, timeout=200)))
                except Exception as exc:
                    if args.command == 'hss' and isinstance(exc, usb.core.USBTimeoutError):
                        rc, _ = probe.action(0x32, 2)
                        if rc:
                            raise RuntimeError(f'HSS sampling failed: {rc}') from exc
                        continue
                    raise
                if args.command == 'hss' and (len(data) != 512 or data[:2] != b'SJ'):
                    raise RuntimeError('Invalid HSS packet')
                count += len(data)
                if sink:
                    sink.write(data)
            print(json.dumps({'bytes': count, 'seconds': args.seconds,
                              'status': probe.action(command, 2)}))
        finally:
            if started:
                rc, _ = probe.action(command, 0)
                # STOP is graceful: drain queued HSS records while it finishes.
                deadline = time.monotonic()+3
                while rc == -7 and args.command == 'hss' and time.monotonic() < deadline:
                    try:
                        data = bytes(resource.read(0x87, 512, timeout=100))
                        if sink:
                            sink.write(data)
                    except usb.core.USBTimeoutError:
                        pass
                    rc, _ = probe.action(command, 0)
                if rc:
                    print(json.dumps({'stop_rc': rc}))
                elif args.command == 'hss':
                    while True:
                        try:
                            data=bytes(resource.read(0x87,512,timeout=100))
                            if sink:
                                sink.write(data)
                        except usb.core.USBTimeoutError:
                            break
            if resource is not None:
                if args.command == 'rtt':
                    resource.close()
                else:
                    usb.util.release_interface(resource, 0)
                    usb.util.dispose_resources(resource)
            if sink:
                sink.close()
    finally:
        probe.close()


if __name__ == '__main__':
    main()
