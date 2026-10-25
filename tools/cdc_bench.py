"""Binary CDC throughput test. IN/OUT are named from the USB host's view.

DTR=0 selects device sink; DTR=1 selects continuous device source.
OUT is host delivery timing, not device completion timing; compare firmware
bench_rx_bytes through JTAG before claiming end-to-end OUT throughput.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import serial
from serial.tools.list_ports import comports


def run(args):
    # Set DTR before open, avoiding the default asserted DTR starting the source.
    port = serial.Serial(port=None, baudrate=2000000, timeout=0.2, write_timeout=args.timeout)
    port.port = args.port
    port.dtr = False
    port.rts = False
    count = calls = empty_reads = 0
    lengths = {}
    started = None
    try:
        port.open()
        port.set_buffer_size(rx_size=1024 * 1024, tx_size=1024 * 1024)
        time.sleep(0.2)
        port.reset_input_buffer()
        payload = bytes(range(256)) * ((args.chunk + 255) // 256)
        payload = payload[:args.chunk]
        if args.direction == 'in':
            port.dtr = True
        started = last_progress = time.perf_counter()
        deadline = started + args.seconds
        validation_offset = 0
        # Warmup is a separate timed invocation when needed, so reported bytes
        # always correspond exactly to the reported timed interval.
        while time.perf_counter() < deadline:
            if args.direction == 'out':
                n = port.write(payload)
                if n <= 0:
                    raise RuntimeError('Zero-byte write')
                # pySerial may return a short write; do not discard its suffix.
                offset = n
                while offset < len(payload):
                    n2 = port.write(payload[offset:])
                    if n2 <= 0:
                        raise RuntimeError('Zero-byte partial write')
                    offset += n2
                n = offset
            else:
                data = port.read(args.chunk)
                n = len(data)
                if not n:
                    empty_reads += 1
                if args.verify and data:
                    period = args.device_tx
                    expected = bytes(((validation_offset + i) % period) & 255 for i in range(n))
                    if data != expected:
                        raise RuntimeError(f'IN data mismatch at or after stream offset {validation_offset}')
                    validation_offset = (validation_offset + n) % period
            calls += 1
            count += n
            lengths[n] = lengths.get(n, 0) + 1
            now = time.perf_counter()
            if n:
                last_progress = now
            elif now - last_progress > args.timeout:
                raise TimeoutError(f'No data for {args.timeout} seconds')
        if args.direction == 'out':
            port.flush()
        elapsed = time.perf_counter() - started
        return {
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'port': args.port, 'direction': args.direction,
            'host_chunk_bytes': args.chunk, 'bytes': count,
            'elapsed_seconds': elapsed, 'MB_per_second': count / elapsed / 1e6,
            'MiB_per_second': count / elapsed / 1048576,
            'host_calls': calls, 'empty_reads': empty_reads,
            'returned_length_histogram': lengths, 'verified': bool(args.verify),
            'note': args.note,
            'measurement': 'host-delivered; confirm device RX counter' if args.direction == 'out' else 'host-received',
        }
    finally:
        if port.is_open:
            port.dtr = False
            port.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--port')
    ap.add_argument('--direction', choices=['in', 'out'], default='in')
    ap.add_argument('--chunk', type=int, default=65536)
    ap.add_argument('--seconds', type=float, default=3)
    ap.add_argument('--timeout', type=float, default=5)
    ap.add_argument('--verify', action='store_true', help='Only for the new ramp-pattern firmware; adds CPU overhead')
    ap.add_argument('--device-tx', type=int, default=512, help='Firmware TX length for pattern validation')
    ap.add_argument('--note', default='')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    if args.list:
        print(json.dumps([{'port': p.device, 'description': p.description, 'hwid': p.hwid} for p in comports()], ensure_ascii=False, indent=2))
        return
    if not args.port or min(args.chunk, args.seconds, args.timeout, args.device_tx) <= 0:
        ap.error('--port and positive size/time arguments are required')
    if args.verify and args.direction != 'in':
        ap.error('--verify currently supports IN only')
    try:
        result = run(args)
    except (serial.SerialException, OSError, RuntimeError) as exc:
        ap.exit(1, f'Benchmark failed: {exc}\n')
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
