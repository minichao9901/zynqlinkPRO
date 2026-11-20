"""Exercise one F103 page inside the backed-up, halted board fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

from dap_pipeline_bench import cmd, setup
from selectio_cli import PAGE, capabilities, connection, transfer
from test_probe_board import Memory
from selectio_native import native_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="12345678")
    parser.add_argument("--transport", required=True, choices=("swd","jtag"))
    parser.add_argument("--tap", type=int, required=True)
    parser.add_argument("--slot", type=int, required=True)
    parser.add_argument("--idle", type=int, required=True)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0 or args.rounds <= 0:
        parser.error("positive window and round count required")
    if not args.execute:
        print("Read/alternate 1 KiB at 0x20008000, then restore from an independent 1 MHz readback.")
        return
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(transport=args.transport, tap=args.tap, slot=args.slot, idle=args.idle, windows=[])
    def save():
        (args.out/"result.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    with connection(args.serial) as (tx,rx), native_connection(args.serial,tx.device) as native:
        report["info"] = native.info()
        if not report["info"]["integrated_pl"]: raise RuntimeError("wrong running PL")
        setup(tx,rx,1000,args.transport)
        mem = Memory(tx,rx)
        before = None
        dirty = False
        def block(data=None):
            return transfer(tx,rx,args.transport,PAGE,1024,data,args.tap,args.slot,args.idle,native)
        try:
            if mem.word(0xe0042000)!=0x10036414 or not mem.word(0xe000edf0)&(1<<17):
                raise RuntimeError("requires halted F103ZE fixture")
            before=mem.read(PAGE,1024)
            if mem.read(PAGE,1024)!=before:
                raise RuntimeError("unstable low-speed backup")
            guards=[mem.word(PAGE-4),mem.word(PAGE+1024)]
            (args.out/"page.bin").write_bytes(before)
            report.update(guards=guards,backup_sha256=hashlib.sha256(before).hexdigest())
            save()
            if block()!=before:
                raise RuntimeError("100 MHz read did not match independent backup")
            seq=0
            for _ in range(args.rounds):
                started=time.perf_counter()
                reads=writes=n=0
                while time.perf_counter()-started<args.seconds:
                    seq+=1
                    payload=hashlib.shake_256(struct.pack("<Q",seq)).digest(1024)
                    dirty=True
                    t0=time.perf_counter();block(payload);t1=time.perf_counter()
                    actual=block();t2=time.perf_counter()
                    if actual!=payload:
                        raise RuntimeError(f"payload mismatch at sequence {seq}")
                    reads+=t2-t1;writes+=t1-t0;n+=1024
                if mem.read(PAGE,1024)!=payload or [mem.word(PAGE-4),mem.word(PAGE+1024)]!=guards:
                    raise RuntimeError("independent pattern or guard mismatch")
                report["windows"].append(dict(seconds=time.perf_counter()-started,bytes_each=n,
                     read_MBps=n/reads/1e6,write_MBps=n/writes/1e6))
                save()
            report["passed"]=True
        except Exception as error:
            report.update(passed=False,error=str(error))
            raise
        finally:
            try:
                if dirty:
                    setup(tx,rx,1000,args.transport)
                    mem.write(PAGE,before)
                    report["restored"]=mem.read(PAGE,1024)==before and [mem.word(PAGE-4),mem.word(PAGE+1024)]==guards
                    if not report["restored"]:
                        raise RuntimeError("page recovery failed")
            finally:
                save()
                cmd(tx,rx,[3])


if __name__=="__main__":
    main()
