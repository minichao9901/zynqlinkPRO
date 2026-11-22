"""Measure verified DDR/PL payload BRAM bursts with the probe's own timer."""
import argparse
import json
from pathlib import Path
from statistics import median
import struct

from selectio_native import native_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="12345678")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=128)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--clock", choices=("current", "133MHz"), default="133MHz",
                        help="temporary FCLK0 profile for a matched A/B")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 256 or args.rounds < 1:
        parser.error("repeats must be 1..256 and rounds must be positive")
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"serial": args.serial, "repeats": args.repeats, "rounds": args.rounds, "windows": []}
    try:
        with native_connection(args.serial) as dev:
            report["probe"] = dev.info()
            for size in (4, 16, 32, 64, 128, 256, 512, 1024):
                for run in range(args.rounds):
                    reply = dev.exchange(7, 7, struct.pack("<3I", size, args.repeats, int(args.clock=="133MHz")))
                    hz, tx_total, tx_min, tx_max, rx_total, rx_min, rx_max, fclk0, ref, signature = struct.unpack("<7Q3I", reply)
                    if not hz or not (tx_min*args.repeats <= tx_total <= tx_max*args.repeats and
                                      rx_min*args.repeats <= rx_total <= rx_max*args.repeats):
                        raise RuntimeError("invalid probe timing record")
                    if args.clock=="133MHz" and abs(fclk0-133333333)>2:
                        raise RuntimeError("unexpected FCLK0 frequency")
                    report["windows"].append(dict(bytes=size, round=run+1, timer_hz=hz,
                        fclk0_hz=fclk0, selectio_ref_hz=ref, selectio_quad_hz=ref//2,
                        queue_signature=hex(signature),
                        upload_mean_us=1e6*tx_total/hz/args.repeats, upload_min_us=1e6*tx_min/hz,
                        upload_max_us=1e6*tx_max/hz, download_mean_us=1e6*rx_total/hz/args.repeats,
                        download_min_us=1e6*rx_min/hz, download_max_us=1e6*rx_max/hz))
        report["passed"] = True
        for size in (4, 16, 32, 64, 128, 256, 512, 1024):
            rows = [row for row in report["windows"] if row["bytes"] == size]
            print(size, *(round(median(row[key] for row in rows), 3)
                          for key in ("upload_mean_us", "download_mean_us")), flush=True)
    finally:
        (args.out/"result.json").write_text(json.dumps(report, indent=2)+"\n", "utf8")


if __name__ == "__main__":
    main()
