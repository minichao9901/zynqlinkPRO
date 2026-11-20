"""Qualify J7 SPI and serial reception through the two real F103 BYPASS cells."""
import argparse
from contextlib import contextmanager,nullcontext
import hashlib
import json
from pathlib import Path
import struct
import time

from dap_pipeline_bench import cmd, setup
from selectio_cli import connection
from selectio_native import native_connection


@contextmanager
def fast_f103_tdo(serial):
    from selectio_f103_fixture import low_link
    enable,crl,dbg=0x40021018,0x40010c00,0xe0042004
    with low_link(serial) as mem:
        if not mem.word(0xe000edf0)&(1<<17):raise RuntimeError("guarded F103 expected")
        apb=mem.word(enable)
        mem.write_word(enable,apb|8)
        gpio=mem.word(crl);trace=mem.word(dbg)
    try:
        with low_link(serial) as mem:
            mem.write_word(dbg,trace&~0xe0)
            mem.write_word(crl,(gpio&~0xf000)|0xb000)
        yield
    finally:
        with low_link(serial) as mem:
            mem.write_word(crl,gpio);mem.write_word(dbg,trace)
            if mem.word(crl)!=gpio or mem.word(dbg)!=trace:raise RuntimeError("TDO GPIO restoration differs")
            mem.write_word(enable,apb)
            if mem.word(enable)!=apb:raise RuntimeError("TDO GPIO clock restoration differs")


def install_bypass(tx,rx):
    setup(tx,rx,1000,"jtag")
    steps=[(1,6,0),(0,1,0),(1,2,0),(0,2,0),(0,8,255),(1,1,1),(1,1,0),(0,1,0),(1,1,0),(0,2,0)]
    packet=bytearray([0x14,len(steps)])
    for tms,n,data in steps:packet.extend((n|(tms<<6),data))
    if cmd(tx,rx,packet)!=b"\x14\0":raise RuntimeError("TAP setup rejected")
    pattern=bytes.fromhex("591f86cbe27a3504")
    reply=cmd(tx,rx,b"\x14\x01\x80"+pattern)
    got=int.from_bytes(reply[2:],"little")
    expected=(int.from_bytes(pattern,"little")<<2)&((1<<64)-1)
    if reply[:2]!=b"\x14\0" or got!=expected:
        raise RuntimeError(f"low-speed BYPASS differs: {got:016x} != {expected:016x}")
    cmd(tx,rx,b"\x14\x01\x02\x00")


def encode(data,manchester):
    bits=[0 if manchester else 1]*32
    if manchester:
        for first in range(0,len(data),8):
            bits.extend((1,0))
            for v in data[first:first+8]:
                for i in range(8):
                    b=(v>>i)&1
                    bits.extend((b,1-b))
            bits.extend([0]*8)
    else:
        for v in data:bits.extend([0,*((v>>i)&1 for i in range(8)),1])
    bits.extend([0 if manchester else 1]*32)
    while len(bits)%8:bits.append(bits[-1])
    return bytes(sum(bit<<(7-j) for j,bit in enumerate(bits[i:i+8])) for i in range(0,len(bits),8))


def qualify_bypass_source(port):
    # Prepare and identify the two TAPs after the final pin handoff. Both
    # the 25 MHz reference and the following waveform use the same owner.
    steps=[(8,1,0),(1,0,0),(2,1,0),(2,0,0),(8,0,1),(1,1,1),
           (1,1,0),(1,0,0),(1,1,0),(2,0,0)]
    wave=bytearray()
    def clock(tms,tdi):
        wave.extend((0,255*tms,255*tdi,255,255*tms,255*tdi))
    for n,tms,tdi in steps:
        for _ in range(n):clock(tms,tdi)
    pattern=[(b>>i)&1 for b in bytes.fromhex("591f86cbe27a3504") for i in range(8)]
    start=len(wave)//6
    for bit in pattern+[0]*12:clock(0,bit)
    port.exchange(4,8,wave)
    raw=port.exchange(4,7)
    levels=[(b>>i)&1 for b in raw for i in range(8)]
    errors,delay=min((sum(levels[16*(start+i)+8+lag]!=pattern[i-2] for i in range(2,64)),lag)
                     for lag in range(64))
    while port.exchange(4,1):pass
    initial=struct.unpack("<5I",port.exchange(4,4))
    return dict(reference_bits=62,reference_errors=errors,return_delay=delay,
                initialization_drops=initial[1],initialization_framing=initial[2])


def captured(port,cfg,data,op=2,raw=None,source=None):
    port.exchange(4,0,cfg)
    try:
        if source is not None:source.update(qualify_bypass_source(port))
        port.exchange(4,op,data)
        if raw is not None:raw.extend(port.exchange(4,7))
        port.exchange(4,3)
        output=bytearray()
        while True:
            part=port.exchange(4,1)
            if not part:break
            output.extend(part)
        status=struct.unpack("<5I",port.exchange(4,4))
        if source is not None:
            status=(status[0],status[1]-source["initialization_drops"],
                    status[2]-source["initialization_framing"],*status[3:])
        return bytes(output),status
    finally:port.exchange(4,5)


def sparse_waveform(data,advance):
    symbols=[]
    for first in range(0,len(data),8):
        symbols.extend((1,0))
        for v in data[first:first+8]:
            for j in range(8):
                bit=(v>>j)&1
                symbols.extend((bit,1-bit))
        symbols.extend([0]*12)
    events=[(8+i*8,0) for i in range(8)]
    previous=0
    for i,level in enumerate(symbols):
        if previous!=level:events.append((100+i*2,level));previous=level
    end=100+len(symbols)*2
    events.extend([(end+8,0),(end+16,0)])
    slots=8*((end+40+7)//8)
    c=[0]*slots;d=[0]*slots;prior_fall=0;prior_rise=0
    for i,(fall,out) in enumerate(events):
        width=2 if fall-prior_fall>=4 else 1
        rise=fall-width;c[rise:fall]=[1]*width
        begin=prior_rise+1 if advance else prior_fall
        bit=events[i+1][1] if i+1<len(events) else 0
        d[begin:fall]=[bit]*(fall-begin)
        prior_rise=rise;prior_fall=fall
    result=bytearray()
    for at in range(0,slots,8):
        result.extend((sum(c[at+i]<<i for i in range(8)),0,sum(d[at+i]<<i for i in range(8))))
    return bytes(result)

def pad_waveform(encoded):
    # Apply two identical 2.5 ns DDR slots per Manchester half-bit. TCK
    # remains low, independently isolating pad reception from the target TAP.
    bits=[(b>>i)&1 for b in encoded for i in range(7,-1,-1) for _ in range(2)]
    return bytes(v for i in range(0,len(bits),8) for v in (0,0,sum(bits[i+j]<<j for j in range(8))))


def raw_alignment(data,observed):
    # A 32-symbol idle guard at each end accommodates actual gearbox latency.
    # Check the complete encoded frames between those guards.
    levels=[(data[i]>>j)&1 for i in range(2,len(data),3) for j in range(8)]
    raw=[(b>>j)&1 for b in observed for j in range(8)]
    begin,end=64,len(levels)-64
    scores=[]
    for lag in range(64):
        if end+lag<=len(raw):
            errors=sum(levels[i]!=raw[i+lag] for i in range(begin,end))
            scores.append((errors,lag))
    errors,delay=min(scores)
    center_errors,phase=min((sum(levels[i]!=raw[i+delay] for i in range(begin+phase,end,2)),phase) for phase in (0,1))
    return dict(compared_ddr_slots=end-begin,delta_slots=delay,different_samples=errors,
                symbols=(end-begin)//2,center_phase=phase,center_errors=center_errors)


def extended_tests(tx,rx,port,seconds,rows,save,only=None,features=0):
    # In SPI tests the remote target contains two single-bit BYPASS cells.
    # The returned bit offset includes the orientation of the sampling edge.
    cases=[("spi-mode0",0,0,0,100000000,0)]
    cases.extend((f"spi-pad-mode{mode}",0,0,mode,100000000,1) for mode in range(4))
    cases.extend([
        ("uart-tx-remote",1,3,0,100000000,2),
        ("uart-rx-remote",1,0,0,100000000,0),
        ("manchester50-remote",2,2,0,50000000,0),
        ("manchester100-tdi-pad",2,2,0,100000000,1),
        ("manchester100-sparse-remote",2,2,0,100000000,0),
    ])
    if only and "manchester100-mixed-remote" in only:
        cases.append(("manchester100-mixed-remote",2,2,0,100000000,0))
    for kind,codec,drive,mode,rate,flags in cases:
        if only and kind not in only:continue
        row=dict(kind=kind,rate=rate,mode=mode,passed=False,points=[])
        rows.append(row)
        def attempt(tap,slot,iteration,probe):
            install_bypass(tx,rx)
            n=64 if probe else 2048 if codec==0 else 96 if codec==1 else 32
            if codec==2: n=32
            sample=hashlib.shake_256(kind.encode()+struct.pack("<I",iteration)).digest(n)
            op=2
            if kind in ("manchester100-sparse-remote","manchester100-mixed-remote"):
                if kind=="manchester100-sparse-remote":sample=b"\xaa"*32
                wire=sparse_waveform(sample,True)
                op=8
            elif kind=="manchester100-tdi-pad":
                wire=pad_waveform(encode(sample,True))
                op=8
            elif codec==0 or drive==3: wire=sample
            else: wire=encode(sample,codec==2)
            cfg=struct.pack("<BBBBIBB",codec,drive,mode,slot,rate,tap,flags)
            local=kind=="manchester100-tdi-pad"
            remote=kind in ("manchester100-sparse-remote","manchester100-mixed-remote")
            raw=bytearray() if (local and features&0x2000) or remote else None
            training={} if remote else None
            got,status=captured(port,cfg,wire,op,raw,training)
            if training is not None:
                row["source_training"]=training
                if not probe:
                    row["qualification_bits"]=row.get("qualification_bits",0)+training["reference_bits"]
                    row["qualification_errors"]=row.get("qualification_errors",0)+training["reference_errors"]
            if remote and raw is not None:
                bits=[(b>>i)&1 for b in raw for i in range(8)]
                row["raw_remote"]=dict(high=sum(bits),slots=len(bits),transitions=sum(a!=b for a,b in zip(bits,bits[1:])),
                                       head=raw[:32].hex())
                if probe:
                    row.setdefault("raw_points",[]).append(dict(tap=tap,slot=slot,**row["raw_remote"]))
            if local and raw is not None:
                applied=raw_alignment(wire,raw)
                row["applied_waveform"]=applied
                if not probe:
                    row["confirmed_source_symbols"]=row.get("confirmed_source_symbols",0)+applied["symbols"]
                    row["source_center_differences"]=row.get("source_center_differences",0)+applied["center_errors"]
            if kind.startswith("spi-pad"):
                return got==sample and not any(status[:3]),len(got),0,status,got[:12].hex()
            delay=0
            if codec==0:
                source=int.from_bytes(sample,"big")
                for delay in range(1,5):
                    if got==(source>>delay).to_bytes(n,"big"):break
                else:delay=-1
                ok=delay>0
            else:ok=got==sample
            return ok and not any(status[:3]) and not (training and training["reference_errors"]),len(got),delay,status,got[:12].hex()
        winner=None
        for tap in (0,8,16,24,4,12,20,28):
            slots=(22,20,24,18,26,16,28,19,21,23,25,27,29,30,12,13,14,15,17,31,32,33,34,35) if codec==0 else (20,21) if codec==2 else (20,)
            for slot in slots:
                ok,n,delay,status,head=attempt(tap,slot,0,True)
                row["points"].append(dict(tap=tap,slot=slot,ok=ok,bytes=n,returned_delay=delay,
                                          overflow=status[1],framing=status[2],prefix=head))
                save()
                if ok:
                    checks=8 if codec==2 else 2
                    for seed in range(1,checks+1):
                        more_ok,_,more_delay,_,_=attempt(tap,slot,seed,True)
                        if not more_ok or more_delay!=delay:break
                    else:
                        winner=(tap,slot,delay)
                        break
            if winner:break
        if not winner:
            print(kind,"no matching physical return",flush=True)
            continue
        first=time.monotonic();cycles=total=0;row["passed"]=True
        while time.monotonic()-first<seconds:
            ok,n,delay,status,head=attempt(winner[0],winner[1],cycles+1,False)
            if not ok or delay!=winner[2]:
                row.update(passed=False,failure=dict(cycle=cycles,status=status,prefix=head));break
            total+=n;cycles+=1
        row.update(tap=winner[0],slot=winner[1],transactions=cycles,confirmed_bytes=total,
                   elapsed=time.monotonic()-first,returned_delay=winner[2]);save()
        print(kind,row["passed"],total,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial",default="12345678")
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--seconds",type=float,default=10)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--extended",action="store_true",help="qualify all four SPI modes, dedicated UART TX and loaded-pad Manchester at 100 Mbit/s")
    parser.add_argument("--only",action="append",help="select one named extended wire test")
    parser.add_argument("--fast-f103-tdo",action="store_true",help="temporarily select PB3 AF push-pull 50 MHz in the guarded F103 fixture")
    args=parser.parse_args()
    if not args.execute:
        print("Select the BYPASS instruction on both F103 TAPs, clock known symbols through TDI/TDO, then restore debug routing.")
        return
    args.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    def save():
        (args.out/"wire.json").write_text(json.dumps(rows,indent=2)+"\n")
    drive=fast_f103_tdo(args.serial) if args.fast_f103_tdo else nullcontext()
    with drive,connection(args.serial) as (tx,rx), native_connection(args.serial,tx.device) as port:
        features=int(port.info()["features"],16)
        try:
            if args.extended:
                extended_tests(tx,rx,port,args.seconds,rows,save,args.only,features)
                return 0 if all(r.get("passed") for r in rows) else 1
            for kind in ("spi","uart","manchester"):
                result=dict(kind=kind,points=[])
                rows.append(result)
                winner=None
                for tap in (0,8,16,24):
                    slots=(16,20,24,28,12,32,18,22,26,30,14,34,17,19,21,23,25,27) if kind=="spi" else (20,)
                    for slot in slots:
                        install_bypass(tx,rx)
                        sample=hashlib.shake_256(kind.encode()).digest(64)
                        codec={"spi":0,"uart":1,"manchester":2}[kind]
                        cfg=struct.pack("<BBBBIB",codec,2 if kind=="manchester" else 0,0,slot,100000000,tap)
                        wire=sample if kind=="spi" else encode(sample,kind=="manchester")
                        expected=(int.from_bytes(wire,"big")>>2).to_bytes(len(wire),"big") if kind=="spi" else sample
                        got,status=captured(port,cfg,wire)
                        ok=got==expected and status[:3]==(0,0,0)
                        point=dict(tap=tap,slot=slot,received=len(got),expected=len(expected),errors=status[2],overflow=status[1],
                                   prefix=got[:16].hex(),expected_prefix=expected[:16].hex(),passed=ok)
                        result["points"].append(point);save()
                        if ok: winner=cfg;break
                    if winner:break
                result["passed"]=winner is not None;save()
                if not winner:continue
                first=time.monotonic();cycles=0;total=0
                while time.monotonic()-first<args.seconds:
                    install_bypass(tx,rx)
                    sample=hashlib.shake_256(struct.pack("<I",cycles)).digest(2048 if kind=="spi" else 96)
                    wire=sample if kind=="spi" else encode(sample,kind=="manchester")
                    expect=(int.from_bytes(wire,"big")>>2).to_bytes(len(wire),"big") if kind=="spi" else sample
                    got,status=captured(port,winner,wire)
                    if got!=expect or any(status[:3]):
                        result.update(passed=False,error="confirmation mismatch",status=status,cycle=cycles);break
                    total+=len(got);cycles+=1
                result.update(confirmed_bytes=total,transactions=cycles,elapsed=time.monotonic()-first);save()
                print(kind,result["passed"],total,flush=True)
        finally:
            try:setup(tx,rx,1000,"swd")
            finally:cmd(tx,rx,[3])
    return 0 if all(r.get("passed") for r in rows) else 1


if __name__=="__main__":
    raise SystemExit(main())
