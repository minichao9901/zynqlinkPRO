"""Check SelectIO SPI reception, the AUX receive ring and the firmware CDC pump."""
import argparse
from pathlib import Path
import re
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


def run_pump(out):
    tests = ROOT / "tools/tests"
    firmware = ROOT / "firmware/xusbps_daplink_dma"
    mock_headers = out / "include"
    mock_headers.mkdir()
    for name in ("DAP_config.h", "DAP.h", "xusbps.h", "xtime_l.h", "xil_types.h"):
        (mock_headers / name).write_text('#include "probe_host_platform.h"\n', encoding="ascii")
    source = (firmware / "xusbps_intr_example.c").read_text(encoding="utf-8")
    handler = re.search(r"^static void XUsbPs_EpCdcEventHandler\([^;]*?\)\s*\{.*?^}",
                        source, re.MULTILINE | re.DOTALL)
    if handler is None:
        raise SystemExit("CDC endpoint callback not found")
    (mock_headers / "cdc_event_under_test.h").write_text(handler.group() + "\n", encoding="utf-8")

    compiler = ["gcc", "-std=gnu11", "-O2", "-DDAP_SELECTIO=1", "-DDAP_SELECTIO_VARIABLE=1",
                "-DDAP_SELECTIO_SLICE=0"]
    for directory in (mock_headers, firmware, firmware / "DAP/Include", tests):
        compiler.extend(("-I", directory))
    cases = (
        ("pump", "selectio_spi_cdc_pump_test.c",
         ("SPI_CDC_PUMP_PASS", "SPI_CDC_PUMP_REARM_PASS", "SPI_CDC_PUMP_COUNTER_PASS")),
        ("cdc_event", "selectio_cdc_event_test.c", ("CDC_EVENT_PASS",)),
    )
    for name, filename, markers in cases:
        image = out / (name + ".exe")
        with (out / (name + "_gcc.txt")).open("w", encoding="utf-8") as log:
            subprocess.run([*compiler, tests / filename, "-o", image], stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=90)
        result = subprocess.run([image], capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        (out / (name + ".txt")).write_text(output, encoding="utf-8")
        if result.returncode or not all(marker in output for marker in markers):
            raise SystemExit(output[-4000:])
        print(output, end="", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ring-only", action="store_true",
                      help="run the digital AUX receive-ring case with Icarus Verilog")
    mode.add_argument("--pump-only", action="store_true",
                      help="run the firmware CDC pump model with a host GCC compiler")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rtl = ROOT / "fpga/rtl"
    if args.ring_only:
        run_ring(out, rtl)
        return
    if args.pump_only:
        run_pump(out)
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
    cases = (("", "", "SPI_SLAVE_PASS", []),
             ("_offset", "_offset", "SPI_SLAVE_OFFSET_PASS", []),
             ("_filter", "", "SPI_SLAVE_PASS", ["-generic_top", "FILTER=1"]))
    for suffix, top_suffix, marker, generics in cases:
        entry = "spi_slave" + suffix
        run("xelab", ["-L", "unisims_ver", "-L", "secureip", *generics,
                      "-s", entry, "tb_selectio_spi_slave" + top_suffix, "glbl"],
            f"xelab{suffix}.txt")
        output = run("xsim", [entry, "-runall"], f"xsim{suffix}.txt")
        match = next((line for line in output.splitlines() if line.startswith(marker)), None)
        if match is None or "Fatal:" in output or (generics and "glitches=1" not in match):
            raise SystemExit(output[-4000:])
        print(match, flush=True)


if __name__ == "__main__":
    main()
