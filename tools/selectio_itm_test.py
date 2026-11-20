"""Compare a finite stream of real F103 ITM packets with the target producer."""
import argparse,hashlib,json,struct,time
from contextlib import ExitStack
from selectio_cmsis_swo import cmsis_swo
from pathlib import Path
from benchmark_rtt_forward import core_read,core_write
from selectio_f103_fixture import BASE,DHCSR
from selectio_f103_swo import f103_swo
from selectio_native import native_connection


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--binary",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--words",type=int,default=16384)
    ap.add_argument("--usb-path",choices=("native","cmsis-dap"),default="native")
    ap.add_argument("--execute",action="store_true")
    args=ap.parse_args()
    if not args.execute:return print("Run the SRAM ITM producer in the halted and backed-up F103 fixture.")
    if not 1<=args.words<=2000000:ap.error("invalid word count")
    code=args.binary.read_bytes()
    if not 0<len(code)<512:ap.error("unexpected producer size")
    args.out.mkdir(parents=True,exist_ok=False)
    report=[]
    expected=b"".join(b"\x03"+struct.pack("<I",i) for i in range(args.words))
    for encoding,rate in (("uart",3000000),("manchester",1500000),("uart",48000000),("manchester",24000000)):
        result=dict(encoding=encoding,rate=rate,words=args.words,usb_path=args.usb_path)
        with f103_swo(args.serial,encoding,rate,1) as target,ExitStack() as session:
            m=target.memory
            if not m.word(DHCSR)&(1<<17):raise RuntimeError("target must be halted")
            if args.usb_path=="native":
                native=session.enter_context(native_connection(args.serial,target.device))
                native.info()
            regs={i:core_read(m,i) for i in [*range(17),20]}
            image=m.read(BASE,1024)
            active=False;received=bytearray()
            try:
                m.write(BASE,code);m.write(BASE+0x200,struct.pack("<2I",args.words,0))
                if m.read(BASE,len(code))!=code:raise RuntimeError("ITM producer differs")
                cfg=struct.pack("<BBBBIB",1 if encoding=="uart" else 2,0,0,0,rate,0)
                if args.usb_path=="native":
                    native.exchange(5,0,cfg)
                    active=True
                    pull=lambda: native.exchange(5,1)
                    stop=lambda: native.exchange(5,3)
                else:
                    standard=session.enter_context(cmsis_swo(*target.endpoints,encoding,rate))
                    pull=standard.pull
                    stop=standard.stop
                target.start()
                core_write(m,16,0x01000000);core_write(m,20,1);core_write(m,15,BASE+1)
                start=time.perf_counter()
                m.write_word(DHCSR,0xa05f0001)
                deadline=start+max(2.0,len(expected)*20/rate+1.0)
                while len(received)<len(expected) and time.perf_counter()<deadline:
                    received.extend(pull())
                result["collect_seconds"]=time.perf_counter()-start
                m.write_word(DHCSR,0xa05f0003)
                stop()
                while part:=pull():received.extend(part)
                if args.usb_path=="native":
                    result["status"]=list(struct.unpack("<5I",native.exchange(5,4)))
                else:
                    state=standard.status()
                    result["cmsis_tail"]=state
                    result["status"]=[state["pending"],state["status"]&128,state["status"]&64]
                    if state["index"]!=len(received):raise RuntimeError("CMSIS trace index differs")
                result["producer_words"]=m.word(BASE+0x204)
                result["bytes"]=len(received)
                result["sha256"]=hashlib.sha256(received).hexdigest()
                result["passed"]=received==expected and not any(result["status"][:3]) and result["producer_words"]==args.words
                if not result["passed"]:result["prefix"]=received[:32].hex()
            finally:
                try:
                    if active:native.exchange(5,5)
                finally:
                    m.write_word(DHCSR,0xa05f0003);m.write(BASE,image)
                    for reg in [*range(15),20,16,15]:core_write(m,reg,regs[reg])
                    if m.read(BASE,1024)!=image or any(core_read(m,r)!=v for r,v in regs.items()):
                        raise RuntimeError("ITM test core or SRAM recovery failed")
                    result["restored"]=True
        report.append(result);(args.out/"result.json").write_text(json.dumps(report,indent=2));print(result,flush=True)
    return 0 if all(r["passed"] for r in report) else 1


if __name__=="__main__":raise SystemExit(main())
