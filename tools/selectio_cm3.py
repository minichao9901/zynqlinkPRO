"""Simulate both SelectIO transports on one shared pin bank and one Cortex-M3."""
import argparse
import subprocess
from pathlib import Path

from run_cm3_sim import DEFAULT_RTL, ROOT, VIVADO, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/selectio-cm3")
    parser.add_argument("--jtag-slot", type=int, default=21)
    parser.add_argument("--swd-slot", type=int, default=12)
    parser.add_argument("--swd-only", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    exe = VIVADO / "bin/unwrapped/win64.o"

    def run(name, arguments, log):
        result = subprocess.run([exe / (name + ".exe"), *map(str, arguments)], cwd=out,
                                env=environment(), capture_output=True, text=True, errors="replace", timeout=300)
        output = result.stdout + result.stderr
        (out / log).write_text(output, encoding="utf-8")
        if result.returncode:
            raise SystemExit(output[-3500:])
        return output

    dut = ROOT / "fpga/rtl"
    sim = ROOT / "fpga/sim"
    run("xvlog", ["--relax", "-i", DEFAULT_RTL, *sorted(DEFAULT_RTL.glob("*.v")), sim / "axi3_sram.v",
                  VIVADO / "data/verilog/src/glbl.v"], "model.log")
    run("xvlog", ["--sv", *sorted(dut.glob("selectio_*.v")), *sorted(dut.glob("jtag200_*.v")),
                  *sorted(dut.glob("swd200_*.v")), dut / "jtag_core.v", dut / "jtag_shift.v",
                  dut / "dap_transfer_block_engine.v", sim / "cm3_target.sv", sim / "jtag_dp_model.sv",
                  sim / "tb_selectio_debug.sv"], "compile.log")
    run("xelab", ["--mt", "2", "-L", "unisims_ver", "-L", "secureip", "-s", "fusion",
                  "tb_selectio_debug", "glbl"], "elab.log")
    switches = ["-testplusarg", "swd_only"] if args.swd_only else []
    output = run("xsim", ["fusion", "-runall", "-testplusarg", f"jslot={args.jtag_slot}",
                          "-testplusarg", f"sslot={args.swd_slot}", *switches], "run.log")
    print(output[-1600:])
    return 0 if "SELECTIO_PASS" in output and "Fatal:" not in output else 1


if __name__ == "__main__":
    raise SystemExit(main())
