"""Capture with KingstVIS and export the current buffer to CSV (all channels)."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, r"E:\zynqlinkPRO\tools\la")
from kingst_la import Vis  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=int, default=100_000_000)
    ap.add_argument("--time", type=float, default=0.02)
    ap.add_argument("--threshold", type=float, default=1.5)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--trigger", default=None, help='e.g. "--pos-edge 0"')
    ap.add_argument("--keep-settings", action="store_true",
                    help="do not override rate/threshold/trigger set in the GUI")
    args = ap.parse_args()

    v = Vis()
    print("last-error:", v.cmd("get-last-error"), flush=True)
    if not args.keep_settings:
        v.cmd(f"set-sample-rate {args.rate}")
        v.cmd(f"set-threshold-voltage {args.threshold}")
        if args.trigger:
            v.cmd("set-trigger " + args.trigger)
        else:
            v.cmd("set-trigger --reset")
    else:
        print("rate:", v.cmd("get-sample-rate"), flush=True)
    v.cmd(f"set-sample-time {args.time}")
    t0 = time.time()
    v.cmd("start", timeout=120)
    print(f"captured in {time.time()-t0:.2f}s depth={v.cmd('get-actual-sample-depth')} span={v.cmd('get-actual-sample-time')}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(6):
        if args.out.exists():
            args.out.unlink()
        try:
            v.cmd(f'export-data "{args.out.as_posix()}"', timeout=600)
        except Exception as e:                      # noqa: BLE001
            last_error = e
            time.sleep(0.5)
            continue
        deadline = time.time() + 120
        while time.time() < deadline and (not args.out.exists() or args.out.stat().st_size == 0):
            time.sleep(0.1)
        if args.out.exists() and args.out.stat().st_size:
            break
        time.sleep(0.5)
    if not args.out.exists() or not args.out.stat().st_size:
        raise SystemExit(f"export failed after retries: {last_error}")
    print(f"export {args.out} size={args.out.stat().st_size}", flush=True)
    v.close()


if __name__ == "__main__":
    main()
