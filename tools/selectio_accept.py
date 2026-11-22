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
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--board",choices=("f103ze",))
    mode.add_argument("--review",type=Path,nargs="+",help="review saved summary.json reports without accessing hardware")
    ap.add_argument("--pair",type=Path,default=ROOT/"prebuilt/selectio-j7-fusion")
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--out",type=Path)
    ap.add_argument("--etm-out",type=Path,help="new native ETM record directory")
    ap.add_argument("--seconds",type=float,default=60)
    ap.add_argument("--rounds",type=int,default=3,help="SRAM, RTT and HSS confirmation rounds per transport")
    ap.add_argument("--only",action="append",choices=(*SUITES,"usb-ddr","spi-cdc"))
    ap.add_argument("--clock",type=int,choices=(50000000,73000000,100000000),default=100000000,
                    help="debug, memory, running RTT, scope and combo clock in Hz")
    ap.add_argument("--frame",type=int,choices=(4096,16384),default=4096,
                    help="negotiated SRAM frame size and guarded fixture extent")
    ap.add_argument("--schedule",choices=("grouped","sliding"),default="sliding")
    ap.add_argument("--rtt-ring-bytes",type=int,choices=(1024,8192),default=1024,
                    help="target producer ring size for running RTT and combo measurements")
    ap.add_argument("--rtt-chunk",type=int,choices=(1024,2048),help="maximum bytes per target-side RTT commit in standalone mode")
    ap.add_argument("--execute",action="store_true")
    args=ap.parse_args(argv)
    if args.review:
        if args.execute:ap.error("--review is offline")
        verdicts=[]
        for supplied in args.review:
            path=supplied/"summary.json" if supplied.is_dir() else supplied
            summary=json.loads(path.read_text(encoding="utf8"))
            if summary.get("board")!="f103ze" or "probe.bit" not in summary.get("hashes",{}):
                ap.error(f"not a SelectIO board report: {path}")
            cases=summary.get("cases",[])
            failed=[c["name"] for c in cases if not c.get("passed") or c.get("restored") is False]
            verdicts.append(dict(report=str(path.resolve()),bit=summary["hashes"]["probe.bit"],
                elf=summary["hashes"]["application.elf"],suites=summary["suites"],cases=len(cases),
                failed=failed,complete="passed" in summary,passed=bool(cases and summary.get("passed") and not failed)))
        print(json.dumps(verdicts,indent=2))
        return 0 if all(v["passed"] for v in verdicts) else 1
    if args.seconds<=0 or args.rounds<=0:ap.error("positive durations and round counts required")
    pair=args.pair.resolve()
    manifest=pair/"manifest.json"
    identity=json.loads(manifest.read_text(encoding="utf8")) if manifest.is_file() else {}
    selected=args.only or (*SUITES, *(("spi-cdc",) if identity.get("spi_slave_cdc") else ()))
    out=(args.out or ROOT/"build"/("selectio-accept-"+datetime.now().strftime("%Y%m%d-%H%M%S"))).resolve()
    summary=dict(board=args.board,operation="HS3 JTAG/RAM, guarded F103ZE SRAM",suites=selected,
                 serial=args.serial,seconds=args.seconds,rounds=args.rounds,pair=str(pair),out=str(out),
                 debug_service_hz=args.clock,memory_frame=args.frame,schedule=args.schedule,
                 rtt_ring_bytes=args.rtt_ring_bytes,rtt_chunk=args.rtt_chunk,cases=[])
    if not args.execute:
        print(json.dumps(summary,indent=2));return 0
    if not identity:
        ap.error("the selected pair must supply a manifest")
    if "spi-cdc" in selected and not identity.get("spi_slave_cdc"):
        ap.error("the selected pair does not provide SPI slave CDC")
    profiles=identity if args.clock==100000000 else identity.get(f"profiles_{args.clock//1000000}mhz")
    if profiles is None:ap.error("selected pair does not supply sampling profiles for the requested clock")
    if (args.frame==16384 or "usb-ddr" in selected) and identity.get("max_native_frame",4096)<16384:
        ap.error("selected pair does not advertise negotiated 16 KiB frames")
    for name in ("probe.bit","application.elf","ps7_init.tcl"):
        if hashlib.sha256((pair/name).read_bytes()).hexdigest()!=identity["hashes"][name]:
            raise ValueError(f"artifact hash differs for {name}")
    out.mkdir(parents=True,exist_ok=False)
    summary["hashes"]=identity["hashes"]
    py=[sys.executable,"-X","utf8"]
    cli=[*py,ROOT/"toolbox.py"]
    def save():
        (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8")
    def run(name,cmd,guard=False,guard_size=4096):
        start=time.monotonic()
        state=out/(name+"-guard")
        if guard:
            cmd=[*py,ROOT/"tools/selectio_f103_fixture.py","--serial",args.serial,"--out",state,
                 "--size",guard_size,"--execute","--",*cmd]
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
    def test(name,script,options,guard_size=4096):
        return run(name,[*py,ROOT/"tools"/script,"--serial",args.serial,"--out",out/name,*options,"--execute"],True,guard_size)
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
    if "usb-ddr" in selected:
        run("usb-ddr",[*py,ROOT/"tools/selectio_transport_bench.py","--serial",args.serial,
                       "--seconds",args.seconds,"--schedule",args.schedule,"--out",out/"usb-ddr"])
    if "switch" in selected:
        test("switch","selectio_mode_switch_test.py",["--swd-slot",profiles["swd"]["slot"],
             "--jtag-slot",profiles["jtag"]["slot"],"--swd-idle",profiles["swd"]["idle"],
             "--jtag-idle",profiles["jtag"]["idle"],"--clock",args.clock,"--rounds",64])
        if identity.get("native_stream_lease_seconds"):
            test("host-loss","selectio_abandon_test.py",[])
    producer=None
    if "rtt" in selected or "combo" in selected:
        producer=fixture("probe_rtt_ram.S","producer",["-Wa,--defsym,FIXTURE_BASE=0x20008000",
                             "-Wa,--defsym,RTT_FROM_DESCRIPTOR=1"])
    for transport in ("swd","jtag"):
        cfg=profiles[transport]
        common=["--transport",transport,"--slot",cfg["slot"]]
        if "debug" in selected:test("debug-"+transport,"selectio_debug_test.py",[*common,"--clock",args.clock,"--idle",cfg["idle"]])
        if "memory" in selected:
            test("memory-"+transport,"selectio_pipeline_bench.py",[*common,"--tap",cfg["tap"],"--idle",cfg.get("bulk_idle",cfg["idle"]),
                 "--clock",args.clock,"--frame",args.frame,"--bytes",args.frame-64,"--schedule",args.schedule,
                 "--depth",4,"--seconds",args.seconds,"--rounds",args.rounds],args.frame)
        for service in ("rtt","combo"):
            chunk=["--rtt-chunk",args.rtt_chunk] if service=="rtt" and args.rtt_chunk else []
            if service in selected:
                repeats=args.rounds if service=="rtt" else 1
                for i in range(repeats):
                    label=service+"-"+transport
                    if repeats>1:label+=f"-{i+1}"
                    test(label,"selectio_running_test.py",
                         [*common,*chunk,"--clock",args.clock,"--idle",cfg["idle"],"--seconds",args.seconds,"--service",service,
                          "--binary",producer,"--ring-bytes",args.rtt_ring_bytes],16384 if args.rtt_ring_bytes==8192 else 4096)
    if "scope" in selected:
        for transport in ("swd","jtag"):
            test("services-"+transport,"selectio_services_accept.py",
                 ["--transport",transport,"--swd-slot",profiles["swd"]["slot"],"--jtag-slot",profiles["jtag"]["slot"],
                  "--swd-idle",profiles["swd"]["idle"],"--jtag-idle",profiles["jtag"]["idle"],"--clock",args.clock,
                  "--confirm-seconds",args.seconds,"--confirm-rounds",args.rounds])
    if "wire" in selected:
        # External Manchester uses the F103 TAP as a timed source. Give
        # it its own guarded SWJ handoff, as for the independent PWM source.
        pad_cases=["spi-mode0",*(f"spi-pad-mode{i}" for i in range(4)),
                   "uart-tx-remote","uart-rx-remote","manchester50-remote","manchester100-tdi-pad"]
        selected_cases=[arg for name in pad_cases for arg in ("--only",name)]
        test("wire","selectio_wire_test.py",["--extended","--seconds",args.seconds,*selected_cases])
        test("external-manchester","selectio_wire_test.py",["--extended","--only","manchester100-sparse-remote",
             "--seconds",args.seconds])
        test("spi-target","selectio_spi_target_test.py",["--seconds",args.seconds])
        if int(identity["bit_features"],16)&0x4000:
            test("manchester-bursts","selectio_manchester_stress.py",["--seconds",args.seconds])
    if "cdc" in selected:
        cdc_options=["--binary",fixture("selectio_f103_uart_echo.S","echo"),"--swd-slot",identity["swd"]["slot"]]
        test("cdc","selectio_cdc_test.py",cdc_options)
        test("cdc-rtt-scope","selectio_cdc_test.py",[*cdc_options,"--combo"])
    if "cdc" in selected and identity.get("cdc_bypass_qualification"):
        test("cdc-100m","selectio_cdc_wire_test.py",["--seconds",args.seconds])
    if "spi-cdc" in selected:
        for spi_mode in range(4):
            test(f"spi-cdc-mode{spi_mode}","selectio_spi_cdc_test.py",
                 ["--mode",spi_mode,"--f103-source",16384,"--seconds",10])
    if "itm" in selected:
        binary=fixture("selectio_f103_itm_words.S","itm_words")
        for path in ("native","cmsis-dap"):
            test("itm-"+path,"selectio_itm_test.py",["--usb-path",path,"--binary",binary,"--words",500000])
    if "etm" in selected:
        dest=args.etm_out or (out/"etm")
        ok=run("etm",[*cli,"trace","capture","--elf",ROOT/"prebuilt/golden/f103ze-cdc48.elf","--bit",pair/"probe.bit",
            "--zynq-elf",pair/"application.elf","--swd-khz",10000,"--running-window","--seconds",1,"--out",dest,"--json-out",out/"etm.json"])
        if ok:
            result=json.loads((out/"etm.json").read_text(encoding="utf8"))
            capture=result["result"]
            window=capture.get("quality",{})
            diag=window.get("diagnostics",{})
            decode=capture.get("summary",{})
            proof=json.loads((dest/"acceptance.json").read_text(encoding="utf8"))
            framing=json.loads((dest/"ddr/demux/result.json").read_text(encoding="utf8"))
            capture_row=summary["cases"][-1]
            verified=run("etm-verify",[*cli,"trace","verify","--record",dest,"--require-decoded"])
            tail=window.get("tailBytes")
            passed=(verified and proof.get("restored") and proof.get("fpb_restored") and
                    window.get("synced") and window.get("ended") and abs(window.get("hardwareSeconds",0)-1)<=.002 and
                    isinstance(tail,int) and 0<=tail<16 and window.get("formatterBytes",0)%16==tail and
                    framing.get("trailingFrameBytes")==tail and window.get("requestedWindowComplete") and window.get("captureComplete") and
                    window.get("loss")==0 and
                    all(diag.get(key)==0 for key in ("parserErrors","frameDrops","idelayReadyLosses","writerError")) and
                    decode.get("executed",0)>0 and decode.get("packetIssues")==0)
            capture_row["passed"]=bool(passed)
            capture_row["restored"]=bool(proof.get("restored") and proof.get("fpb_restored"))
            summary["etm_record"]=str(dest)
            summary["etm_decode"]=decode
            summary["etm_window"]=window
    summary["passed"]=all(r["passed"] and r.get("restored",True) for r in summary["cases"])
    save()
    return 0 if summary["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
