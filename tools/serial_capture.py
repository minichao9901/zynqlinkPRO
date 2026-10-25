"""Capture a serial port to a log file for a fixed number of seconds."""
import argparse
import time
from pathlib import Path

import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=15)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + args.seconds
    with serial.Serial(args.port, args.baud, timeout=0.2) as port, args.output.open("wb") as log:
        while time.time() < deadline:
            data = port.read(4096)
            if data:
                log.write(data)
                log.flush()


if __name__ == "__main__":
    main()
