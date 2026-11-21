"""Compare directional SRAM queue, PS and end-to-end throughput with the wire budget."""
import argparse
import json
from pathlib import Path
from statistics import median


def summarize(report, legacy_idle=None, legacy_hz=None):
    port = report["transport"]
    if port not in ("swd", "jtag"):
        raise ValueError("expected an SWD or JTAG SRAM benchmark")
    idle = report.get("idle", legacy_idle)
    if idle is None:
        raise ValueError("this legacy report needs --legacy-idle")
    if not report.get("passed") or not report.get("restored"):
        raise ValueError("benchmark or SRAM restoration did not pass")
    rows = {}
    for window in report["windows"]:
        direction = window["direction"]
        if direction not in ("read", "write"):
            continue
        clock = window.get("clock", {})
        hz = clock.get("wire_hz", legacy_hz)
        if not hz:
            raise ValueError("this legacy report needs --legacy-hz")
        costs = window.get("probe_delta", window["probe"])
        index = int(direction == "write")
        payload = costs[direction + "_bytes"]
        queue = payload / costs["queue_s"][index] / 1e6
        ps = payload / costs["probe_s"][index] / 1e6
        host = window["payload_bytes"] / window["wall_seconds"] / 1e6
        limit = 4 * hz / ((46 if port == "swd" else 43) + idle) / 1e6
        retry = window["probe"].get("jtag_retry_profile")
        key = (direction, hz, limit)
        rows.setdefault(key, []).append((queue, ps, host, host/limit*100,
                                         int(retry[0]) if port == "jtag" and retry else 0))
    if not rows:
        raise ValueError("no directional windows in report")
    return [dict(direction=direction, hz=hz, idle=idle, rounds=len(values), wire_MBps=limit,
                 queue_MBps=median(v[0] for v in values), ps_MBps=median(v[1] for v in values),
                 pc_MBps=median(v[2] for v in values), pc_percent=median(v[3] for v in values),
                 jtag_max_backoffs=max(v[4] for v in values))
            for (direction,hz,limit),values in rows.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="selectio_pipeline_bench result.json")
    parser.add_argument("--legacy-idle", type=int, help="initial idle in an older report")
    parser.add_argument("--legacy-hz", type=int, help="register-derived queue clock for an older report")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        for row in summarize(report, args.legacy_idle, args.legacy_hz):
            print(json.dumps(row, allow_nan=False))
    except (ValueError, OSError, KeyError, ZeroDivisionError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
