"""Verify configurable SWD ACK timing against a delayed target model.

The target changes SWDIO on SWCLK falling edges and can delay its output
transitions.  ACK=WAIT (010) is used for the timing sweep because ACK=OK has a
pull-up-compatible first bit and would hide a late target response.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ROOT / "fpga/rtl/swd_core.v",
    ROOT / "fpga/sim/tb_swd_ack_delay.sv",
]


def run_case(build_dir: Path, *, tco: int, ack_delay: int, turn_extra: int,
             expect_ack: int) -> dict:
    name = f"tco{tco}_ack{ack_delay}_turn{turn_extra}_ack{expect_ack}"
    exe = build_dir / f"{name}.vvp"
    params = {
        "TCO_NS": tco,
        "ACK_DELAY": ack_delay,
        "TURN_EXTRA": turn_extra,
        "EXPECT_ACK": expect_ack,
    }
    cmd = ["iverilog", "-g2012", "-s", "tb_swd_ack_delay"]
    for key, value in params.items():
        cmd += ["-P", f"tb_swd_ack_delay.{key if key != 'TCO_NS' else 'TARGET_TCO_NS'}={value}"]
    cmd += ["-o", str(exe), *(str(p) for p in SOURCES)]
    compile_run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if compile_run.returncode:
        return {"tco": tco, "ack_delay": ack_delay,
                "turn_extra": turn_extra, "expect_ack": expect_ack,
                **params, "passed": False, "compile": False,
                "output": compile_run.stderr[-1000:]}
    sim = subprocess.run(["vvp", str(exe)], cwd=ROOT, capture_output=True,
                         text=True, timeout=10)
    output = sim.stdout + sim.stderr
    return {"tco": tco, "ack_delay": ack_delay,
            "turn_extra": turn_extra, "expect_ack": expect_ack,
            **params, "passed": sim.returncode == 0, "compile": True,
            "output": output[-1000:]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="results/optimization/swd_ack_simulation.json")
    args = parser.parse_args()
    build_dir = ROOT / "build/swd_ack_simulation"
    build_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    # Baseline includes a complete DP read and checks data/parity. The sweep
    # uses WAIT so a late ACK cannot be mistaken for the line pull-up.
    rows.append(run_case(build_dir, tco=1, ack_delay=0, turn_extra=0,
                         expect_ack=1))
    for tco, ack_delay, turn_extra in (
        (8, 0, 0),       # normal margin
        (20, 0, 0),      # deliberately late: wrong ACK
        (20, 1, 0),      # one extended high phase: recovered ACK
    ):
        rows.append(run_case(build_dir, tco=tco, ack_delay=ack_delay,
                             turn_extra=turn_extra, expect_ack=2))

    # In this model a 20 ns target response requires at least one extended
    # high phase; turnaround-only stretching does not fix the ACK bit that was
    # already launched on the first falling edge.
    for row in rows:
        if row["expect_ack"] == 1:
            row["expected"] = True
        elif row["tco"] < 20:
            row["expected"] = True
        else:
            row["expected"] = row["ack_delay"] >= 1
        row["matches_expectation"] = row["passed"] == row["expected"]
        print(json.dumps({k: row[k] for k in (
            "tco", "ack_delay", "turn_extra", "expect_ack", "passed",
            "expected", "matches_expectation")}), flush=True)

    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if not all(row["matches_expectation"] for row in rows):
        raise SystemExit("SWD ACK timing simulation did not match expectations")


if __name__ == "__main__":
    main()
