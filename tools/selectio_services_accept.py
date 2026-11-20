"""Check native RTT UP/DOWN plus one/eight-variable HSS on a halted F103ZE fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from selectio_f103_fixture import BASE,ROOT,low_link
from selectio_scope import export_scope


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--swd-slot",type=int,default=20)
    ap.add_argument("--jtag-slot",type=int,default=28)
    ap.add_argument("--confirm-seconds",type=float,default=5)
    ap.add_argument("--execute",action="store_true")
    args=ap.parse_args()
    if not args.execute:
        print("RTT UP/DOWN ring wrap and HSS rates on both physical transports.");return
    args.out.mkdir(parents=True,exist_ok=False)
    report={"points":[]}
    def save(): (args.out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    def cli(params,label):
        p=subprocess.run([sys.executable,"-X","utf8",str(ROOT/"toolbox.py"),"selectio","--serial",args.serial,*map(str,params)],
                         cwd=ROOT,capture_output=True)
        log=args.out/(label+".log")
        log.write_bytes(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError(log.read_text(encoding="utf8",errors="replace")[-700:])
        return json.loads(p.stdout)
    with low_link(args.serial) as m:
        if not m.word(0xe000edf0)&(1<<17):raise RuntimeError("requires a halted guarded fixture")
        original=m.read(BASE,4096)
        guards=[m.word(BASE-4),m.word(BASE+4096)]
    data=hashlib.shake_256(b"RTT bytewise UP check").digest(257)
    down=hashlib.shake_256(b"RTT DOWN wrap").digest(37)
    sample=[0x13579bdf^(i*0x1234567) for i in range(8)]
    (args.out/"down.bin").write_bytes(down)
    try:
        for transport,tap,slot,idle in (("swd",8,args.swd_slot,2),("jtag",16,args.jtag_slot,33)):
            profile=["--transport",transport,"--tap",tap,"--slot",slot,"--idle",idle]
            cli(["profile",*profile],transport+"-profile")
            contents=bytearray(original)
            struct.pack_into("<16sII",contents,0,b"SEGGER RTT",1,1)
            struct.pack_into("<6I",contents,24,0,BASE+0x301,512,254,509,0)
            for i,b in enumerate(data):contents[0x301+(509+i)%512]=b
            struct.pack_into("<6I",contents,48,0,BASE+0x601,512,500,300,0)
            struct.pack_into("<8I",contents,0xa00,*sample)
            with low_link(args.serial) as m:
                m.write(BASE,contents);assert m.read(BASE,4096)==contents
            target=args.out/(transport+"-up.bin")
            up_status=cli(["rtt","--transport",transport,"--clock",100000000,"--address",hex(BASE),"--size",48,
                           "--seconds",1,"--out",target],transport+"-up")
            if target.read_bytes()!=data:raise RuntimeError(transport+" RTT UP data mismatch")
            cli(["rtt-send",*profile,"--address",hex(BASE),"--file",args.out/"down.bin"],transport+"-down")
            with low_link(args.serial) as m:
                if m.word(BASE+40)!=254 or m.word(BASE+60)!=25:raise RuntimeError("RTT pointer mismatch")
                ring=m.read(BASE+0x601,512)
                if ring[500:]+ring[:25]!=down or ring[25:500]!=contents[0x601+25:0x601+500]:
                    raise RuntimeError("RTT DOWN data or guard mismatch")
            report[transport+"_rtt"]=dict(up_bytes=len(data),down_bytes=len(down),status=up_status["status"]);save()
            for channels,periods in [(1,[24,32,48,64,96,128]),(8,[144,192,240,320,416,600,960])]:
                plan=[]
                for i in range(channels):plan.extend(["--var",f"{BASE+0xa00+4*i:#x}:4:4"])
                expected=struct.pack("<"+"I"*channels,*sample[:channels])
                def point(ticks,seconds,kind):
                    name=f"{transport}-{channels}-{ticks}-{kind}"
                    dest=args.out/(name+".hss")
                    status=cli(["scope","--transport",transport,"--clock",100000000,"--period",ticks,*plan,
                                "--seconds",seconds,"--out",dest],name)
                    verified=export_scope(dest,expected=expected)
                    skipped=verified["stat"]["skipped"];groups=verified["groups"]
                    row=dict(transport=transport,channels=channels,ticks=ticks,seconds=seconds,stage=kind,
                             actual_link_hz=status["status"][1],groups=groups,skipped=skipped,
                             skipped_fraction=skipped/max(1,skipped+groups),frames=verified["packets"],
                             tail_match=groups==status["status"][2],read_errors=verified["stat"]["read_errors"])
                    report["points"].append(row);save()
                    if not row["tail_match"] or not groups:raise RuntimeError(name+" empty or mismatched STOP")
                    return row["skipped_fraction"]<0.001
                for t in periods:
                    if point(t,0.4,"trial") and point(t,args.confirm_seconds,"confirm"):break
                else:raise RuntimeError(f"no sustained {transport} {channels}-channel point")
        report["passed"]=True
    except BaseException as ex:
        report.update(passed=False,error=str(ex));raise
    finally:
        try:
            with low_link(args.serial) as m:
                m.write(BASE,original)
                report["restored"]=m.read(BASE,4096)==original and [m.word(BASE-4),m.word(BASE+4096)]==guards
                if not report["restored"]:raise RuntimeError("test image recovery failed")
        finally:save()


if __name__=="__main__":main()
