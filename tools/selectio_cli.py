"""Native USB CLI for the integrated J7 SelectIO firmware."""
import argparse
from contextlib import contextmanager
import json
import hashlib
from pathlib import Path
import struct
import time

import usb.util
from dap_pipeline_bench import cmd, open_dap, setup
from selectio_native import native_connection


PAGE = 0x20008000
PORTS = {"swd": 1, "jtag": 2}


def number(text):
    return int(text, 0)


@contextmanager
def connection(serial):
    device, out_ep, in_ep = open_dap(serial)
    try:
        yield out_ep, in_ep
    finally:
        usb.util.dispose_resources(device)


def capabilities(out_ep, in_ep):
    reply = cmd(out_ep, in_ep, [0x8f, 0])
    if len(reply) != 18 or reply[1] or reply[2:6] != b"SIO1":
        raise RuntimeError("The probe did not report the SIO1 firmware interface")
    ref, start, size = struct.unpack_from("<III", reply, 6)
    return dict(protocol="SIO1", reference_hz=ref, link_hz=ref / 2,
                sram_start=start, sram_bytes=size)


def transfer(out_ep, in_ep, transport, address, length, data, tap, slot, idle, native=None):
    op = PORTS[transport] | (0x80 if data is not None else 0)
    header = struct.pack("<BBHIBBBB", 0x8e, op, length // 4, address, tap, slot, idle, 0)
    request = header + (data if data is not None else b"")
    reply = native.exchange(1,0,request) if native is not None else cmd(out_ep,in_ep,request)
    if len(reply) < 6 or reply[1]:
        raise RuntimeError(f"{transport} transaction failed at {address:#010x}: {reply[:6].hex()}")
    expected = 6 + (length if data is None else 0)
    if len(reply) != expected:
        raise RuntimeError(f"Expected {expected} USB bytes, received {len(reply)}")
    return reply[6:]


def capture_combo(args):
    import csv
    if not 1<=len(args.var)<=8 or args.seconds<=0 or args.ticks<=0:
        raise ValueError("choose 1..8 word addresses, a positive period and a positive window")
    if args.rtt_out.exists() or args.scope_out.exists() or args.rtt_out.resolve()==args.scope_out.resolve():
        raise ValueError("provide two distinct new output paths")
    config=struct.pack("<4BIIBB2x",PORTS[args.transport],args.tap,args.slot,args.idle,
                       args.rtt_address,args.ticks,len(args.var),args.channel)
    config+=struct.pack("<"+"I"*len(args.var),*args.var)
    layout=struct.Struct("<"+"I"*(1+len(args.var)))
    received=samples=0
    with connection(args.serial) as (tx,rx), native_connection(args.serial,tx.device) as native, \
         args.rtt_out.open("xb") as rtt,args.scope_out.open("x",newline="",encoding="utf8") as wave:
        info=native.info()
        setup(tx,rx,1000,args.transport)
        writer=csv.writer(wave); writer.writerow(["tick_24mhz",*(f"u32_{a:08x}" for a in args.var)])
        active=False
        def pull():
            nonlocal received,samples
            payload=native.exchange(6,1);rtt.write(payload);received+=len(payload)
            values=native.exchange(6,2)
            if len(values)%layout.size: raise RuntimeError("partial sample group")
            writer.writerows(layout.iter_unpack(values));samples+=len(values)//layout.size
            return len(payload)+len(values)
        try:
            native.exchange(6,0,config);active=True;start=time.perf_counter()
            next_check=start+0.25
            while time.perf_counter()-start<args.seconds:
                pull()
                if time.perf_counter()>=next_check:
                    state=struct.unpack("<8I",native.exchange(6,4))
                    if state[1]:break
                    next_check=time.perf_counter()+0.25
        finally:
            try:
                if active:
                    native.exchange(6,3)
                    while pull(): pass
                    state=struct.unpack("<8I",native.exchange(6,4))
                    detail=struct.unpack("<8I",native.exchange(6,6)) if state[1] else ()
                    native.exchange(6,5)
                    if state[1] or not (state[3]==state[4]==received and state[5]==state[6]==samples):
                        raise RuntimeError(f"probe/host tail mismatch: {state}, {received} RTT bytes, {samples} groups, diagnostic={detail}")
                    info.update(rtt_bytes=received,sample_groups=samples,skipped_groups=state[7],
                                period_ticks=state[2],elapsed_seconds=time.perf_counter()-start)
            finally: cmd(tx,rx,[3])
    print(json.dumps(info,indent=2))
    return 0


def capture(args):
    from probe_stream import variable
    channel=2 if args.action=="rtt" else 3
    if args.seconds<=0: raise ValueError("positive window required")
    if channel==3 and not 1<=len(args.var)<=8: raise ValueError("scope requires 1..8 variables")
    if channel==3:
        variables=[variable(v) for v in args.var]
    if args.out.exists(): raise ValueError("capture output already exists")
    with native_connection(args.serial) as native, args.out.open("xb") as output:
        info=native.info()
        native.exchange(channel,0,b"\x01")
        active=False
        received=0
        def action(op,data=b""):
            rc,words=native.control(channel,op,data)
            if rc: raise RuntimeError(f"stream action {op} failed: {rc}")
            return words
        def drain():
            nonlocal received
            block=native.exchange(channel,1)
            output.write(block)
            received+=len(block)
            return len(block)
        try:
            action(12,bytes([PORTS[args.transport]]))
            if channel==2:
                action(7,struct.pack("<IHBB",args.clock,1024,0,1))
                cfg=struct.pack("<IIB",args.address,args.size,args.channel)
            else:
                action(3,struct.pack("<I",args.clock))
                cfg=struct.pack("<IBB",args.period,0,len(variables))
                cfg+=b"".join(struct.pack("<IBB",*v) for v in variables)
                action(10,cfg)
                cfg=b""
            action(1,cfg)
            active=True
            start=time.monotonic()
            while time.monotonic()-start<args.seconds: drain()
        finally:
            try:
                if active:
                    deadline=time.monotonic()+5
                    while True:
                        rc,_=native.control(channel,0)
                        if rc==0: break
                        if rc!=-7 or time.monotonic()>deadline: raise RuntimeError(f"stream STOP failed: {rc}")
                        drain()
                    while drain(): pass
                    info.update(bytes=received,status=list(action(2)),seconds=time.monotonic()-start)
            finally:
                native.exchange(channel,0,b"\x00")
    print(json.dumps(info,indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="12345678", help="J7 USB serial number")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("info", help="read firmware capabilities and PS reference clock")
    test = commands.add_parser("usb-test", help="verify WinUSB transport independently of the target")
    test.add_argument("--seconds", type=float, default=5)
    sub=commands.add_parser("combo",help="simultaneously drain RTT and sample 1..8 SRAM words on one link")
    sub.add_argument("--transport",choices=PORTS,required=True)
    sub.add_argument("--tap",type=int,choices=range(32),required=True,metavar="0..31")
    sub.add_argument("--slot",type=int,choices=range(64),required=True,metavar="0..63")
    sub.add_argument("--idle",type=int,required=True)
    sub.add_argument("--rtt-address",type=number,required=True)
    sub.add_argument("--channel",type=int,default=0)
    sub.add_argument("--ticks",type=number,required=True,help="requested sample period in 24 MHz ticks")
    sub.add_argument("--var",type=number,action="append",required=True,help="aligned u32 SRAM address")
    sub.add_argument("--seconds",type=float,required=True)
    sub.add_argument("--rtt-out",type=Path,required=True)
    sub.add_argument("--scope-out",type=Path,required=True)
    for action in ("rtt","scope"):
        sub=commands.add_parser(action,help="capture RTT bytes or HSS frames through native WinUSB")
        sub.add_argument("--transport",choices=PORTS,required=True)
        sub.add_argument("--clock",type=number,required=True,help="requested link rate, Hz")
        sub.add_argument("--seconds",type=float,required=True)
        sub.add_argument("--out",type=Path,required=True)
        if action=="rtt":
            sub.add_argument("--address",type=number,required=True,help="RTT control block or scan base")
            sub.add_argument("--size",type=number,default=256)
            sub.add_argument("--channel",type=int,default=0)
        else:
            sub.add_argument("--period",type=number,required=True,help="sample period in 24 MHz timer ticks")
            sub.add_argument("--var",action="append",required=True,help="address:size:type")
    for action in ("read", "write"):
        sub = commands.add_parser(action, help=f"{action} one block of aligned F103 SRAM")
        sub.add_argument("--transport", required=True, choices=PORTS)
        sub.add_argument("--address", type=number, default=PAGE)
        sub.add_argument("--tap", type=int, required=True, choices=range(32), metavar="0..31")
        sub.add_argument("--slot", type=int, required=True)
        sub.add_argument("--idle", type=int, required=True)
        if action == "read":
            sub.add_argument("--bytes", type=number, required=True)
            sub.add_argument("--out", type=Path, required=True)
        else:
            sub.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action=="combo": return capture_combo(args)
        if args.action in ("rtt","scope"): return capture(args)
        if args.action in ("info","usb-test"):
            with native_connection(args.serial) as native:
                info=native.info()
                if args.action=="usb-test":
                    if args.seconds<=0: parser.error("positive window required")
                    for n in (0,1,495,496,497,1008,2032,4079):
                        data=hashlib.shake_256(bytes([n%256])).digest(n)
                        if native.exchange(0,1,data)!=data: raise RuntimeError(f"native boundary mismatch at {n}")
                    seq=0
                    start=time.perf_counter()
                    while time.perf_counter()-start<args.seconds:
                        data=hashlib.shake_256(struct.pack("<I",seq)).digest(4079)
                        if native.exchange(0,1,data)!=data: raise RuntimeError(f"echo mismatch at frame {seq}")
                        seq+=1
                    elapsed=time.perf_counter()-start
                    info.update(seconds=elapsed,frames=seq,bytes_each=4079*seq,
                                combined_host_MBps=2*4079*seq/elapsed/1e6)
            print(json.dumps(info,indent=2))
            return 0
        payload = args.file.read_bytes() if args.action == "write" else None
        if args.action != "info":
            size = len(payload) if payload is not None else args.bytes
            if (size <= 0 or size % 4 or args.address % 4 or
                    not 0x20000000 <= args.address < args.address+size <= 0x20010000):
                parser.error("the F103 profile supports aligned words in its 64 KiB SRAM")
            if not 0 <= args.slot <= 63 or not 0 <= args.idle <= 255:
                parser.error("invalid timing fields")
            if args.transport == "jtag" and (args.slot < 16 or args.idle % 2 != 1):
                parser.error("JTAG needs a sample slot >=16 and odd idle")
            if args.transport == "swd" and args.idle > 15:
                parser.error("SWD idle must be 0..15")
            if args.action == "read" and args.out.exists():
                parser.error("output file already exists")
        with connection(args.serial) as (tx, rx), native_connection(args.serial,tx.device) as native:
            info=native.info()
            if not info["integrated_pl"]:
                raise RuntimeError("running PL does not advertise SelectIO queues")
            setup(tx, rx, 1000, args.transport)
            try:
                started = time.perf_counter()
                result=bytearray()
                offset=0
                with native.memory(PORTS[args.transport],args.tap,args.slot,args.idle):
                    while offset<size:
                        address=args.address+offset
                        n=min(size-offset,4032)
                        chunk=None if payload is None else payload[offset:offset+n]
                        result.extend(native.bulk(address,n,chunk))
                        offset+=n
                elapsed=time.perf_counter()-started
            finally:
                cmd(tx, rx, [3])
        if args.action == "read":
            with args.out.open("xb") as file:
                file.write(result)
        print(json.dumps(dict(transport=args.transport, direction=args.action, address=hex(args.address),
                              bytes=size, wire_hz=info["link_hz"], usb_seconds=elapsed,
                              usb_MBps=size/elapsed/1e6), indent=2))
        return 0
    except (RuntimeError, OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
