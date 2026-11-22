"""Confirm selected J7/F103ZE performance cases after a checked JTAG/RAM load."""
import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PYTHON = [sys.executable, "-X", "utf8"]


@dataclass(frozen=True)
class Point:
    name: str
    transport: str
    hclk_mhz: int
    clock_hz: int
    tap: int
    slot: int
    idle: int
    directions: tuple[str, ...] = ()
    rtt: bool = False
    scope: bool = False
    edge_idle: int | None = None


POINTS = (
    Point("DBG-03", "swd", 96, 100_000_000, 8, 25, 2, ("read",), True, True),
    Point("DBG-04", "swd", 128, 100_000_000, 8, 25, 1, ("read", "write", "mixed"), True, True, 0),
    Point("DBG-07", "jtag", 96, 100_000_000, 16, 28, 33, scope=True),
    Point("DBG-08", "jtag", 128, 100_000_000, 16, 28, 29, ("read", "write", "mixed"), True, True, 25),
)


def run(command, log):
    with log.open("xb") as output:
        return subprocess.run([str(value) for value in command], cwd=ROOT, stdout=output,
                              stderr=subprocess.STDOUT).returncode


def memory_command(point, args, out, idle, seconds, rounds, directions):
    return [*PYTHON, TOOLS/"selectio_pipeline_bench.py", "--serial", args.serial,
            "--transport", point.transport, "--clock", point.clock_hz,
            "--tap", point.tap, "--slot", point.slot, "--idle", idle,
            "--bytes", 4032, "--frame", 4096, "--depth", 4, "--seconds", seconds,
            "--rounds", rounds, "--directions", *directions, "--out", out, "--execute"]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def inside_clock_guard(point, args):
    out = args.out
    out.mkdir()
    tests = {}
    if point.edge_idle is not None:
        for idle in (point.idle, point.edge_idle):
            destination = out/f"idle{idle}-short"
            tests[f"idle{idle}-short"] = run(
                memory_command(point, args, destination, idle, 3, 1, ("read", "write")),
                destination.with_suffix(".log"))
            path = destination/"result.json"
            if path.is_file() and read_json(path).get("restored") is not True:
                # The enclosing fixture will restore its own backup before continuing.
                save(out/"summary.json", tests)
                return 1
    if point.directions:
        destination = out/"sram"
        tests["sram"] = run(memory_command(point, args, destination, point.idle, args.seconds,
                                           args.rounds, point.directions), out/"sram.log")
        path = destination/"result.json"
        if path.is_file() and read_json(path).get("restored") is not True:
            save(out/"summary.json", tests)
            return 1
    if point.rtt:
        tests["profile"] = run([*PYTHON, ROOT/"toolbox.py", "selectio", "--serial", args.serial,
                                "profile", "--transport", point.transport, "--tap", point.tap,
                                "--slot", point.slot, "--idle", point.idle], out/"profile.log")
        if tests["profile"] == 0:
            tests["rtt-cdc"] = run([*PYTHON, TOOLS/"benchmark_rtt_forward.py", "--serial", args.serial,
                                    "--transport", point.transport, "--bootstrap-speed-khz", 1000,
                                    "--bit", args.pair/"probe.bit", "--elf", args.pair/"application.elf",
                                    "--speeds", point.clock_hz, "--chunks", 2048, "--seconds", args.seconds,
                                    "--repeats", args.rounds, "--serialized-control",
                                    "--output", out/"rtt-cdc.json"], out/"rtt-cdc.log")
            if (out/"rtt-cdc.json").is_file():
                check = read_json(out/"rtt-cdc.json")
                if not (check.get("restore_match") and check.get("registers_match")):
                    save(out/"summary.json", tests)
                    return 1
    if point.scope:
        tests["hss"] = run([*PYTHON, TOOLS/"selectio_services_accept.py", "--serial", args.serial,
                            "--transport", point.transport, "--clock", point.clock_hz,
                            f"--{point.transport}-slot", point.slot, f"--{point.transport}-idle", point.idle,
                            "--confirm-seconds", args.seconds, "--confirm-rounds", args.rounds,
                            "--out", out/"hss", "--execute"], out/"hss.log")
    save(out/"summary.json", tests)
    return int(any(code for name, code in tests.items() if not name.endswith("-short")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--serial", default="12345678")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--only", action="append", choices=["DBG-01", *(p.name for p in POINTS), "ETM-02"],
                        help="repeat to confirm selected cases")
    parser.add_argument("--worker", choices=[p.name for p in POINTS], help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.pair = args.pair.resolve()
    args.out = args.out.resolve()
    if args.seconds <= 0 or args.rounds < 1:
        parser.error("positive duration and rounds required")
    selected = set(args.only or [point.name for point in POINTS] + ["DBG-01", "ETM-02"])
    if not args.execute:
        print(json.dumps({"operation": "temporary JTAG/RAM load and guarded F103ZE SRAM",
                          "pair": str(args.pair), "out": str(args.out), "serial": args.serial,
                          "points": [asdict(point) for point in POINTS if point.name in selected],
                          "seconds": args.seconds, "rounds": args.rounds,
                          "swd50_historical": "DBG-01" in selected,
                          "etm36_rounds": 3 if "ETM-02" in selected else 0}, indent=2))
        return 0
    if args.worker:
        return inside_clock_guard(next(p for p in POINTS if p.name == args.worker), args)

    manifest = read_json(args.pair / "manifest.json")
    args.out.mkdir()
    load = run([*PYTHON, ROOT/"toolbox.py", "probe-load", "--pair", args.pair,
                "--out", args.out/"load"], args.out/"load.log")
    if load:
        raise RuntimeError(f"Probe load or OCM verification failed: {args.out / 'load.log'}")
    ocm = read_json(args.out / "load/ocm/result.json")
    if not ocm["passed"] or ocm["elf_sha256"] != manifest["hashes"]["application.elf"]:
        raise RuntimeError("Loaded PS image differs from the selected manifest")
    results = {"hashes": manifest["hashes"], "serial": args.serial, "seconds": args.seconds,
               "rounds": args.rounds, "cases": sorted(selected),
               "verified_ocm_bytes": ocm["expected_executable_bytes"], "rows": [], "complete": False}
    clock_guard = [*PYTHON, TOOLS/"selectio_f103_clock_accept.py", "--pair", args.pair,
                   "--serial", args.serial, "--execute"]

    def guard(name, hclk, extra):
        dest = args.out/(name+"-guard")
        rc = run([*clock_guard, "--hclk-mhz", hclk, "--out", dest, *extra], args.out/(name+".log"))
        state_file = dest/"state.json"
        state = read_json(state_file) if state_file.is_file() else {}
        restored = state.get("restored") is True and state.get("probe_hashes") == manifest["hashes"]
        row = {"name": name, "exit": rc, "restored": restored,
               "hclk_dwt_hz": state.get("measured_core_hz"), "error": state.get("error")}
        results["rows"].append(row)
        save(args.out/"summary.json", results)
        print(json.dumps(row), flush=True)
        if not restored:
            raise RuntimeError(f"{name}: target recovery or pair identity unconfirmed; inspect {dest}")

    if "DBG-01" in selected:
        guard("DBG-01-historical", 96, ["--only", "historical", "--historical-clock", 50_000_000,
                                        "--swd-tap", 8, "--swd-slot", 24, "--swd-idle", 0,
                                        "--rtt-cdc-seconds", args.seconds, "--rtt-cdc-rounds", args.rounds])
    for point in POINTS:
        if point.name not in selected:
            continue
        args_for_worker = [*PYTHON, Path(__file__).resolve(), "--pair", args.pair, "--serial", args.serial,
                           "--out", args.out/point.name, "--worker", point.name, "--seconds", args.seconds,
                           "--rounds", args.rounds, "--execute"]
        jtag = ["--enable-jtag"] if point.transport == "jtag" else []
        guard(point.name, point.hclk_mhz, [*jtag, "--command", *args_for_worker])
    if "ETM-02" in selected:
        for repeat in range(1, 4):
            guard(f"ETM-02-36-{repeat}", 72, ["--only", "etm", "--trace-seconds", 1])
    results["complete"] = True
    results["passed"] = all(row["exit"] == 0 for row in results["rows"])
    save(args.out/"summary.json", results)
    return int(not results["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
