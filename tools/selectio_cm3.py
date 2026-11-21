"""Simulate both SelectIO transports on one shared pin bank and one Cortex-M3."""
import argparse
import subprocess
from pathlib import Path

from run_cm3_sim import DEFAULT_RTL, ROOT, VIVADO, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/selectio-cm3")
    parser.add_argument("--jtag-slot", type=int, default=21)
    parser.add_argument("--swd-slot", type=int, default=16)
    parser.add_argument("--swd-only", action="store_true")
    parser.add_argument("--services", action="store_true", help="verify the autonomous RTT and sample engines through the live transport")
    parser.add_argument("--sample-ticks",type=int,default=32)
    parser.add_argument("--wiretrace",action="store_true")
    parser.add_argument("--half-rate", action="store_true", help="exercise the 50 MHz profile")
    parser.add_argument("--idle",type=int,default=2)
    parser.add_argument("--jtag-idle",type=int,default=33)
    parser.add_argument("--service-words",type=int,choices=(1,8),default=1)
    parser.add_argument("--meter",action="store_true")
    parser.add_argument("--rtt-window", action="store_true", help="time four verified RTT packets through the final target RdOff commit")
    args = parser.parse_args()
    if args.rtt_window and not args.services:
        parser.error("--rtt-window requires --services")
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
    run("xvlog", ["--relax", "-i", DEFAULT_RTL, *sorted(DEFAULT_RTL.glob("*.v")), sim / "axi3_sram.v",
                  VIVADO / "data/verilog/src/glbl.v"], "model.log")
    if args.services:
        run("xvlog",["--relax",*sorted(dut.glob("*.v"))],"dut.log")
        sources=[sim/"xpm_memory_tdpram.sv", sim/"cm3_target.sv",
                 sim/"jtag_dp_model.sv", sim/"tb_cm3_jtag.sv", sim/"tb_selectio_services.sv"]
        top="tb_selectio_services"
    else:
        sources=[*sorted(dut.glob("selectio_*.v")), *sorted(dut.glob("jtag200_*.v")),
                 *sorted(dut.glob("swd200_*.v")), dut/"jtag_core.v", dut/"jtag_shift.v",
                 dut/"dap_transfer_block_engine.v",sim/"cm3_target.sv",sim/"jtag_dp_model.sv",sim/"tb_selectio_debug.sv"]
        top="tb_selectio_debug"
    run("xvlog",["--sv","-i",sim,*sources],"compile.log")
    run("xelab", ["--mt","2","-L","unisims_ver","-L","secureip","-s","fusion",top,"glbl"],"elab.log")
    switches=["-testplusarg",f"idle={args.idle}","-testplusarg",f"jidle={args.jtag_idle}"]
    if args.services:
        for opt in ("bypass","clk_ns=7.5","target_clk_ns=20.833",f"service_ticks={args.sample_ticks}"):
            switches.extend(["-testplusarg",opt])
        if args.swd_only: switches.extend(["-testplusarg","swd"])
    elif args.swd_only: switches.extend(["-testplusarg","swd_only"])
    switches.extend(["-testplusarg",f"service_words={args.service_words}"])
    if args.meter:switches.extend(["-testplusarg","meter"])
    if args.rtt_window:switches.extend(["-testplusarg","rtt_window"])
    if args.half_rate: switches.extend(["-testplusarg","half_rate"])
    if args.wiretrace: switches.extend(["-testplusarg","wiretrace"])
    output = run("xsim", ["fusion", "-runall", "-testplusarg", f"jslot={args.jtag_slot}",
                          "-testplusarg", f"sslot={args.swd_slot}", *switches], "run.log")
    print(output[-1600:])
    return 0 if ("SELECTIO_SERVICES_PASS" if args.services else "SELECTIO_PASS") in output and "Fatal:" not in output else 1


if __name__ == "__main__":
    raise SystemExit(main())
