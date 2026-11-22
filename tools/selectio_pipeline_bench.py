"""Verified native USB pipeline throughput, inside the F103ZE SRAM fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

from dap_pipeline_bench import cmd,setup
from selectio_cli import PAGE,PORTS,connection
from selectio_native import native_connection
from test_probe_board import Memory


def measure_window(native,direction,address,n,depth,seconds,index,seq,expected,*,transport_only=False):
    count=0
    active_time=0
    started=time.perf_counter()
    while time.perf_counter()-started<seconds:
        batch=[];checks=[]
        for i in range(16):
            write=direction=="write" or (direction=="mixed" and i%2==0)
            if write:
                seq+=1
                expected=hashlib.shake_256(struct.pack("<II",index,seq)).digest(n)
            batch.append((address,n,expected if write else None))
            checks.append(b"" if write else expected)
        t0=time.perf_counter()
        actual=native.bulk_many(batch,depth,transport_only=transport_only)
        active_time+=time.perf_counter()-t0
        if actual!=checks:raise RuntimeError(f"payload or order differs at {count}")
        count+=len(batch)
    elapsed=time.perf_counter()-started
    return count,elapsed,active_time,seq,expected


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--transport",choices=PORTS,required=True)
    ap.add_argument("--tap",type=int,required=True)
    ap.add_argument("--slot",type=int,required=True)
    ap.add_argument("--idle",type=int,required=True)
    ap.add_argument("--bytes",type=int,default=4032)
    ap.add_argument("--address",type=lambda value:int(value,0),default=PAGE+32)
    ap.add_argument("--depth",type=int,choices=range(1,5),default=4)
    ap.add_argument("--seconds",type=float,default=10)
    ap.add_argument("--rounds",type=int,default=3)
    ap.add_argument("--directions",nargs="+",choices=("read","write","mixed"),default=["read","write","mixed"])
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--clock",type=int,choices=(50000000,100000000),default=100000000)
    ap.add_argument("--frame",type=int,choices=(4096,16384),help="cap the negotiated WinUSB frame")
    ap.add_argument("--schedule",choices=("sliding","grouped"),default="sliding")
    args=ap.parse_args()
    if not args.execute:
        print("Verify fresh USB payloads and restore the backed-up F103 SRAM page.");return
    n=args.bytes;address=args.address
    if (n<=0 or n%4 or n>16320 or address%4 or not PAGE<=address<=PAGE+16384-n or
        args.seconds<=0 or args.rounds<1):ap.error("invalid window or guarded SRAM payload")
    args.out.mkdir(parents=True,exist_ok=False)
    report=dict(transport=args.transport,requested_hz=args.clock,tap=args.tap,slot=args.slot,idle=args.idle,
                bytes=n,address=hex(address),depth=args.depth,windows=[])
    def save(): (args.out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    with connection(args.serial) as (tx,rx),native_connection(args.serial,tx.device) as native:
        report["info"]=native.info()
        if args.frame:native.set_frame_size(args.frame)
        native.sliding=args.schedule=="sliding"
        report.update(frame=native.frame_size,schedule=args.schedule)
        if n>native.max_bulk:raise ValueError("loaded probe frame is too small")
        setup(tx,rx,1000,args.transport);mem=Memory(tx,rx)
        original=None;dirty=False
        try:
            if mem.word(0xe0042000)!=0x10036414 or not mem.word(0xe000edf0)&(1<<17):
                raise RuntimeError("requires the halted F103ZE fixture")
            original=mem.read(address,n)
            if mem.read(address,n)!=original:raise RuntimeError("unstable SRAM backup")
            guards=[mem.word(address-4),mem.word(address+n)]
            (args.out/"page.bin").write_bytes(original)
            report.update(guards=guards,backup_sha256=hashlib.sha256(original).hexdigest());save()
            seq=0
            for index in range(args.rounds):
                for direction in args.directions:
                    with native.memory(PORTS[args.transport],args.tap,args.slot,args.idle,args.clock):
                        expected=hashlib.shake_256(struct.pack("<II",index,seq)).digest(n)
                        dirty=True;native.bulk(address,n,expected)
                        if native.bulk(address,n)!=expected:raise RuntimeError("prefill failed")
                        before=native.memory_stats()
                        count,elapsed,active_time,seq,expected=measure_window(native,direction,address,n,args.depth,
                            args.seconds,index,seq,expected)
                        probe=native.memory_stats()
                        clock=native.memory_clock(PORTS[args.transport],report["info"]["reference_hz"],args.clock)
                    delta={k:probe[k]-before[k] for k in ("read_bytes","write_bytes")}
                    for key in ("queue_s","probe_s"):
                        delta[key]=[a-b for a,b in zip(probe[key],before[key])]
                    if delta["read_bytes"]+delta["write_bytes"]!=count*n:
                        raise RuntimeError("probe window byte counters differ from verified host payload")
                    if mem.read(address,n)!=expected or [mem.word(address-4),mem.word(address+n)]!=guards:
                        raise RuntimeError("final image or SRAM guard differs")
                    report["windows"].append(dict(round=index+1,direction=direction,requests=count,
                          payload_bytes=count*n,wall_seconds=elapsed,USB_seconds=active_time,
                          wall_MBps=count*n/elapsed/1e6,USB_MBps=count*n/active_time/1e6,probe=probe,probe_delta=delta,clock=clock))
                    save();print(report["windows"][-1],flush=True)
            report["passed"]=True
        except Exception as exc:
            report.update(passed=False,error=str(exc));raise
        finally:
            try:
                if dirty:
                    setup(tx,rx,1000,args.transport);mem.write(address,original)
                    report["restored"]=mem.read(address,n)==original and [mem.word(address-4),mem.word(address+n)]==guards
                    if not report["restored"]:raise RuntimeError("SRAM recovery differs")
            finally:save();cmd(tx,rx,[3])


if __name__=="__main__":
    main()
