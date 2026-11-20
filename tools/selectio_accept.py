"""F103ZE CLI-only SelectIO acceptance. The default is a hardware-free preview."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SUITES=("usb","switch","debug","memory","rtt","scope","combo","wire","cdc","itm","etm")


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board",choices=("f103ze",),required=True)
    ap.add_argument("--pair",type=Path,default=ROOT/"prebuilt/selectio-j7-fusion")
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--out",type=Path)
    ap.add_argument("--etm-out",type=Path,help="new native ETM record directory")
    ap.add_argument("--seconds",type=float,default=60)
    ap.add_argument("--rounds",type=int,default=3,help="read/write/mixed SRAM windows per transport")
    ap.add_argument("--only",action="append",choices=SUITES)
    ap.add_argument("--execute",action="store_true")
    args=ap.parse_args(argv)
    if args.seconds<=0 or args.rounds<=0:ap.error("positive durations and round counts required")
    selected=args.only or SUITES
    pair=args.pair.resolve()
    out=(args.out or ROOT/"build"/("selectio-accept-"+datetime.now().strftime("%Y%m%d-%H%M%S"))).resolve()
    summary=dict(board=args.board,operation="HS3 JTAG/RAM, guarded F103ZE SRAM",suites=selected,
                 serial=args.serial,seconds=args.seconds,rounds=args.rounds,pair=str(pair),out=str(out),cases=[])
    if not args.execute:
        print(json.dumps(summary,indent=2));return 0
    identity=json.loads((pair/"manifest.json").read_text(encoding="utf8"))
    for name in ("probe.bit","application.elf","ps7_init.tcl"):
        if hashlib.sha256((pair/name).read_bytes()).hexdigest()!=identity["hashes"][name]:
            raise ValueError(f"artifact hash differs for {name}")
    out.mkdir(parents=True,exist_ok=False)
    summary["hashes"]=identity["hashes"]
    py=[sys.executable,"-X","utf8"]
    cli=[*py,ROOT/"toolbox.py"]
    def save():
        (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8")
    def run(name,cmd,guard=False):
        start=time.monotonic()
        state=out/(name+"-guard")
        if guard:
            cmd=[*py,ROOT/"tools/selectio_f103_fixture.py","--serial",args.serial,"--out",state,"--execute","--",*cmd]
        log=out/(name+".log")
        with log.open("xb") as stream:
            p=subprocess.run(list(map(str,cmd)),stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
        row=dict(name=name,passed=p.returncode==0,exit_code=p.returncode,seconds=time.monotonic()-start,log=log.name)
        if guard:
            path=state/"state.json"
            row["restored"]=path.is_file() and json.loads(path.read_text(encoding="utf8")).get("restored") is True
        summary["cases"].append(row);save();print(json.dumps(row),flush=True)
        if guard and not row["restored"]:
            raise RuntimeError(f"{name}: inspect {state}; recovery not confirmed")
        return row["passed"]
    def test(name,script,options):
        return run(name,[*py,ROOT/"tools"/script,"--serial",args.serial,"--out",out/name,*options,"--execute"],True)
    def fixture(src,entry,parameters=()):
        binary=out/(entry+".bin")
        elf=out/(entry+".elf")
        subprocess.run(["arm-none-eabi-gcc","-mcpu=cortex-m3","-mthumb","-nostdlib",
                        "-Wl,--build-id=none","-Wl,-Ttext=0x20008000","-Wl,-e,"+entry,*parameters,
                        ROOT/"firmware/target"/src,"-o",elf],check=True)
        subprocess.run(["arm-none-eabi-objcopy","-O","binary","-j",".text",elf,binary],check=True)
        return binary
    save()
    if not run("load",[*cli,"probe-load","--bit",pair/"probe.bit","--zynq-elf",pair/"application.elf",
               "--ps-init",pair/"ps7_init.tcl","--out",out/"load"]):
        return 1
    if not run("info",[*cli,"selectio","--serial",args.serial,"info"]):return 1
    info=json.loads((out/"info.log").read_text(encoding="utf8"))
    if int(info["features"],16)!=int(identity["bit_features"],16):
        raise RuntimeError("live feature word differs from the loaded pair manifest")
    if "usb" in selected:
        for i in range(args.rounds):
            run("usb-"+str(i+1),[*cli,"selectio","--serial",args.serial,"usb-test","--seconds",args.seconds])
    if "switch" in selected:
        test("switch","selectio_mode_switch_test.py",["--swd-slot",identity["swd"]["slot"],
             "--jtag-slot",identity["jtag"]["slot"],"--rounds",64])
        if identity.get("native_stream_lease_seconds"):
            test("host-loss","selectio_abandon_test.py",[])
    producer=None
    if "rtt" in selected or "combo" in selected:
        producer=fixture("probe_rtt_ram.S","producer",["-Wa,--defsym,FIXTURE_BASE=0x20008000",
                             "-Wa,--defsym,RTT_RING_OFFSET=0x400","-Wa,--defsym,RTT_RING_MASK=1023"])
    for transport in ("swd","jtag"):
        cfg=identity[transport]
        common=["--transport",transport,"--slot",cfg["slot"]]
        if "debug" in selected:test("debug-"+transport,"selectio_debug_test.py",common)
        if "memory" in selected:
            test("memory-"+transport,"selectio_pipeline_bench.py",[*common,"--tap",cfg["tap"],"--idle",cfg["idle"],
                 "--bytes",4032,"--depth",4,"--seconds",args.seconds,"--rounds",args.rounds])
        for service in ("rtt","combo"):
            if service in selected:test(service+"-"+transport,"selectio_running_test.py",
                [*common,"--seconds",args.seconds,"--service",service,"--binary",producer])
    if "scope" in selected:test("services","selectio_services_accept.py",["--swd-slot",identity["swd"]["slot"],
                       "--jtag-slot",identity["jtag"]["slot"],"--confirm-seconds",args.seconds])
    if "wire" in selected:
        test("wire","selectio_wire_test.py",["--extended","--seconds",args.seconds])
        test("spi-target","selectio_spi_target_test.py",["--seconds",args.seconds])
    if "cdc" in selected:test("cdc","selectio_cdc_test.py",["--binary",fixture("selectio_f103_uart_echo.S","echo"),
                       "--swd-slot",identity["swd"]["slot"]])
    if "cdc" in selected and identity.get("cdc_bypass_qualification"):
        test("cdc-100m","selectio_cdc_wire_test.py",["--seconds",args.seconds])
    if "itm" in selected:
        binary=fixture("selectio_f103_itm_words.S","itm_words")
        for path in ("native","cmsis-dap"):
            test("itm-"+path,"selectio_itm_test.py",["--usb-path",path,"--binary",binary,"--words",500000])
    if "etm" in selected:
        dest=args.etm_out or (out/"etm")
        ok=run("etm",[*cli,"trace","capture","--elf",ROOT/"prebuilt/golden/f103ze-cdc48.elf","--bit",pair/"probe.bit",
            "--zynq-elf",pair/"application.elf","--swd-khz",10000,"--seconds",1,"--out",dest,"--json-out",out/"etm.json"])
        if ok:
            result=json.loads((out/"etm.json").read_text(encoding="utf8"))
            capture=result["result"]
            window=capture.get("quality",{})
            diag=window.get("diagnostics",{})
            decode=capture.get("summary",{})
            passed=(window.get("requestedWindowComplete") and window.get("captureComplete") and
                    window.get("loss")==0 and not window.get("tailAmbiguous") and
                    all(diag.get(key)==0 for key in ("parserErrors","frameDrops","idelayReadyLosses","writerError")) and
                    decode.get("executed",0)>0 and decode.get("packetIssues")==0)
            summary["cases"][-1]["passed"]=bool(passed)
            summary["etm_record"]=str(dest)
            summary["etm_decode"]=decode
            summary["etm_window"]=window
    summary["passed"]=all(r["passed"] and r.get("restored",True) for r in summary["cases"])
    save()
    return 0 if summary["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
