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
        VIVADO / "data/verilog/src/glbl.v",
    ]
    steps = [
        ("xvlog", ["--sv", *sources]),
        ("xelab", ["-L", "unisims_ver", "-L", "secureip", "-s", "spi_slave", "tb_selectio_spi_slave", "glbl"]),
        ("xsim", ["spi_slave", "-runall"]),
    ]
    for name, options in steps:
        result = subprocess.run(
            [binaries / (name + ".exe"), *options], cwd=out, env=environment(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            errors="replace", timeout=300)
        (out / (name + ".txt")).write_text(result.stdout, encoding="utf-8")
        if result.returncode or (name == "xsim" and "SPI_SLAVE_PASS" not in result.stdout):
            raise SystemExit(result.stdout[-4000:])
    print(next(line for line in result.stdout.splitlines() if line.startswith("SPI_SLAVE_PASS")))


if __name__ == "__main__":
    main()
