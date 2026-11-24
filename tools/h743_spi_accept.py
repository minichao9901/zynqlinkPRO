"""Exercise the H743 USB-controlled SPI2 fixture and the J7 SPI paths."""
import argparse
import json
from pathlib import Path
import struct
import time

import serial
from serial.tools.list_ports import comports

from selectio_native import native_connection

H743_USB = (0xF055, 0x7432, "H743SPI0001")
DIVIDERS = (256, 128, 64, 32, 16, 8, 4, 2)
CHANNEL = 4


def payload(seed, length):
    values = ((i ^ seed) * 0x9e3779b1 & 0xffffffff for i in range(length))
    return bytes((x ^ (x >> 13) ^ (x >> 23)) & 255 for x in values)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class ReleaseError(Exception):
    """A role could not be released. Further SPI operations are unsafe."""


def release(h743, probe=None):
    try:
        try:
            require(h743.state("SPI STOP")["state"] != "active", "H743 still owns the bus")
        finally:
            if probe is not None:
                probe.exchange(CHANNEL, 5)
    except Exception as error:
        raise ReleaseError(f"SPI pin release could not be verified: {error}") from error


class Fixture:
    def __init__(self, port):
        self.port = port
        self.kernel = 0

    def command(self, command):
        self.port.write((command + "\n").encode("ascii"))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            line = self.port.readline().decode("ascii").strip()
            if line and line != "H743SPI/1 ready":
                require(not line.startswith("ERR "), f"H743 {command!r}: {line}")
                return line
        raise TimeoutError(f"no H743 reply to {command!r}")

    def identify(self):
        require(self.command("PING") == "PONG H743SPI/1", "wrong H743 firmware")
        info = self.command("SPI INFO")
        require(info.startswith("H743SPI/1 "), f"unexpected H743 fixture info: {info}")
        self.kernel = int(dict(field.split("=", 1) for field in info.split()[1:])["kernel_hz"])
        require(self.kernel == 200_000_000, f"unexpected H743 SPI2 kernel clock: {self.kernel}")
        return info

    def state(self, command="SPI STATUS"):
        reply = self.command(command)
        require(reply.startswith("SPI state="), f"unexpected H743 status: {reply}")
        return {key: value if key in ("role", "state") else int(value, 0)
                for key, value in (field.split("=", 1) for field in reply.split()[1:])}

    def wait(self):
        until = time.monotonic() + 2
        while True:
            status = self.state()
            if status["state"] != "active" or time.monotonic() >= until:
                return status
            time.sleep(0.005)


def assert_status(status, *, received=None):
    require(status["state"] == "done" and not any(status[k] for k in ("bad", "spi", "dma")),
            f"H743 transfer failed: {status}")
    if received is not None:
        require(status["rx"] == received, f"H743 expected {received} bytes: {status}")


def spi_config(codec, mode, hz, slot=0, drive=0, tap=0):
    return struct.pack("<BBBBIB", codec, drive, mode, slot, hz, tap)


def receive_on_j7(probe, h743, mode, divider, row, seconds=0):
    hz = h743.kernel // divider
    row.update(sck_hz=hz, sck_source="H743 PLL2 readback and SPI2 divider")
    seed = 0xB594D20F ^ (mode << 24) ^ divider
    block_size = 16384 if seconds else 4096
    expected = payload(seed, block_size)
    first_bad = None
    total = 0

    def accept(data):
        nonlocal total, first_bad
        if first_bad is None and data:
            offset = total % block_size
            patterns = (expected + expected) if len(data) + offset > block_size else expected
            match = patterns[offset:offset + len(data)]
            if match != data:
                first_bad = total + next(i for i, (a, b) in enumerate(zip(match, data)) if a != b)
        total += len(data)

    probe.exchange(CHANNEL, 0, spi_config(3, mode, hz))
    start = time.monotonic()
    try:
        if seconds:
            started = h743.state(f"SPI STREAM {mode} {divider} {round(1000 * seconds)} {seed}")
        else:
            started = h743.state(f"SPI MASTER TX {mode} {divider} {block_size} 4 2000 {seed} 0")
        require(started["state"] == "active" and started["sck_hz"] == hz, f"H743 did not start: {started}")
        deadline = time.monotonic() + max(3, seconds + 3)
        next_status = time.monotonic() if not seconds else time.monotonic() + seconds
        status = started
        while time.monotonic() < deadline:
            data = probe.exchange(CHANNEL, 1)
            accept(data)
            if time.monotonic() >= next_status:
                status = h743.state()
                if status["state"] != "active":
                    break
                next_status = time.monotonic() + 0.02
            if not data:
                time.sleep(0.001)
        probe.exchange(CHANNEL, 3)
        while data := probe.exchange(CHANNEL, 1):
            accept(data)
        pending, dropped, errors, flags, cursor = struct.unpack("<5I", probe.exchange(CHANNEL, 4))
        elapsed = time.monotonic() - start
        row.update(bytes=total, first_bad=first_bad, duration_seconds=elapsed,
                   pc_MBps=total / elapsed / 1e6, probe=dict(pending=pending, dropped=dropped,
                   errors=errors, flags=flags, cursor=cursor), target=status)
        assert_status(status)
        require(total and first_bad is None and not (pending or dropped or errors), "J7 receive mismatch or loss")
        if seconds:
            # TX DMA can be up to one TX FIFO ahead of what was shifted when SPI is suspended.
            require(0 <= status["tx_dma"] - total <= 32, "J7 stream count differs from the H743 TX DMA count")
            require(status["ms"] >= round(1000 * seconds), "H743 stopped streaming early")
        else:
            require(total == status["tx_dma"] == block_size * 4, "J7 finite transfer count mismatch")
    finally:
        release(h743, probe)


def receive_on_h743(probe, h743, mode, length, row):
    hz = 100_000_000
    seed = 0x4C20A5DF ^ (mode << 23) ^ length
    row.update(sck_hz=hz, sck_source="J7 native SPI configured clock", size=length)
    started = h743.state(f"SPI SLAVE RX {mode} {length} 5000 0 {seed}")
    configured = False
    try:
        require(started["state"] == "active", f"H743 did not arm: {started}")
        probe.exchange(CHANNEL, 0, spi_config(0, mode, hz, slot=18 + 2 * (mode & 1)))
        configured = True
        probe.exchange(CHANNEL, 2, payload(seed, length))
        probe.exchange(CHANNEL, 3)
        count = 0
        while data := probe.exchange(CHANNEL, 1):
            count += len(data)
        stats = struct.unpack("<5I", probe.exchange(CHANNEL, 4))
        row.update(target=h743.wait(), probe_stats=stats, miso_sample_bytes=count)
        assert_status(row["target"], received=length)
        require(count == length and not any(stats[:3]), f"invalid master completion: {stats}")
    finally:
        release(h743, probe if configured else None)


def raw_wave(mode, half, data):
    idle = (mode >> 1) & 1
    late = mode & 1
    plan = [(idle, 1, 0)] * 16
    bits = [(byte >> b) & 1 for byte in data for b in range(7, -1, -1)]
    previous = 0 if late else bits[0]
    plan.extend([(idle, 0, previous)] * 32)
    samples = []
    for i, bit in enumerate(bits):
        samples.append(len(plan) + half * late)
        plan.extend([(1 ^ idle, 0, bit)] * half)
        after = bits[i + 1] if not late and i + 1 < len(bits) else bit
        plan.extend([(idle, 0, after)] * half)
    plan.extend([(idle, 0, plan[-1][2])] * 16)
    plan.extend([(idle, 1, 0)] * 48)
    plan.extend([plan[-1]] * (-len(plan) % 8))
    require(len(plan) <= 4096, "raw J7 transaction exceeds the physical waveform buffer")
    packed = bytes(sum(plan[i + bit][pin] << bit for bit in range(8))
                   for i in range(0, len(plan), 8) for pin in range(3))
    return packed, samples


def raw_duplex(probe, h743, mode, reference, row):
    # Use J7's raw SelectIO waveform path to go below the 31 MHz H743 slave TX limit.
    half = (reference + 24_999_999) // 25_000_000
    length = min(24, (4096 - 120) // (16 * half))
    tx_seed, rx_seed = 0x958A13CE ^ mode, 0x6EC21475 ^ mode
    output, indices = raw_wave(mode, half, payload(tx_seed, length))
    row.update(sck_hz=reference // half, sck_source="J7 raw sample reference and waveform period", size=length)
    probe.exchange(CHANNEL, 0, spi_config(1, mode, 50_000_000, drive=2))
    try:
        idle = 255 if mode & 2 else 0
        probe.exchange(CHANNEL, 8, bytes((idle, 255, 0)))
        started = h743.state(f"SPI SLAVE FD {mode} {length} 5000 {rx_seed} {tx_seed}")
        require(started["state"] == "active", f"H743 did not arm: {started}")
        probe.exchange(CHANNEL, 8, output)
        samples = probe.exchange(CHANNEL, 7)
        levels = [(byte >> bit) & 1 for byte in samples for bit in range(8)]
        require(len(levels) == len(output) // 3 * 8, "J7 raw capture was truncated")
        expected = payload(rx_seed, length)
        matching = []
        for delay in range(32):
            got = bytes(sum(levels[indices[i + b] + delay] << (7 - b) for b in range(8))
                        for i in range(0, len(indices), 8))
            if got == expected:
                matching.append(delay)
        row.update(target=h743.wait(), matching_sample_offsets=matching)
        assert_status(row["target"], received=length)
        require(matching, "J7 raw MISO differs at all candidate offsets")
    finally:
        release(h743, probe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="12345678", help="J7 USB serial")
    parser.add_argument("--out", type=Path, required=True, help="new JSON report file")
    parser.add_argument("--cdc-only", action="store_true")
    parser.add_argument("--modes", type=int, nargs="+", choices=range(4), default=list(range(4)))
    parser.add_argument("--seconds", type=int, choices=range(121), default=0, metavar="0..120")
    parser.add_argument("--repeats", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    ports = [p.device for p in comports() if (p.vid, p.pid, p.serial_number) == H743_USB]
    require(len(ports) == 1, f"expected one H743SPI fixture, found {ports}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.touch(exist_ok=False)
    report = dict(h743_com=ports[0], j7_serial=args.serial, rows=[])

    def save():
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def check(name, mode, fn, *values, **options):
        row = dict(case=name, mode=mode, passed=False)
        report["rows"].append(row)
        try:
            fn(*values, row=row, **options)
            row["passed"] = True
        except (RuntimeError, TimeoutError) as error:
            row["error"] = str(error)
        finally:
            save()
            print(json.dumps(row), flush=True)
        return row["passed"]

    try:
        with serial.Serial(ports[0], 115200, timeout=0.05, write_timeout=2) as port:
            h743 = Fixture(port)
            report["fixture"] = h743.identify()
            report["initial_status"] = h743.state("SPI STOP")
            save()
            if args.cdc_only:
                return 0
            with native_connection(args.serial) as probe:
                info = report["probe"] = probe.info()
                require(info["dedicated_pipes"], "expected the ABI 2 J7 pair")
                for mode in args.modes:
                    passing = []
                    for divider in DIVIDERS:
                        if check("j7_slave", mode, receive_on_j7, probe, h743, mode, divider):
                            passing.append(divider)
                    for length in (1, 5, 4096):
                        check("j7_native_master", mode, receive_on_h743, probe, h743, mode, length)
                    check("j7_raw_duplex", mode, raw_duplex, probe, h743, mode, info["reference_hz"])
                    if args.seconds:
                        for divider in reversed(passing):
                            trials = [check("j7_slave_sustained", mode, receive_on_j7, probe, h743, mode, divider,
                                            seconds=args.seconds) for _ in range(args.repeats)]
                            if all(trials):
                                break
            report["final_status"] = h743.state("SPI STOP")
    except ReleaseError as error:
        report["error"] = str(error)
        raise
    finally:
        save()
    return 0 if report["rows"] and all(row["passed"] for row in report["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
