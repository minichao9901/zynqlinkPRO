"""Build, RAM-download, and measure the connected benchmark board sequentially."""
import argparse
from argparse import Namespace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
from serial.tools.list_ports import comports
from cdc_bench import run
from read_cdc_status import read_status

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    '512_itc8': (512, 8, 0, 1, '0'),
    '512_itc0': (512, 0, 0, 1, '0'),
    '512_zlp': (512, 0, 1, 1, '0'),
    '512_poll': (512, 0, 0, 0, '0'),
    '4096_itc0': (4096, 0, 0, 1, '0'),
    '131072_itc0': (131072, 0, 0, 1, '0'),
    '512_O3': (512, 0, 0, 1, '3'),
    '4096_O3': (4096, 0, 0, 1, '3'),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cases', nargs='+', choices=list(CASES), default=list(CASES))
    ap.add_argument('--seconds', type=float, default=2)
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--host-chunk', type=int, default=65536)
    ap.add_argument('--output-dir', type=Path, default=ROOT / 'results/matrix')
    ap.add_argument('--memory-mode', choices=['legacy', 'isolated', 'cached', 'hybrid'], default='legacy')
    args = ap.parse_args()
    folder = args.output_dir
    folder.mkdir(parents=True, exist_ok=True)
    for name in args.cases:
        size, itc, zlp, callback, opt = CASES[name]
        tag = f'tx{size}_rx{size}_itc{itc}_zlp{zlp}_cb{callback}_O{opt}_mem{args.memory_mode}'
        result = {'case': name, 'tag': tag, 'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'runs': []}
        print('START', name, flush=True)
        try:
            build = subprocess.run(['python', str(ROOT / 'tools/build_cdc_bench.py'), '--tx', str(size), '--rx', str(size), '--itc', str(itc), '--zlp', str(zlp), '--callback-tx', str(callback), '--opt', opt, '--memory-mode', args.memory_mode], capture_output=True, text=True, timeout=30)
            (folder / (name + '_build.log')).write_text(build.stdout + build.stderr, encoding='utf-8')
            if build.returncode:
                raise RuntimeError('Build failed')
            elf = ROOT / 'build/cdc_bench' / tag / 'cdc_bench.elf'
            result['elf_sha256'] = hashlib.sha256(elf.read_bytes()).hexdigest()
            download = subprocess.run(['python', str(ROOT / 'tools/run_xsct.py'), str(ROOT / 'tools/download_cdc.tcl'), str(elf)], capture_output=True, text=True, timeout=35)
            (folder / (name + '_download.log')).write_text(download.stdout + download.stderr, encoding='utf-8')
            if download.returncode:
                raise RuntimeError('Download failed')
            time.sleep(1)
            port = next((p.device for p in comports() if p.vid == 0xFFFF and p.pid == 0xFFFF), None)
            if not port:
                raise RuntimeError('CDC did not enumerate')
            status = read_status(elf)
            result['initial_status'] = status
            if status['usb_speed_code'] != 2 or status['itc'] != itc:
                raise RuntimeError('Unexpected USB speed or ITC')
            for direction in ['in', 'out']:
                for repeat in range(args.repeat):
                    before = read_status(elf)
                    host_args = Namespace(port=port, timeout=5, direction=direction, chunk=max(args.host_chunk, size), seconds=args.seconds, verify=False, device_tx=size, note=tag)
                    row = run(host_args)
                    time.sleep(0.05)
                    after = read_status(elf)
                    row['device_before'] = before
                    row['device_after'] = after
                    row['repeat'] = repeat + 1
                    if direction == 'out':
                        delta = (after['bench_rx_bytes'] - before['bench_rx_bytes']) & 0xFFFFFFFF
                        row['device_rx_delta'] = delta
                        row['device_rx_count_matches'] = delta == row['bytes']
                        if not row['device_rx_count_matches']:
                            raise RuntimeError(f'RX count mismatch: device={delta}, host={row["bytes"]}')
                    if after['bench_submit_errors'] != 0:
                        raise RuntimeError('Firmware submit error')
                    result['runs'].append(row)
            verify_args = Namespace(port=port, timeout=5, direction='in', chunk=4096, seconds=.5, verify=True, device_tx=size, note=tag + ' pattern check')
            result['pattern_check'] = run(verify_args)
            result['median_MB_per_second'] = {d: statistics.median(x['MB_per_second'] for x in result['runs'] if x['direction'] == d) for d in ['in', 'out']}
            result['status'] = 'passed'
            print('PASS', name, result['median_MB_per_second'], flush=True)
        except Exception as exc:
            result['status'] = 'failed'
            result['error'] = str(exc)
            print('FAIL', name, str(exc), flush=True)
        (folder / (name + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
