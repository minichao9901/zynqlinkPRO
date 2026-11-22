"""Simulate both SelectIO transports on one shared pin bank and one Cortex-M3."""
import argparse
import subprocess
from pathlib import Path

from run_cm3_sim import DEFAULT_RTL, ROOT, VIVADO, environment


def early_swd50_link(source, out):
    """Keep the experimental RTL out of the production source list."""
    rtl = source.read_text(encoding="utf-8")
    changes = (
        ("reg seed_pending = 0, read_seed;", "reg seed_pending = 0, seed_half = 0, read_seed;"),
        ("    wire early_clock = !guarded && (early_single ||",
         """    // At 50 MHz there are two quad words per SWCLK. ACK and D0
    // must use the same quartet phase to capture D0 two words later.
    wire early_half = rate == 0 && ack_sample >= 16 && ack_sample[5:2] == data_sample[5:2];
    wire early_clock = !guarded && (early_single || early_half ||"""),
        ("            seed_pending <= 0;", "            seed_pending <= 0;\n            seed_half <= 0;"),
        ("            if (seed_pending) read_seed <= rx_slots[data_sample[1:0]];",
         """            seed_half <= seed_pending && early_half;
            if ((seed_pending && !early_half) || seed_half)
                read_seed <= rx_slots[data_sample[1:0]];"""),
    )
    for original, replacement in changes:
        if rtl.count(original) != 1:
            raise SystemExit(f"SWD 50 MHz overlay no longer matches {source}: {original!r}")
        rtl = rtl.replace(original, replacement, 1)
    candidate = out / "swd200_link_early_swd50.v"
    candidate.write_text(rtl, encoding="utf-8")
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/selectio-cm3")
    parser.add_argument("--jtag-slot", type=int, default=21)
    parser.add_argument("--swd-slot", type=int, default=16)
    parser.add_argument("--swd-only", action="store_true")
    parser.add_argument("--target-clk-ns",type=float,help="target model HCLK period in ns")
    parser.add_argument("--return-ns",type=float,help="model-only SWDIO return delay in ns")
    parser.add_argument("--wire-budget",action="store_true",help="count 50 MHz pin clocks and gaps in SWD windows")
    parser.add_argument("--services", action="store_true", help="verify the autonomous RTT and sample engines through the live transport")
    parser.add_argument("--sample-ticks",type=int,default=32)
    parser.add_argument("--wiretrace",action="store_true")
    parser.add_argument("--half-rate", action="store_true", help="exercise the 50 MHz profile")
    parser.add_argument("--idle",type=int,default=2)
    parser.add_argument("--jtag-idle",type=int,default=33)
    parser.add_argument("--service-words",type=int,choices=(1,8),default=1)
    parser.add_argument("--meter",action="store_true")
    parser.add_argument("--rtt-window", action="store_true", help="time 8048 verified RTT bytes through the final target RdOff commit")
    parser.add_argument("--rtt-chunk", type=int, choices=(1024,2048), default=2048)
    parser.add_argument("--quad-dma",action="store_true",help="clock the queue AXI and BRAM ports with the SelectIO quad clock")
    parser.add_argument("--early-swd50", action="store_true", help="simulate one early released SWCLK edge after ACK")
    parser.add_argument("--swd50-faults", action="store_true", help="verify ACK, parity and wire ownership against a scripted target")
    parser.add_argument("--swd50-windows", action="store_true", help="measure standard 512-word SRAM and queued RTT through RdOff confirmation")
    parser.add_argument("--variable-clock", type=int, choices=range(32,64), metavar="DIV", help="use adjustable FCLK1 MMCM and exercise divider DIV")
    parser.add_argument("--slice", choices=("full", "jtag", "swd"), default="full")
    parser.add_argument("--jtag-only", action="store_true")
    args = parser.parse_args()
    if args.variable_clock is not None and (args.services or args.quad_dma):
        parser.error("--variable-clock uses the A-layout shared pad simulation")
    if args.slice=="jtag" and not args.jtag_only or args.slice=="swd" and not args.swd_only:
        parser.error("exercise the transport included in this slice")
    if args.jtag_only and (args.swd_only or args.services or args.wire_budget):
        parser.error("--jtag-only is a separate pad benchmark")
    if (args.early_swd50 or ((args.swd50_faults or args.swd50_windows) and args.variable_clock is None)) and (
        not args.half_rate or not args.swd_only or args.services or args.quad_dma
    ):
        parser.error("SWD 50 MHz experiments require --half-rate --swd-only and the reference queue layout")
    if args.swd50_windows and (args.swd50_faults or not args.wire_budget):
        parser.error("--swd50-windows requires --wire-budget and runs separately from --swd50-faults")
    if args.quad_dma and args.services:
        parser.error("--quad-dma is available for the queue and shared-pad simulation")
    if args.rtt_window and not args.services:
        parser.error("--rtt-window requires --services")
    if args.target_clk_ns is not None and args.target_clk_ns<=0:
        parser.error("--target-clk-ns must be positive")
    if args.return_ns is not None and args.return_ns<0:
        parser.error("--return-ns cannot be negative")
    if args.wire_budget and (not args.swd_only or (not args.half_rate and args.variable_clock is None) or args.rtt_window):
        parser.error("--wire-budget requires --swd-only and an explicit SWD timing profile")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    exe = VIVADO / "bin/unwrapped/win64.o"

    def run(name, arguments, log):
        result = subprocess.run([exe / (name + ".exe"), *map(str, arguments)], cwd=out,
                                env=environment(), capture_output=True, text=True, errors="replace",
                                timeout=1200 if name=="xsim" else 300)
        output = result.stdout + result.stderr
        (out / log).write_text(output, encoding="utf-8")
        if result.returncode:
            raise SystemExit(output[-3500:])
        return output

    dut = ROOT / "fpga/rtl"
    sim = ROOT / "fpga/sim"
    link = dut / "swd200_link.v"
    if args.early_swd50:
        link = early_swd50_link(link, out)
    if not args.swd50_faults:
        run("xvlog", ["--relax", "-i", DEFAULT_RTL, *sorted(DEFAULT_RTL.glob("*.v")), sim / "axi3_sram.v",
                      VIVADO / "data/verilog/src/glbl.v"], "model.log")
    if args.swd50_faults:
        sources = [dut / "selectio_clocking.v", dut / "selectio_debug_phy.v",
                   dut / "swd200_segment.v", dut / "swd200_batch.v", link, sim / "tb_swd50_edges.sv",
                   VIVADO / "data/verilog/src/glbl.v"]
        top = "tb_swd50_edges"
    elif args.services:
        run("xvlog",["--relax",*sorted(dut.glob("*.v"))],"dut.log")
        sources=[sim/"xpm_memory_tdpram.sv", sim/"cm3_target.sv",
                 sim/"jtag_dp_model.sv", sim/"tb_cm3_jtag.sv", sim/"tb_selectio_services.sv"]
        top="tb_selectio_services"
    else:
        sources=[*sorted(dut.glob("selectio_*.v")), *sorted(dut.glob("jtag200_*.v")),
                 *sorted(dut.glob("swd200_*.v")), dut/"jtag_core.v", dut/"jtag_shift.v",
                 dut/"dap_transfer_block_engine.v",sim/"cm3_target.sv",sim/"jtag_dp_model.sv",sim/"tb_selectio_debug.sv"]
        top="tb_selectio_debug"
    if args.early_swd50:
        sources = [link if path == dut / "swd200_link.v" else path for path in sources]
    run("xvlog",["--sv","-i",sim,*sources],"compile.log")
    generic=["--generic_top","QUAD_DMA=1"] if args.quad_dma else []
    if args.variable_clock is not None:
        generic+=["--generic_top","VARIABLE_CLOCK=1"]
    if args.slice!="full":
        generic+=["--generic_top",f"SELECTIO_SLICE={('full','jtag','swd').index(args.slice)}"]
    run("xelab", ["--mt","2","-L","unisims_ver","-L","secureip",*generic,"-s","fusion",top,"glbl"],"elab.log")
    switches=["-testplusarg",f"idle={args.idle}","-testplusarg",f"jidle={args.jtag_idle}"]
    if args.services:
        for opt in ("bypass","clk_ns=7.5",f"service_ticks={args.sample_ticks}"):
            switches.extend(["-testplusarg",opt])
        if args.swd_only: switches.extend(["-testplusarg","swd"])
    elif args.swd_only: switches.extend(["-testplusarg","swd_only"])
    if args.target_clk_ns is not None or args.services:
        target_ns=args.target_clk_ns if args.target_clk_ns is not None else 20.833
        switches.extend(["-testplusarg",f"target_clk_ns={target_ns}"])
    if args.return_ns is not None:switches.extend(["-testplusarg",f"return_ns={args.return_ns}"])
    if args.early_swd50: switches.extend(["-testplusarg", "early_swd50"])
    if args.swd50_windows: switches.extend(["-testplusarg", "swd50_windows"])
    if args.wire_budget:switches.extend(["-testplusarg","wire_budget"])
    if args.wire_budget and args.services:switches.extend(["-testplusarg","benchmark"])
    switches.extend(["-testplusarg",f"service_words={args.service_words}"])
    if args.meter:switches.extend(["-testplusarg","meter"])
    if args.rtt_window:switches.extend(["-testplusarg","rtt_window","-testplusarg",f"rtt_chunk={args.rtt_chunk}"])
    if args.variable_clock is not None:
        switches.extend(["-testplusarg",f"fclk1_ns={args.variable_clock*0.625}"])
    if args.jtag_only: switches.extend(["-testplusarg","jtag_only"])
    if args.half_rate: switches.extend(["-testplusarg","half_rate"])
    if args.wiretrace: switches.extend(["-testplusarg","wiretrace"])
    output = run("xsim", ["fusion", "-runall", "-testplusarg", f"jslot={args.jtag_slot}",
                          "-testplusarg", f"sslot={args.swd_slot}", *switches], "run.log")
    print(output[-1600:])
    expected="SELECTIO_SERVICES_PASS" if args.services else "SELECTIO_PASS"
    if args.wire_budget and args.services:expected="PASS SWD wire budgets and payloads"
    if args.jtag_only: expected = "SELECTIO_JTAG_ONLY_PASS"
    if args.swd50_faults: expected = "SWD50_EDGES_PASS"
    if args.swd50_windows: expected = "SWD50_WINDOWS_PASS"
    return 0 if expected in output and "Fatal:" not in output else 1


if __name__ == "__main__":
    raise SystemExit(main())
