"""Exercise SelectIO SPI reception at the pads and the AUX receive ring."""
import argparse
from pathlib import Path
import subprocess

from run_cm3_sim import ROOT, VIVADO, environment


def run_ring(out, rtl):
    modules = (
        "selectio_aux_regs", "selectio_command_bridge", "selectio_spi_slave_rx",
        "selectio_spi", "selectio_uart_rx", "selectio_uart_tx",
        "selectio_manchester_rx", "selectio_manchester_fast",
    )
    top = "tb_selectio_spi_slave_ring"
    image = out / "spi_slave_ring.vvp"
    sources = [rtl / (name + ".v") for name in modules]
    sources.append(ROOT / "fpga/sim" / (top + ".sv"))
    with (out / "iverilog.txt").open("w", encoding="utf-8") as log:
        subprocess.run(["iverilog", "-g2012", "-s", top, "-o", image, *sources],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
    result = subprocess.run(["vvp", image], capture_output=True, text=True, timeout=300)
    output = result.stdout + result.stderr
    (out / "ring.txt").write_text(output, encoding="utf-8")
    if result.returncode or not any(line.startswith("SPI_SLAVE_RING_PASS")
                                    for line in output.splitlines()):
        raise SystemExit(output[-4000:])
    print(output, end="", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ring-only", action="store_true",
                        help="run the digital AUX receive-ring case with Icarus Verilog")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rtl = ROOT / "fpga/rtl"
    if args.ring_only:
        run_ring(out, rtl)
        return
    binaries = VIVADO / "bin/unwrapped/win64.o"
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
