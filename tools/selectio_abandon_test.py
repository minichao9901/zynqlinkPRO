"""Exercise native host loss without resetting the target or reloading the probe."""
import argparse
import json
from pathlib import Path
import struct
import time

from dap_pipeline_bench import cmd,setup
from selectio_cli import connection
from selectio_native import native_connection,NativeStatusError
from selectio_f103_fixture import BASE
from test_probe_board import Memory


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678");ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--clock",type=int,choices=(50000000,73000000,100000000),default=100000000)
    ap.add_argument("--tap",type=int,choices=range(32),default=8)
    ap.add_argument("--slot",type=int,choices=range(64),default=24)
    ap.add_argument("--idle",type=int,choices=range(16),default=2)
    a=ap.parse_args()
    if not a.execute:return print("Drop native SPI and HSS leases, then reacquire and verify SRAM.")
    a.out.mkdir(parents=True,exist_ok=False)
    result={}
    def configure_scope(port):
        port.exchange(0,2,bytes((1,a.tap,a.slot,a.idle)))
        port.exchange(3,0,b"\1")
        for op,data in [(12,b"\1"),(3,struct.pack("<I",a.clock)),
                        (10,struct.pack("<IBBIBB",24000,0,1,BASE,4,4)),(1,b"")]:
            rc,_=port.control(3,op,data)
            if rc:raise RuntimeError(f"HSS action {op} failed with {rc}")
    cfg=struct.pack("<BBBBIB",0,0,0,22,100000000,0)
    try:
        for kind in ("spi","scope"):
            with connection(a.serial) as (tx,rx),native_connection(a.serial,tx.device) as port:
                port.info();setup(tx,rx,1000,"swd");expected=Memory(tx,rx).read(BASE,32)
                if kind=="spi":port.exchange(4,0,cfg)
                else:configure_scope(port)
                # A complete, unread response may survive handle closure.
                port._write(0,1,b"old-handle")
            started=time.perf_counter()
            while True:
                try:
                    with native_connection(a.serial) as new:
                        new.info();new.exchange(4,0,cfg);new.exchange(4,5)
                    break
                except NativeStatusError as error:
                    if error.status!=2 or time.perf_counter()-started>10:raise
                    time.sleep(.2)
            with connection(a.serial) as (tx,rx):
                setup(tx,rx,1000,"swd")
                if Memory(tx,rx).read(BASE,32)!=expected:raise RuntimeError("target SRAM differs after recovery")
                cmd(tx,rx,[3])
            result[kind]=dict(passed=True,reacquire_seconds=time.perf_counter()-started)
        result["passed"]=True
    finally:(a.out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))


if __name__=="__main__":main()
