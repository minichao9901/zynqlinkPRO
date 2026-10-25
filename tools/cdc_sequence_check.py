"""Check changing frame contents and monotonic sequences across cached DMA."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import time
import serial
from read_cdc_status import read_status

PAYLOADS = [bytes((seq + i * 17 + (i >> 3)) & 255 for i in range(16, 512)) for seq in range(256)]

def frame(seq):
    return struct.pack('<IIII', 0x30434443, seq, 512, seq ^ 0xFFFFFFFF) + PAYLOADS[seq & 255]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf', type=Path)
    ap.add_argument('--port', default='COM33')
    ap.add_argument('--seconds', type=float, default=3)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    before = read_status(args.elf)
    port = serial.Serial(port=None, baudrate=2000000, timeout=.2, write_timeout=5)
    port.port = args.port
    port.dtr = False
    result = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'before': before}
    try:
        port.open()
        port.set_buffer_size(rx_size=1024 * 1024, tx_size=1024 * 1024)
        time.sleep(.2)
        port.reset_input_buffer()
        port.dtr = True
        pending = bytearray()
        expected = None
        frames = 0
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            pending.extend(port.read(16384))
            while len(pending) >= 512:
                data = bytes(pending[:512])
                del pending[:512]
                _, seq, _, _ = struct.unpack_from('<IIII', data)
                if expected is not None and seq != expected:
                    raise RuntimeError(f'IN sequence error: got {seq}, expected {expected}')
                if data != frame(seq):
                    raise RuntimeError(f'IN content error: frame {seq}')
                expected = (seq + 1) & 0xFFFFFFFF
                frames += 1
        if frames < 100:
            raise RuntimeError('Insufficient IN frames')
        result['IN_verified_frames'] = frames
        result['IN_verified_bytes'] = frames * 512
        port.dtr = False
        time.sleep(.2)
        out_before = read_status(args.elf)
        seq = out_before['bench_rx_expected_seq']
        sent = 0
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            data = b''.join(frame((seq + i) & 0xFFFFFFFF) for i in range(32))
            done = 0
            while done < len(data):
                n = port.write(data[done:])
                if not n:
                    raise RuntimeError('Zero-byte OUT write')
                done += n
            seq = (seq + 32) & 0xFFFFFFFF
            sent += len(data)
        port.flush()
        time.sleep(.1)
        after = read_status(args.elf)
        if after['bench_rx_verify_errors'] != 0 or after['bench_rx_expected_seq'] != seq:
            raise RuntimeError('Device reported OUT content/sequence errors')
        if (after['bench_rx_bytes'] - out_before['bench_rx_bytes']) & 0xFFFFFFFF != sent:
            raise RuntimeError('OUT byte count mismatch')
        if after['bench_submit_errors']:
            raise RuntimeError('Device reported submit errors')
        result.update(OUT_verified_bytes=sent, OUT_verified_frames=sent // 512, after=after, status='passed')
        print(json.dumps(result, indent=2))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    finally:
        if port.is_open:
            port.dtr = False
            port.close()


if __name__ == '__main__':
    main()
