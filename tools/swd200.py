"""Offline SWD-only SelectIO experiment on XC7Z020."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from run_cm3_sim import DEFAULT_RTL, VIVADO, environment

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "fpga/experiments/swd200"
OUT = ROOT / "build/swd200"
SIM = OUT / "sim"
XBIN = VIVADO / "bin/unwrapped/win64.o"
SNAPSHOT = "swd200_sim"
SUCCESS = re.compile(r"^SWD200_PASS .+", re.MULTILINE)
COST = re.compile(r"^SWD200_COST .+", re.MULTILINE)
FAILURE = re.compile(r"^\s*(?:Fatal|Error)\b.*", re.MULTILINE | re.IGNORECASE)
RATES = (50, 100, 160, 200)
GCC = Path("E:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe")


def run(command, cwd, log, *, env=None):
    with log.open("w", encoding="utf-8") as output:
        return subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=output,
                              stderr=subprocess.STDOUT, check=False).returncode


def checked(command, cwd, log, *, env=None):
    if run(command, cwd, log, env=env):
        raise SystemExit(log.read_text(encoding="utf-8", errors="replace")[-5000:])


def snapshot(model):
    wrapper = ROOT / "fpga/sim"
    encrypted = sorted(model.glob("*.v"))
    verilog = [*encrypted, *sorted(RTL.glob("*.v")), wrapper / "axi3_sram.v",
               wrapper / "cm3_target.sv", VIVADO / "data/verilog/src/glbl.v"]
    bench = RTL / "tb_swd200.sv"
    if not (model / "cortexm3_integration.v").is_file():
        raise SystemExit(f"Missing Cortex-M3 model in {model}")
    digest = hashlib.sha256(str(VIVADO).encode())
    for source in [*verilog, bench, *sorted(model.glob("*.vp"))]:
        digest.update(str(source).encode())
        digest.update(source.read_bytes())
    fingerprint = digest.hexdigest()
    SIM.mkdir(parents=True, exist_ok=True)
    stamp = SIM / "snapshot.sha256"
    if stamp.is_file() and stamp.read_text().strip() == fingerprint:
        return
    stamp.unlink(missing_ok=True)
    env = environment()
    checked([XBIN / "xvlog.exe", "--relax", "-i", model, *verilog],
            SIM, SIM / "compile.log", env=env)
    checked([XBIN / "xvlog.exe", "--sv", bench], SIM, SIM / "compile-bench.log", env=env)
    checked([XBIN / "xelab.exe", "--mt", "2", "-L", "unisims_ver", "-L", "secureip",
             "-s", SNAPSHOT, "tb_swd200", "glbl"], SIM, SIM / "elaborate.log", env=env)
    stamp.write_text(fingerprint + "\n", encoding="ascii")


def simulate(mhz, return_ns, target_ns, ack, data, tap, idle, words, rounds, trace=False, guard=0, banks=False):
    profile = dict(mhz=mhz, return_ns=return_ns, target_ns=target_ns,
                   ack=ack, data=data, tap=tap, idle=idle, words=words, rounds=rounds)
    if guard:
        profile["guard"] = guard
    key = "-".join(f"{name}{value}" for name, value in profile.items()) + ("-banks" if banks else "")
    log = SIM / f"{key}.log"
    command = [XBIN / "xsim.exe", SNAPSHOT, "-runall", "-log", SIM / f"{key}.xsim.log"]
    for name, value in profile.items():
        command += ["-testplusarg", f"{name}={value}"]
    if trace:
        command += ["-testplusarg", "trace"]
    if banks:
        command += ["-testplusarg", "banks"]
    rc = run(command, SIM, log, env=environment())
    output = log.read_text(encoding="utf-8", errors="replace")
    success = SUCCESS.search(output)
    failure = FAILURE.search(output)
    result = dict(profile, passed=rc == 0 and bool(success) and not failure,
                  log=log.name, result=(failure or success).group(0).strip()
                  if failure or success else f"xsim status {rc}")
    print(f"{key} {result['result']}", flush=True)
    if result["passed"]:
        result["cost"] = COST.findall(output)
        if trace:
            print("\n".join(result["cost"]), flush=True)
    return result


def matrix():
    nominal = [simulate(mhz, 0.8, 10.0, 12, 12, 0, 2, 256, 3) for mhz in reversed(RATES)]
    boundary = simulate(200, 4.0, 10.0, 13, 13, 0, 2, 256, 3)
    margin = [simulate(200, delay, 10.0, sample, sample, 0, 2, 32, 2)
              for delay in (0.0, 0.8, 1.6, 2.0, 2.4, 2.8, 3.2, 4.0)
              for sample in (12, 13, 14)]
    core = [simulate(200, 0.8, period, 12, 12, 0, 2, 256, 3)
            for period in (8.0, 12.5, 20.0)]
    report = dict(snapshot=(SIM / "snapshot.sha256").read_text().strip(), nominal=nominal,
                  boundary=boundary, margin=margin, target_clock=core)
    (SIM / "matrix.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    expected_pass = [*nominal, boundary, *core, *(row for row in margin if row["ack"] == 13)]
    return 0 if all(row["passed"] for row in expected_pass) else 1


def build(gcc):
    work = OUT / "fpga"
    work.mkdir(parents=True, exist_ok=True)
    temp = work / "tmp"
    temp.mkdir(exist_ok=True)
    env = environment()
    env.update(TEMP=str(temp), TMP=str(temp))
    checked([VIVADO / "bin/vivado.bat", "-mode", "batch", "-source", RTL / "build.tcl",
             "-log", work / "vivado.log", "-journal", work / "vivado.jou"],
            work, work / "build.log", env=env)
    firmware = ROOT / "firmware/swd200"
    checked([gcc, "-mcpu=cortex-a9", "-marm", "-Os", "-g", "-ffreestanding", "-nostdlib",
             "-Wall", "-Wextra", "-Werror", "-Wl,--build-id=none",
             f"-Wl,-T,{firmware / 'ocm.ld'}", f"-Wl,-Map,{work / 'application.map'}",
             firmware / "start.S", firmware / "clock.c", "-o", work / "application.elf"],
            work, work / "firmware.log")
    from verify_probe_ocm_code import read_ocm_code

    read_ocm_code(work / "application.elf")
    print(f"SWD-only build and routed timing: {work}")
    return 0


def bench_elf(gcc, output, resident):
    """Build the OCM board timing helper for the same GP0 register map."""
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    source = Path("firmware/swd200")
    flags = ["-mcpu=cortex-a9", "-marm", "-O2", "-g", "-ffreestanding", "-nostdlib",
             "-Wall", "-Wextra", "-Werror", "-DSWD200_BOARD_BENCH"]
    if resident:
        flags.append("-DSWD200_RESIDENT")
    subprocess.run([gcc, *flags, "-Wl,--build-id=none", "-T", source / "ocm.ld",
                    source / "start.S", source / "clock.c", source / "f103_bench.c",
                    "-o", output], cwd=ROOT, check=True)
    from verify_probe_ocm_code import read_ocm_code
    read_ocm_code(output)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_subparsers(dest="action", required=True)
    sim = action.add_parser("sim", help="Run Cortex-M3 and AMD primitive simulation")
    sim.add_argument("--rtl", type=Path, default=DEFAULT_RTL)
    sim.add_argument("--mhz", type=int, choices=RATES, default=200)
    sim.add_argument("--return-ns", type=float, default=0.8)
    sim.add_argument("--target-ns", type=float, default=10.0)
    sim.add_argument("--ack", type=int, choices=range(64), default=12)
    sim.add_argument("--data", type=int, choices=range(64), default=12)
    sim.add_argument("--tap", type=int, choices=range(32), default=0)
    sim.add_argument("--idle", type=int, choices=range(1, 16), default=2)
    sim.add_argument("--words", type=int, choices=range(1, 257), default=128)
    sim.add_argument("--rounds", type=int, choices=range(1, 11), default=3)
    sim.add_argument("--trace", action="store_true")
    sim.add_argument("--guard", type=int, choices=range(8), default=0)
    sim.add_argument("--banks", action="store_true")
    scan = action.add_parser("matrix", help="Verify the frequency and return-delay matrix")
    scan.add_argument("--rtl", type=Path, default=DEFAULT_RTL)
    build_args = action.add_parser("build", help="Synthesize, route and build a matching OCM ELF")
    build_args.add_argument("--gcc", type=Path, default=GCC)
    elf_args = action.add_parser("bench-elf", help="Build the Cortex-A9 F103 SRAM timing helper")
    elf_args.add_argument("--gcc", type=Path, default=GCC)
    elf_args.add_argument("--out", type=Path, required=True)
    elf_args.add_argument("--resident", action="store_true")
    args = parser.parse_args()
    if args.action == "build":
        return build(args.gcc.resolve())
    if args.action == "bench-elf":
        return bench_elf(args.gcc, args.out, args.resident)
    snapshot(args.rtl.resolve())
    if args.action == "matrix":
        return matrix()
    return 0 if simulate(args.mhz, args.return_ns, args.target_ns, args.ack, args.data, args.tap,
                         args.idle, args.words, args.rounds, args.trace, args.guard, args.banks)["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
