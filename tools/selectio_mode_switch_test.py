"""Alternate target transport after deliberately selecting the opposite stream preference."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from dap_pipeline_bench import cmd,setup
from selectio_cli import connection
from selectio_f103_fixture import BASE,DHCSR
from selectio_native import native_connection
from test_probe_board import Memory


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--swd-slot",type=int,default=24)
    ap.add_argument("--jtag-slot",type=int,default=28)
    ap.add_argument("--clock",type=int,choices=(50000000,73000000,100000000),default=100000000)
    ap.add_argument("--swd-idle",type=int,default=2)
    ap.add_argument("--jtag-idle",type=int,default=33)
    ap.add_argument("--rounds",type=int,default=64)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--execute",action="store_true")
    a=ap.parse_args()
    if not a.execute:return print(f"Alternating {a.clock//1000000} MHz JTAG and SWD SRAM reads after opposite stream selection.")
    a.out.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False,completed=0,requested_hz=a.clock)
    try:
        with connection(a.serial) as (tx,rx),native_connection(a.serial,tx.device) as native:
            native.info();setup(tx,rx,1000,"swd")
            mem=Memory(tx,rx)
            if not mem.word(DHCSR)&(1<<17):raise RuntimeError("requires the guarded F103ZE target")
            image=mem.read(BASE,4096)
            report["sha256"]=hashlib.sha256(image).hexdigest()
            started=time.perf_counter()
            try:
                for k in range(a.rounds):
                    for name,port,tap,slot,idle in (("jtag",2,16,a.jtag_slot,a.jtag_idle),("swd",1,8,a.swd_slot,a.swd_idle)):
                        rc,_=native.control(2,12,bytes([3-port]))
                        if rc:raise RuntimeError(f"previous stream selection failed {rc}")
                        setup(tx,rx,1000,name)
                        with native.memory(port,tap,slot,idle,a.clock):
                            offset=4*(k%256)
                            if native.bulk(BASE+offset,2048)!=image[offset:offset+2048]:
                                raise RuntimeError(f"{name} memory data differs after transport switch")
                        report["completed"]+=1
                report["elapsed"]=time.perf_counter()-started
            finally:
                native.control(2,12,b"\0")
                setup(tx,rx,1000,"swd")
                if mem.read(BASE,4096)!=image:raise RuntimeError("SRAM changed during read-only test")
                cmd(tx,rx,[3])
            report["passed"]=True
    finally:(a.out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))


if __name__=="__main__":main()
