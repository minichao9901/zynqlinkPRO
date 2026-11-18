"""Run the SelectIO block pipeline against RTL Hazard3 DTM/DM/SBA and MCU SRAM."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from jtag200 import OUT, ROOT, RTL, VIVADO, environment, run_logged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hazard3-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=OUT / "hazard3-sim")
    sweep = parser.add_mutually_exclusive_group()
    sweep.add_argument('--fine', action='store_true', help='Sweep 200 MHz around the DMI BUSY boundary')
    sweep.add_argument('--hundred', action='store_true', help='Sweep the two-TCK, 100 MHz mode and both TX advances')
    args = parser.parse_args()
    root = args.hazard3_root.resolve()
    work = args.out.resolve()
    work.mkdir(exist_ok=False, parents=True)
    hazard = root / "third_party/hazard3/hdl"
    manifests = ["hazard3.f", "debug/dm/hazard3_dm.f", "debug/dtm/hazard3_jtag_dtm.f"]
    sources = []
    for manifest in manifests:
        name = hazard / manifest
        for line in name.read_text().splitlines():
            if line.startswith("file "):
                source = (name.parent / line[5:]).resolve()
                if source not in sources:
                    sources.append(source)

    rtl_names = ["axi_pkg", "core_axi", "ahb_bram", "ahb_axi_bridge", "axi_qspi_route",
                 "axi_memory", "uart", "spi_master", "peripherals", "mcu_top"]
    sources += [root / "rtl" / f"{name}.sv" for name in rtl_names]
    copies = []
    for index, source in enumerate(sources):
        body = source.read_text(encoding="utf-8-sig")
        if source.name == "mcu_top.sv":
            body, matched = re.subn(r"(\.dbg_sbus_addr\s*\()sbus_addr(\))",
                r"\g<1>sbus_addr[31:17]==15'h82 ? {15'h4000,sbus_addr[16:0]} : sbus_addr\2",
                body)
            if matched != 1:
                raise RuntimeError("Hazard3 MCU SBA hookup changed; inspect fixture alias translation")
        scratch = work / f"{index:02d}-{source.name}"
        scratch.write_text(chr(96) + "timescale 1ns/1ps\n" + body, encoding="utf8")
        copies.append(scratch)

    behavior = ROOT / "fpga/sim"
    original = ROOT / "fpga/rtl"
    exe = VIVADO / "bin/unwrapped/win64.o"
    env = environment()
    run_logged([exe / "xvlog.exe", "--sv", "--relax", "-i", hazard, "-d", "J200_TEST_HAZARD3",
                *copies, *sorted(RTL.glob("*.v")),
                *(original / file for file in ("jtag_core.v","jtag_shift.v","dap_transfer_block_engine.v")),
                behavior / "jtag_dtm_model.sv", behavior / "jtag200_hazard_target.sv",
                behavior / "tb_jtag200.sv", VIVADO / "data/verilog/src/glbl.v"],
               work, work / "compile.log", env)
    run_logged([exe / "xelab.exe", "-L", "unisims_ver", "-L", "secureip", "-s", "jtag200_hazard",
                "tb_jtag200", "glbl"], work, work / "elab.log", env)
    pattern = "fine" if args.fine else "hundred" if args.hundred else None
    plusargs = ["-testplusarg", pattern] if pattern else []
    run_logged([exe / "xsim.exe", "jtag200_hazard", "-runall", *plusargs],
               work, work / "sim.log", env)
    text = (work / "sim.log").read_text(encoding="utf8", errors="replace")
    valid = [line for line in text.splitlines() if "J200_HAZARD3_" in line]
    print("\n".join(valid) or text[-4000:])
    if "JTAG200_SIM_PASS" not in text or "J200_HAZARD3_PASS" not in text or "Fatal:" in text:
        raise SystemExit(f"Hardware model simulation did not pass: {work / 'sim.log'}")
    meta = {
        "hazard3_source_revision": subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
        "hazard3_upstream_revision": subprocess.check_output(["git","rev-parse","HEAD"],cwd=hazard,text=True).strip(),
        "source_sha256": {path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        "target_hz":80000000,
        "sba_alias":"0x01040000–0x0105ffff maps to 0x80000000–0x8001ffff SRAM in the test copy of mcu_top",
        "outcomes":valid,
    }
    (work / "result.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf8")


if __name__ == "__main__":
    main()
