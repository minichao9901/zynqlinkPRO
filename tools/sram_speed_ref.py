"""Reference-style SRAM speed sweep (20 KB load/dump, wall + OpenOCD xfer timer).

Adapted from superlinkPRO/script_test/sram_speed_test.py for this DAP: the
SWD clock must be programmed *before* connecting (a mid-session speed change
without a line reset breaks the link on this firmware), so every speed runs a
fresh OpenOCD process.  Metric matches the original: one load_image + one
dump_image of a 20 KB blob, plus OpenOCD's own reported transfer rate.
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--speeds', default='20000,36000,45000,50000,60000,64000')
    ap.add_argument('--address', default='0x20000000')
    ap.add_argument('--size', type=lambda x: int(x, 0), default=20480)
    ap.add_argument('--config', default='tools/openocd_h7.cfg')
    ap.add_argument('--openocd-exe', default=r'E:\Share\env-windows\openocd-nightly\bin\openocd.exe')
    ap.add_argument('--scripts', default=r'E:\Share\env-windows\openocd-nightly\share\openocd\scripts')
    ap.add_argument('--output', default='results/optimization/sram_speed_ref.json')
    args = ap.parse_args()

    out_dir = ROOT / 'results/optimization/sram_speed_ref'
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / 'pattern.bin'
    if not pattern.exists() or pattern.stat().st_size != args.size:
        x = 0x12345678
        data = bytearray()
        for _ in range(args.size):
            x ^= (x << 13) & 0xFFFFFFFF
            x ^= x >> 17
            x ^= (x << 5) & 0xFFFFFFFF
            data.append(x & 0xFF)
        pattern.write_bytes(bytes(data))

    rows = []
    for spd in [int(s) for s in args.speeds.split(',')]:
        label = f'{spd / 1000:g} MHz'
        dump = out_dir / f'dump_{spd}.bin'
        tcl = out_dir / f'run_{spd}.tcl'
        tcl.write_text(f'''
init
reset halt
set t0 [clock microseconds]
for {{set i 0}} {{$i < 20}} {{incr i}} {{load_image {{{pattern.as_posix()}}} {args.address}}}
set t1 [clock microseconds]
for {{set i 0}} {{$i < 20}} {{incr i}} {{dump_image {{{dump.as_posix()}}} {args.address} 0x{args.size:x}}}
set t2 [clock microseconds]
echo "WALL write_ms=[expr {{$t1-$t0}}] read_ms=[expr {{$t2-$t1}}]"
shutdown
''')
        cmd = [args.openocd_exe, '-s', args.scripts, '-f', args.config,
               '-c', f'adapter speed {spd}', '-f', str(tcl)]
        t0 = time.perf_counter()
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           errors='replace', timeout=120,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        wall = time.perf_counter() - t0
        text = p.stdout + p.stderr
        (out_dir / f'run_{spd}.log').write_text(text, encoding='utf-8')
        m = re.search(r'WALL write_ms=(\d+) read_ms=(\d+)', text)
        if not m or 'Error' in text or p.returncode:
            rows.append({'speed_khz': spd, 'ok': False})
            print(f'{label:>8} | FAILED  {text.strip().splitlines()[-1][:80] if text.strip() else ""}')
            continue
        w_ms, r_ms = map(int, m.groups())
        got = dump.read_bytes()
        data_ok = got == pattern.read_bytes()
        wx = re.search(r'downloaded .*?\(([0-9.]+) KiB/s\)', text)
        rx = re.search(r'dumped .*?\(([0-9.]+) KiB/s\)', text)
        row = {'speed_khz': spd, 'ok': data_ok,
               'write_KB_s': args.size * 20 / (w_ms / 1e6) / 1024,
               'read_KB_s': args.size * 20 / (r_ms / 1e6) / 1024,
               'xfer_write_KB_s': float(wx.group(1)) if wx else None,
               'xfer_read_KB_s': float(rx.group(1)) if rx else None,
               'wall_s': wall}
        rows.append(row)
        print(f"{label:>8} | write {row['write_KB_s']:8.1f} KB/s | read {row['read_KB_s']:8.1f} KB/s"
              f" | xfer w {row['xfer_write_KB_s'] or 0:8.1f} r {row['xfer_read_KB_s'] or 0:8.1f}"
              f" | verified={data_ok}")

    Path(args.output).write_text(json.dumps({'address': args.address, 'size': args.size,
                                             'rows': rows}, indent=2), encoding='utf-8')
    print('\n=== summary (20 KB load/dump) ===')
    print(f"{'SWD clock':>9} | {'wall w':>9} | {'wall r':>9} | {'xfer w':>9} | {'xfer r':>9}")
    for r in rows:
        if not r['ok']:
            print(f"{r['speed_khz']/1000:>6g} MHz |   FAILED")
            continue
        print(f"{r['speed_khz']/1000:>6g} MHz | {r['write_KB_s']:8.1f}K | {r['read_KB_s']:8.1f}K"
              f" | {r['xfer_write_KB_s'] or 0:8.1f}K | {r['xfer_read_KB_s'] or 0:8.1f}K")


if __name__ == '__main__':
    main()



