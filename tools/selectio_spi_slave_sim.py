"""Exercise SelectIO SPI slave reception with Vivado UNISIM pad models."""
import argparse
from pathlib import Path
import subprocess

from run_cm3_sim import ROOT, VIVADO, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    binaries = VIVADO / "bin/unwrapped/win64.o"
    rtl = ROOT / "fpga/rtl"
    sources = [
        rtl / "selectio_clocking.v",
        rtl / "selectio_debug_phy.v",
        rtl / "selectio_spi_slave_rx.v",
        ROOT / "fpga/sim/tb_selectio_spi_slave.sv",
        ROOT / "fpga/sim/tb_selectio_spi_slave_offset.sv",
        VIVADO / "data/verilog/src/glbl.v",
    ]

    def run(name, options, log):
        result = subprocess.run(
            [binaries / (name + ".exe"), *options], cwd=out, env=environment(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            errors="replace", timeout=300)
        (out / log).write_text(result.stdout, encoding="utf-8")
        if result.returncode:
            raise SystemExit(result.stdout[-4000:])
        return result.stdout

    run("xvlog", ["--sv", *sources], "xvlog.txt")
    for suffix, marker in (("", "SPI_SLAVE_PASS"), ("_offset", "SPI_SLAVE_OFFSET_PASS")):
        entry = "spi_slave" + suffix
        run("xelab", ["-L", "unisims_ver", "-L", "secureip", "-s", entry, "tb_selectio_" + entry, "glbl"],
            f"xelab{suffix}.txt")
        output = run("xsim", [entry, "-runall"], f"xsim{suffix}.txt")
        match = next((line for line in output.splitlines() if line.startswith(marker)), None)
        if match is None or "Fatal:" in output:
            raise SystemExit(output[-4000:])
        print(match, flush=True)


if __name__ == "__main__":
    main()
