"""Simulate, build and exercise the isolated J7 JTAG PHY."""
import argparse
import json
import random
import re
import struct
import subprocess
import sys
from pathlib import Path

from run_cm3_sim import VIVADO, environment

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "fpga/experiments/jtag200"
OUT = ROOT / "build/jtag200"
PROFILES = {
    "50": (0, 4, 50_000_000),
    "66.667": (1, 3, 66_666_667),
    "80": (2, 2, 80_000_000),
    "100": (3, 2, 100_000_000),
    "160": (4, 1, 160_000_000),
    "200": (5, 1, 200_000_000),
    "66.667-block": (6, 2, 66_666_667),
}
LEAD = 8
TAIL = 64


def bits(value, count):
    return [(value >> bit) & 1 for bit in range(count)]


def waveform(tms, tdi, half_slots, tdi_advance=0):
    """Encode low/high half periods and pad out the receive pipeline."""
    if not tms or len(tms) != len(tdi) or not 1 <= half_slots <= 4:
        raise ValueError("Expected a nonempty pair of JTAG vectors and 1–4 slots")
    if not 0 <= tdi_advance < half_slots:
        raise ValueError("TDI advance must leave at least one slot of hold time")
    idle = 0b110
    slots = [idle] * LEAD
    for mode, data in zip(tms, tdi):
        level = mode << 1 | data << 2
        slots.extend([level] * half_slots)
        slots.extend([level | 1] * half_slots)
    slots.extend([idle] * (TAIL + (-len(slots) % 8)))
    if len(slots) > 4096:
        raise ValueError("Scan exceeds the 512-word waveform buffer")

    # Compensate TDI/TCK skew independently. Nominal capture remains on TCK rise.
    if tdi_advance:
        tdi_levels = slots[tdi_advance:] + [idle] * tdi_advance
        slots = [(slot & 3) | (data & 4) for slot, data in zip(slots, tdi_levels)]
    words = []
    for start in range(0, len(slots), 8):
        word = 0
        for slot, value in enumerate(slots[start:start + 8]):
            for lane in range(3):
                word |= (value >> lane & 1) << (lane * 8 + slot)
        words.append(word)
    words[-1] |= 1 << 24  # Terminator travels in the TX BRAM, with the waveform.
    return words


def tap_vectors():
    """Reset, explicitly select HPM IDCODE IR, then move into Shift-DR."""
    navigation = [1] * 6 + [0] + [1, 1, 0, 0] + [0, 0, 0, 0, 1] + [1, 0] + [1, 0, 0]
    ir_data = [0] * 11 + bits(1, 5) + [0] * 5
    return navigation, ir_data


def vectors(kind):
    rng = random.Random(200)
    if kind == "loopback":
        data = [rng.randrange(2) for _ in range(479)]
        return [0] * len(data), data, 0, data
    nav, header = tap_vectors()
    if kind == "idcode":
        return nav + [0] * 31 + [1, 1, 0], header + [0] * 34, len(nav), None

    data = [rng.randrange(2) for _ in range(257)]
    dr = data + [0] * 32
    mode = [0] * (len(dr) - 1) + [1, 1, 0]
    expect = bits(0x1000563D, 32) + data
    return nav + mode, header + dr + [0, 0], len(nav), expect


def decode(raw, half_slots, start, count, offset):
    """Offset is in serializer slots relative to the outgoing TCK rising edge."""
    positions = [LEAD + half_slots + 2 * half_slots * i + offset for i in range(start, start + count)]
    if min(positions) < 0 or max(positions) >= 8 * len(raw):
        return None
    return [raw[pos // 8] >> (pos % 8) & 1 for pos in positions]


def alignment(raw, half_slots, start, expected):
    return [offset for offset in range(-8, TAIL)
            if decode(raw, half_slots, start, len(expected), offset) == expected]


def run_logged(command, cwd, log, env=None):
    with log.open("w", encoding="utf8") as stream:
        result = subprocess.run([str(part) for part in command], cwd=cwd,
                                stdout=stream, stderr=subprocess.STDOUT, env=env)
    if result.returncode:
        print(log.read_text(encoding="utf8", errors="replace")[-4500:])
        raise SystemExit(f"{command[0]} failed: {log}")


def simulate():
    work = OUT / "sim"
    work.mkdir(parents=True, exist_ok=True)
    modes, data, _, _ = vectors("model")
    for key, (index, half, _) in PROFILES.items():
        words = waveform(modes, data, half, tdi_advance=int(half == 2))
        (work / f"tx{index}.mem").write_text(
            f"{len(words):06x}\n" + "".join(f"{word:06x}\n" for word in words), encoding="ascii")
    (work / "pins.mem").write_text(
        "".join(f"{mode << 1 | value:x}\n" for mode, value in zip(modes, data)), encoding="ascii")

    exe = VIVADO / "bin/unwrapped/win64.o"
    source = ROOT / "fpga/sim"
    env = environment()
    run_logged([exe / "xvlog.exe", "--sv", *sorted(RTL.glob("*.v")),
                *(ROOT / "fpga/rtl" / file for file in ("jtag_core.v", "jtag_shift.v", "dap_transfer_block_engine.v")),
                source / "jtag_dtm_model.sv", source / "riscv_sba_model.sv", source / "jtag_dp_model.sv",
                source / "tb_jtag200.sv",
                VIVADO / "data/verilog/src/glbl.v"], work, work / "compile.log", env)
    run_logged([exe / "xelab.exe", "-L", "unisims_ver", "-L", "secureip", "-s", "jtag200_sim",
                "tb_jtag200", "glbl"], work, work / "elab.log", env)
    run_logged([exe / "xsim.exe", "jtag200_sim", "-runall"], work, work / "sim.log", env)
    log = (work / "sim.log").read_text(encoding="utf8", errors="replace")
    if "JTAG200_SIM_PASS" not in log or re.search(r"^\s*(?:Fatal|Error|FAIL)\b", log, re.M | re.I):
        raise SystemExit(log[-3500:])

    _, _, start, expected = vectors("model")
    for key, (index, half, _) in PROFILES.items():
        raw = bytes.fromhex((work / f"rx{index}.hex").read_text(encoding="ascii"))
        offsets = alignment(raw, half, start, expected)
        if not offsets:
            raise SystemExit(f"{key} MHz: IDCODE/PRBS did not round-trip: {raw.hex()}")
        print(f"PASS {key} MHz: TCK edges/period, TMS/TDI, IDCODE and {len(expected)-32} PRBS bits; RX offsets {offsets}")
    for line in log.splitlines():
        if line.startswith(("J200_PIPELINE_PASS", "J200_ARM_PASS", "J200_ARM_BREAKDOWN")):
            print(line)
    print(f"Evidence: {work / 'sim.log'}")


def build_firmware(gcc):
    work = OUT / "firmware"
    work.mkdir(parents=True, exist_ok=True)
    src = ROOT / "firmware/jtag200"
    run_logged([gcc, "-mcpu=cortex-a9", "-marm", "-Os", "-g", "-ffreestanding", "-nostdlib",
                "-Wall", "-Wextra", "-Werror", "-Wl,--build-id=none",
                f"-Wl,-T,{src / 'ocm.ld'}", f"-Wl,-Map,{work / 'application.map'}",
                src / "start.S", src / "clock.c", "-o", work / "application.elf"],
               ROOT, work / "build.log")
    from verify_probe_ocm_code import read_ocm_code
    read_ocm_code(work / "application.elf")
    print(work / "application.elf")


def pair_files(pair):
    import hashlib

    manifest = json.loads((pair / "manifest.json").read_text(encoding="utf8"))
    for name in ("probe.bit", "application.elf", "ps7_init.tcl"):
        path = pair / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"][name]:
            raise ValueError(f"JTAG200 pair hash mismatch: {path}")
    return manifest


def load_pair(args):
    """RAM load after the operator has identified and released the probe."""
    import hashlib

    from probe_flash import Session
    from verify_probe_ocm_code import read_ocm_code
    from zynq_memory import PhysicalMemory

    pair = args.pair.resolve()
    manifest = pair_files(pair)
    elf = pair / "application.elf"
    blob, _, sections = read_ocm_code(elf)
    if not args.execute:
        print(f"RAM load {pair} to cable {args.cable_serial}; pair hashes verified. Use --execute for hardware.")
        return
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    session = Session(out, args.sdk, args.server, cable_serial=args.cable_serial)
    memory = PhysicalMemory(session, cable_serial=args.cable_serial)
    select = ' && jtag_cable_serial == "' + args.cable_serial + '"'
    bit = (pair / "probe.bit").as_posix()
    init = (pair / "ps7_init.tcl").as_posix()
    image = out / "live-code.bin"
    end = max(section[3] + section[5] for section in sections)
    report = {"pair": manifest["sha256"], "cable_serial": args.cable_serial, "passed": False}
    sys.path.insert(0, str(ROOT / "etm-service/tools"))
    from probe_ownership import Ownership
    lease = Ownership()
    try:
        session.run(f'''targets -set -filter {{name =~ "APU"{select}}}
rst -system
after 1000
set ready 0
for {{set attempt 0}} {{$attempt < 50}} {{incr attempt}} {{
    if {{![catch {{
        targets -set -filter {{name =~ "APU"{select}}}
        mrd -force -value 0xf8007080
    }} reason]}} {{set ready 1; break}}
    after 100
}}
if {{!$ready}} {{error "APU did not recover after reset: $reason"}}
source {{{init}}}
ps7_init
targets -set -filter {{name =~ "xc7z020"{select}}}
fpga -f {{{bit}}}
after 300
targets -set -filter {{name =~ "APU"{select}}}
ps7_post_config
targets -set -filter {{name =~ "ARM Cortex-A9 MPCore #0*"{select}}}
rst -processor
configparams force-mem-access 1
dow {{{elf.as_posix()}}}
mwr -force 0x0002ff00 0
con''')
        memory.run(SCAN_TCL.read_text(encoding="ascii") + f'''
wait_mask 0x2ff00 0xffffffff 0x4a323030
if {{[read_word 0x2ff14] != 0 || [read_word 0x40000000] != 0x4a323030}} {{
    error "Experimental bit/ELF did not initialize"
}}
wait_mask 0x40000004 0x1f 5
physrd -force -bin -file {{{image.as_posix()}}} 0 {(end + 3)//4}''')
        live = image.read_bytes()
        for section in sections:
            addr, offset, size = section[3:6]
            if live[addr:addr + size] != blob[offset:offset + size]:
                raise RuntimeError("Physical MEM-AP0 OCM readback differs from candidate")
        report.update(passed=True, live_code_sha256=hashlib.sha256(live).hexdigest(),
                      verified_code_bytes=sum(section[5] for section in sections))
    finally:
        lease.close()
        (out / "load.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(f"Running JTAG200 pair verified at {args.cable_serial}: {out / 'load.json'}")



def scan(args):
    """Execute only after an explicit command against the selected cable."""
    from probe_flash import Session
    from zynq_memory import PhysicalMemory

    profile, half, hz = PROFILES[args.mhz]
    tms, tdi, start, expected = vectors(args.kind)
    if args.kind == "idcode":
        if args.idcode is None:
            raise ValueError("--idcode is required for a target IDCODE check")
        expected = bits(args.idcode, 32)
    words = waveform(tms, tdi, half, tdi_advance=args.tdi_advance)
    if not args.execute:
        print(f"{args.kind}: cable {args.cable_serial}, nominal TCK {hz} Hz, "
              f"{len(tms)} pulses, {len(words)} words, tap {args.taps}, TDI advance {args.tdi_advance}. "
              "Use --execute for hardware.")
        return

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tx = out / "tx.bin"
    tx.write_bytes(struct.pack(f"<{len(words)}I", *words))
    session = Session(out, args.sdk, args.server, cable_serial=args.cable_serial)
    memory = PhysicalMemory(session, cable_serial=args.cable_serial)
    results = []
    try:
        body = SCAN_TCL.read_text(encoding="ascii")
        body += f"\nprofile {profile} {args.taps} {hz} {half}\n"
        for round_no in range(args.repeats):
            rx = out / f"rx-{round_no+1}.bin"
            body += "scan_jtag {" + tx.as_posix() + "} {" + rx.as_posix() + f"}} {len(words)}\n"
        # A single XSCT client for the entire attempt.
        sys.path.insert(0, str(ROOT / "etm-service/tools"))
        from probe_ownership import Ownership
        lease = Ownership()
        try:
            memory.run(body)
        finally:
            lease.close()
        common = None
        for round_no in range(args.repeats):
            frame = (out / f"rx-{round_no+1}.bin").read_bytes()
            raw_words = struct.unpack(f"<{len(words)}I", frame)
            offsets = alignment(raw_words, half, start, expected)
            common = set(offsets) if common is None else common.intersection(offsets)
            results.append({"round": round_no + 1, "matching_slot_offsets": offsets})
        print(f"Matching offsets common to all {args.repeats} rounds: {sorted(common)}")
        if not common:
            raise RuntimeError("No common capture offset at the selected tap")
    finally:
        (out / "result.json").write_text(json.dumps({
            "nominal_tck_hz": hz, "target_kind": args.kind, "io_delay_tap": args.taps,
            "tdi_advance_slots": args.tdi_advance,
            "cable_serial": args.cable_serial, "rounds": results,
        }, indent=2) + "\n", encoding="utf8")


SCAN_TCL = ROOT / "fpga/experiments/jtag200/scan_ap0.tcl"


def hardware_args(parser):
    parser.add_argument("--cable-serial", required=True)
    parser.add_argument("--sdk", type=Path, default=Path("E:/Xilinx/SDK/2018.3"))
    parser.add_argument("--server", default="tcp:127.0.0.1:3121")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sim", help="Run offline XSim with actual SelectIO primitive models")
    firmware = sub.add_parser("firmware", help="Build the Zynq OCM clock-control ELF")
    firmware.add_argument("--gcc", type=Path, default=Path(
        "E:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe"))
    loader = sub.add_parser("load", help="RAM load after verifying the intended probe is idle")
    loader.add_argument("--pair", type=Path, required=True)
    hardware_args(loader)
    capture = sub.add_parser("scan", help="Use the already loaded pair; no target memory or flash write")
    capture.add_argument("--mhz", choices=PROFILES, required=True)
    capture.add_argument("--taps", type=int, choices=range(32), default=0, metavar="0..31")
    capture.add_argument("--kind", choices=["loopback", "idcode"], required=True)
    capture.add_argument("--tdi-advance", type=int, choices=range(4), default=0, metavar="0..3",
                         help="Advance TDI by serializer slots, less than one TCK half-period")
    capture.add_argument("--idcode", type=lambda value: int(value, 0))
    capture.add_argument("--repeats", type=int, choices=range(1, 101), default=3, metavar="1..100")
    hardware_args(capture)
    args = parser.parse_args()
    if args.command == "sim":
        simulate()
    elif args.command == "firmware":
        build_firmware(args.gcc)
    elif args.command == "load":
        load_pair(args)
    else:
        scan(args)


if __name__ == "__main__":
    main()
