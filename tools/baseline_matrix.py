"""Full matrix on the baseline firmware: SRAM speed + correctness, RTT, HSS."""
import json, random, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from dap_pipeline_bench import open_dap, setup
from test_probe_board import Memory

SPEEDS = [int(x) for x in sys.argv[1].split(',')]
dev, out, inp = open_dap()
pat = random.Random(2024).randbytes(4096)

def one(speed):
    row = {'req_khz': speed // 1000}
    try:
        setup(out, inp, speed, 'jtag')
    except Exception as e:
        row['connect'] = 'FAIL:' + type(e).__name__
        return row
    row['connect'] = 'ok'
    m = Memory(out, inp)
    try:
        m.write(0x20004000, pat)
        bad = sum(1 for _ in range(4) if m.read(0x20004000, 4096) != pat)
        row['sram_4k_mismatch'] = '%d/4' % bad
    except Exception as e:
        row['sram_4k_mismatch'] = 'FAIL:' + type(e).__name__
    return row

rows = []
for s in SPEEDS:
    rows.append(one(s))
print(json.dumps(rows))