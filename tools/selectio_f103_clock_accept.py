"""Qualify SWD SRAM, running RTT and ETM with a fixed F103ZE HCLK and SRAM-only execution."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from benchmark_rtt_forward import core_read, core_write
from f103_ram_image import plan
from run_f103_clock_fixture import APB1ENR, CFGR, CR, FLASH, hsi, restore as restore_clocks, wait_bits
from selectio_f103_fixture import APB2ENR, DHCSR, MAPR, ROOT, SWJ_MASK, low_link, save

BASE, SIZE = 0x20000000, 1024
WORK_BASE, WORK_SIZE = BASE+0x8000, 16384
VTOR, DCRDR, DEMCR = 0xe000ed08, 0xe000edf8, 0xe000edfc
DWT_CTRL, CYCCNT = 0xe0001000, 0xe0001004
TARGET = ROOT/"prebuilt/targets/f103ze-etm-clock-loop/fw.elf"
CLOCKS = {"CR": CR, "CFGR": CFGR, "APB1ENR": APB1ENR, "FLASH_ACR": FLASH}


def clocks(mem):
    return {name: mem.word(address) for name,address in CLOCKS.items()}


def set_hclk(mem,saved,mhz):
    if mhz==48:
        return
    mem.write_word(FLASH,(saved["FLASH_ACR"] & ~7)|2)
    mem.write_word(APB1ENR,saved["APB1ENR"] & ~(1<<23))
    hsi(mem)
    mem.write_word(CR,mem.word(CR) & ~(1<<24))
    wait_bits(mem,CR,1<<25,0)
    # HSE8, HPRE /1, APB1 /4, APB2 /2, ADC /8. Keep MCO unchanged.
    mask=15|(15<<4)|(7<<8)|(7<<11)|(3<<14)|(63<<16)
    cfg=(saved["CFGR"] & ~mask)|(5<<8)|(4<<11)|(3<<14)|(1<<16)|((mhz//8-2)<<18)
    mem.write_word(CFGR,cfg)
    mem.write_word(CR,mem.word(CR)|(1<<16)|(1<<24))
    wait_bits(mem,CR,1<<25,1<<25)
    mem.write_word(CFGR,cfg|2)
    if wait_bits(mem,CFGR,12,8) != cfg|10:
        raise RuntimeError("PLL or bus divider readback differs")


def recover(folder,state):
    backup=(folder/"original-sram.bin").read_bytes()
    if len(backup)!=state.get("backup_bytes",SIZE) or hashlib.sha256(backup).hexdigest()!=state["sram_sha256"]:
        raise RuntimeError("invalid recovery bytes")
    work=None
    if "work_sha256" in state:
        work=(folder/"original-work.bin").read_bytes()
        if len(work)!=WORK_SIZE or hashlib.sha256(work).hexdigest()!=state["work_sha256"]:
            raise RuntimeError("invalid work buffer backup")
    with low_link(state["serial"]) as mem:
        mem.write_word(DHCSR,0xa05f0003)
        wait_bits(mem,DHCSR,1<<17,1<<17)
        if clocks(mem)!=state["clocks"]:
            restore_clocks(mem,state["clocks"])
        if clocks(mem)!=state["clocks"]:
            raise RuntimeError("clock recovery failed; core held")
        if "mapr" in state:
            mem.write_word(APB2ENR,state["apb2"]|1)
            mem.write_word(MAPR,state["mapr"]|0x02000000)
            if mem.word(MAPR)&~SWJ_MASK!=state["mapr"]:
                raise RuntimeError("AFIO recovery failed; core held")
        if "apb2" in state:
            mem.write_word(APB2ENR,state["apb2"])
            if mem.word(APB2ENR)!=state["apb2"]:
                raise RuntimeError("APB2 recovery failed; core held")
        mem.write(BASE,backup)
        if work is not None:
            mem.write(WORK_BASE,work)
            if mem.read(WORK_BASE,WORK_SIZE)!=work or [mem.word(WORK_BASE-4),mem.word(WORK_BASE+WORK_SIZE)]!=state["work_guards"]:
                raise RuntimeError("work buffer or guard recovery failed")
        mem.write_word(VTOR,state["vtor"])
        if "dwt" in state:
            mem.write_word(DWT_CTRL,state["dwt"][0])
            mem.write_word(CYCCNT,state["dwt"][1])
            if [mem.word(DWT_CTRL),mem.word(CYCCNT)]!=state["dwt"]:
                raise RuntimeError("DWT recovery failed")
        mem.write_word(DEMCR,state["demcr"])
        for reg in [*range(13),14,17,18,20,16,15]:
            core_write(mem,reg,state["regs"][str(reg)])
        if any(core_read(mem,int(k))!=v for k,v in state["regs"].items()):
            raise RuntimeError("core register recovery failed")
        mem.write_word(DCRDR,state["dcrdr"])
        if (mem.read(BASE,len(backup))!=backup or mem.word(VTOR)!=state["vtor"] or
            mem.word(DEMCR)!=state["demcr"] or mem.word(DCRDR)!=state["dcrdr"]):
            raise RuntimeError("SRAM or debug register recovery failed")
        mem.write_word(DHCSR,0xa05f0000|(state["dhcsr"]&0x2f))
        final=mem.word(DHCSR)
        if (final^state["dhcsr"])&0x2002f:
            raise RuntimeError("target run/halt recovery failed")
        state.update(restored=True,final_dhcsr=hex(final))
    save(folder/"state.json",state)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--pair",type=Path,default=ROOT/"prebuilt/selectio-efficiency")
    ap.add_argument("--hclk-mhz",type=int,choices=(48,64,72,96,128),default=128)
    ap.add_argument("--only",choices=("memory","rtt","etm","historical"),action="append")
    ap.add_argument("--trace-seconds",type=float,default=0.1)
    ap.add_argument("--seconds",type=float,default=60,help="seconds per directional SRAM window or running RTT capture")
    ap.add_argument("--rounds",type=int,default=3,help="windows per SRAM direction")
    ap.add_argument("--rtt-cdc-seconds",type=float,default=3)
    ap.add_argument("--rtt-cdc-rounds",type=int,default=2)
    ap.add_argument("--rtt-cdc-check-handoff",action="store_true")
    ap.add_argument("--swd-slot",type=int,choices=range(64),default=22)
    ap.add_argument("--swd-idle",type=int,choices=range(16),default=0)
    ap.add_argument("--swd-tap",type=int,choices=range(32),default=8)
    ap.add_argument("--historical-clock",type=int,default=50000000,help="requested SWD Hz for the CMSIS-DAP / CDC comparison")
    ap.add_argument("--historical-stage",choices=("both","sram","rtt"),default="both")
    ap.add_argument("--memory-page-aligned",action="store_true")
    ap.add_argument("--memory-bytes",type=int,help="override the native SRAM block size for a geometry comparison")
    ap.add_argument("--rtt-queue",action="store_true")
    ap.add_argument("--gpio-speed",type=int,choices=(1,2,3),default=3)
    ap.add_argument("--etm-taps",help="D0,D1,D2,D3,CLK taps 0..31, applied through HS3 and restored after the window")
    ap.add_argument("--hs3-serial",default="210299008529")
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--restore",action="store_true")
    ap.add_argument("--enable-jtag",action="store_true",help="temporarily enable full JTAG for a guarded child")
    ap.add_argument("--command",nargs=argparse.REMAINDER,help="run one child with the verified HCLK and halted SRAM guard")
    args=ap.parse_args()
    if args.command == [] or (args.command and args.only) or (args.enable_jtag and not args.command):
        ap.error("--command requires a child and is separate from --only; --enable-jtag requires --command")
    folder=args.out.resolve()
    if not args.execute:
        print(f"SRAM-only F103ZE loop, HCLK {args.hclk_mhz} MHz, TRACECLK {args.hclk_mhz/2:g} MHz");return
    if args.restore:
        state=json.loads((folder/"state.json").read_text("utf8"))
        if state.get("restored"):ap.error("fixture already restored")
        recover(folder,state);return
    if (not 0<args.trace_seconds<=2 or args.seconds<=0 or args.rounds<1 or
        args.rtt_cdc_seconds<=0 or args.rtt_cdc_rounds<1):ap.error("invalid window length or count")
    suites=["command"] if args.command else args.only or ["memory","rtt","etm"]
    needs_halt=any(s in suites for s in ("memory","rtt","historical","command"))
    backup_bytes=20480 if any(s in suites for s in ("historical","command")) else SIZE
    pair=args.pair.resolve()
    manifest=json.loads((pair/"manifest.json").read_text("utf8"))
    for name,sha in manifest["hashes"].items():
        if hashlib.sha256((pair/name).read_bytes()).hexdigest()!=sha:raise RuntimeError("probe artifact mismatch: "+name)
    taps=None
    if "etm" in suites:
        from etm_lane_delay import LaneDelay,payload
        from probe_flash import Session
        from zynq_memory import PhysicalMemory
        default_taps=manifest.get("f103ze_etm64",{}).get("taps") if args.hclk_mhz==128 else None
        taps=[int(v) for v in args.etm_taps.split(",")] if args.etm_taps else default_taps
        if taps is not None:payload(True,taps)
    image=plan(TARGET)
    if image["stack"]!=BASE+SIZE or any(not BASE<=a<=a+len(b)<=BASE+SIZE for a,b in image["payloads"]):
        raise RuntimeError("ELF extends outside the backed-up SRAM")
    folder.mkdir(parents=True,exist_ok=False)
    state=dict(serial=args.serial,requested_mhz=args.hclk_mhz,restored=False,passed=False,
               suites=suites,probe_hashes=manifest["hashes"],target_elf_sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest())
    def run(name,command):
        with (folder/(name+".log")).open("xb") as stream:
            subprocess.run(list(map(str,command)),cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
    saved=False;lane=None;prior_taps=None
    try:
        with low_link(args.serial) as mem:
            state.update(clocks=clocks(mem),dhcsr=mem.word(DHCSR))
            if state["clocks"]["CFGR"]!=0x51040a:raise RuntimeError("expected CDC48 clock profile")
            mem.write_word(DHCSR,0xa05f0003)
            try:
                wait_bits(mem,DHCSR,1<<17,1<<17)
                state.update(vtor=mem.word(VTOR),dcrdr=mem.word(DCRDR),demcr=mem.word(DEMCR))
                state["regs"]={str(i):core_read(mem,i) for i in [*range(19),20]}
                if state["regs"]["16"]&511:raise RuntimeError("halted in an exception; use a thread-mode window")
                backup=mem.read(BASE,backup_bytes)
                if backup!=mem.read(BASE,backup_bytes):raise RuntimeError("unstable SRAM backup")
                (folder/"original-sram.bin").write_bytes(backup)
                state.update(sram_sha256=hashlib.sha256(backup).hexdigest(),backup_bytes=backup_bytes)
                if needs_halt:
                    work=mem.read(WORK_BASE,WORK_SIZE)
                    if work!=mem.read(WORK_BASE,WORK_SIZE):raise RuntimeError("unstable work buffer backup")
                    (folder/"original-work.bin").write_bytes(work)
                    state.update(work_sha256=hashlib.sha256(work).hexdigest(),
                                 work_guards=[mem.word(WORK_BASE-4),mem.word(WORK_BASE+WORK_SIZE)])
                save(folder/"state.json",state);saved=True
            finally:
                if not saved:
                    if "dcrdr" in state:mem.write_word(DCRDR,state["dcrdr"])
                    mem.write_word(DHCSR,0xa05f0000|(state["dhcsr"]&0x2f))
            for addr,data in image["payloads"]:
                mem.write(addr,data)
                if mem.read(addr,len(data))!=data:raise RuntimeError("SRAM code differs")
            mem.write_word(DEMCR,state["demcr"]|(1<<24))
            state["dwt"]=[mem.word(DWT_CTRL),mem.word(CYCCNT)];save(folder/"state.json",state)
            mem.write_word(DWT_CTRL,state["dwt"][0]|1)
            mem.write_word(VTOR,BASE)
            core_write(mem,20,1);core_write(mem,17,image["stack"])
            core_write(mem,16,0x01000000);core_write(mem,15,image["entry"])
            set_hclk(mem,state["clocks"],args.hclk_mhz)
            cfgr=mem.word(CFGR)
            if cfgr&0x300fc!=0x10008 or 8*min(16,2+((cfgr>>18)&15))!=args.hclk_mhz:
                raise RuntimeError("unexpected HCLK source")
            for sym,val in (("loop_count",0),("g_sysclk_hz",args.hclk_mhz*1000000),("g_clock_err",0)):
                mem.write_word(image["symbols"][sym],val)
            if (core_read(mem,15)&~1)!=image["entry"]&~1 or core_read(mem,20)!=1 or mem.word(VTOR)!=BASE:
                raise RuntimeError("SRAM entry context was not applied")
            mem.write_word(DHCSR,0xa05f0001)
            def sample():
                before=time.perf_counter();cycles=mem.word(CYCCNT)
                return cycles,(before+time.perf_counter())/2
            a,t0=sample();time.sleep(.2);b,t1=sample()
            hz=((b-a)&0xffffffff)/(t1-t0)
            state.update(rcc_cfgr=hex(cfgr),measured_core_hz=hz,trace_hz_from_hclk=args.hclk_mhz*500000,
                         loop_iterations=mem.word(image["symbols"]["loop_count"]))
            save(folder/"state.json",state)
            if not state["loop_iterations"] or abs(hz/(args.hclk_mhz*1e6)-1)>.03:
                mem.write_word(DHCSR,0xa05f0003);wait_bits(mem,DHCSR,1<<17,1<<17)
                state["failed_core"]={str(i):hex(core_read(mem,i)) for i in (0,1,3,4,5,13,14,15,16,20)}
                state["fault_regs"]={hex(a):hex(mem.word(a)) for a in (0xe000ed24,0xe000ed28,0xe000ed2c)}
                raise RuntimeError("DWT or SRAM workload check failed")
            if needs_halt:
                mem.write_word(DHCSR,0xa05f0003);wait_bits(mem,DHCSR,1<<17,1<<17)
            if args.enable_jtag:
                state["apb2"]=mem.word(APB2ENR)
                save(folder/"state.json",state)
                mem.write_word(APB2ENR,state["apb2"]|1)
                state["mapr"]=mem.word(MAPR)&~SWJ_MASK
                save(folder/"state.json",state)
                mem.write_word(MAPR,state["mapr"])
        py=[sys.executable,"-X","utf8"]
        if args.command:
            run("command",args.command)
        if "memory" in suites:
            size=args.memory_bytes or (15360 if args.memory_page_aligned else 16320)
            address=WORK_BASE if args.memory_page_aligned else WORK_BASE+32
            run("memory",[*py,ROOT/"tools/selectio_pipeline_bench.py","--serial",args.serial,"--transport","swd",
                "--clock",50000000,"--tap",8,"--slot",args.swd_slot,"--idle",0,"--frame",16384,"--address",hex(address),"--bytes",size,
                "--depth",4,"--directions","read","write","--seconds",args.seconds,"--rounds",args.rounds,"--out",folder/"memory","--execute"])
        if "rtt" in suites:
            run("compile-producer",["arm-none-eabi-gcc","-mcpu=cortex-m3","-mthumb","-nostdlib","-Wl,--build-id=none",
                "-Wl,-Ttext=0x20008000","-Wl,-e,producer","-Wa,--defsym,FIXTURE_BASE=0x20008000","-Wa,--defsym,RTT_FROM_DESCRIPTOR=1",
                ROOT/"firmware/target/probe_rtt_ram.S","-o",folder/"producer.elf"])
            run("extract-producer",["arm-none-eabi-objcopy","-O","binary","-j",".text",folder/"producer.elf",folder/"producer.bin"])
            run("rtt",[*py,ROOT/"tools/selectio_running_test.py","--serial",args.serial,"--transport","swd","--slot",args.swd_slot,
                "--clock",50000000,"--idle",0,"--seconds",args.seconds,"--service","rtt","--binary",folder/"producer.bin",
                "--ring-bytes",8192,*(["--rtt-queue"] if args.rtt_queue else ["--rtt-chunk",2048]),
                "--out",folder/"rtt","--execute"])
        if "historical" in suites:
            common=["--serial",args.serial,"--transport","swd","--bootstrap-speed-khz",1000,"--bit",pair/"probe.bit","--elf",pair/"application.elf"]
            cli=[*py,ROOT/"toolbox.py","selectio","--serial",args.serial]
            run("profile",[*cli,"profile","--transport","swd","--tap",args.swd_tap,"--slot",args.swd_slot,"--idle",args.swd_idle])
            if args.historical_stage!="rtt":
                run("cmsis-peak",[*py,ROOT/"tools/h743_peak.py",*common,"--speed-hz",args.historical_clock,
                    "--address","0x20008000","--words",512,"--depth",32,"--loops",256,"--repeats",3,
                    "--observe-link","--output",folder/"cmsis-peak.json"])
            if args.historical_stage!="sram":
                run("com-before",[*cli,"com","status"])
                bound=json.loads((folder/"com-before.log").read_text("utf8"))["bound"]
                if bound not in (0,1):raise RuntimeError("unexpected CDC binding")
                try:
                    if bound:run("com-rtt",[*cli,"com","release"])
                    run("rtt-cdc",[*py,ROOT/"tools/benchmark_rtt_forward.py",*common,"--serialized-control",
                        "--speeds",args.historical_clock,"--chunks",2048,"--seconds",args.rtt_cdc_seconds,
                        "--repeats",args.rtt_cdc_rounds,*(["--check-dap-handoff"] if args.rtt_cdc_check_handoff else []),
                        "--output",folder/"rtt-cdc.json"])
                finally:
                    if bound:run("com-restore",[*cli,"com","bind"])
        if "etm" in suites:
            if taps is not None:
                tap_dir=folder/"lane";tap_dir.mkdir()
                lane=LaneDelay(PhysicalMemory(Session(tap_dir,Path("E:/Xilinx/SDK/2018.3"),"tcp:127.0.0.1:3121",
                    cable_serial=args.hs3_serial)))
                prior_taps=lane.snapshot()
                state["original_taps"]=prior_taps;save(folder/"state.json",state)
                state["active_taps"]=lane.configure(True,taps)["after"];save(folder/"state.json",state)
            if needs_halt:
                with low_link(args.serial) as mem:
                    pc=core_read(mem,15)&~1
                    if not mem.word(DHCSR)&(1<<17) or not BASE<=pc<BASE+len(image["payloads"][0][1]):
                        raise RuntimeError("SRAM loop context not restored")
                    mem.write_word(DHCSR,0xa05f0001)
            run("capture",[*py,ROOT/"toolbox.py","trace","capture",
                "--ram-image","--running-window","--transport","ddr","--elf",str(TARGET),
                "--bit",pair/"probe.bit","--zynq-elf",pair/"application.elf","--json-out",folder/"etm.json",
                "--swd-khz","1000","--gpio-speed",args.gpio_speed,"--seconds",args.trace_seconds,"--out",folder/"record"])
            run("verify",[*py,ROOT/"toolbox.py","trace","verify","--record",folder/"record","--require-decoded"])
            quality=json.loads((folder/"record/acceptance.json").read_text("utf8"))
            q=quality["quality"];diag=q["diagnostics"]
            summary=json.loads((folder/"etm.json").read_text("utf8"))["result"]["summary"]
            functions=summary["functions"]
            outside=sum(n for name,n in functions.items() if name not in ("trace_loop","trace_even","trace_odd"))
            imbalance=abs(functions.get("trace_even",0)-functions.get("trace_odd",0))
            state.update(decoded_outside_workload=outside,alternating_path_imbalance=imbalance)
            if (outside or imbalance>6 or summary.get("unknownExecution") or
                summary.get("packetIssues") or summary.get("gaps",2)>1 or not functions.get("trace_even")):
                raise RuntimeError("decoded execution differs from the running SRAM loop")
            if not (quality["restored"] and quality["fpb_restored"] and q["captureComplete"] and
                    q["requestedWindowComplete"] and q["synced"] and q["ended"] and q["loss"]==0 and
                    abs(q["hardwareSeconds"]-args.trace_seconds)<.002 and
                    all(diag[k]==0 for k in ("parserErrors","frameDrops","idelayReadyLosses","writerError"))):
                raise RuntimeError("ETM data quality or cleanup failed")
        state["passed"]=True
    except BaseException as error:
        state["error"]=str(error);raise
    finally:
        save(folder/"state.json",state)
        try:
            if prior_taps is not None:
                state["restored_taps"]=lane.configure(prior_taps["enabled"],prior_taps["taps"])["after"]
        finally:
            if saved:recover(folder,state)

if __name__=="__main__":main()
