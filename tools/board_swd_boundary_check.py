"""Check the SWD receive-boundary bit on the board at low clock rates.

The firmware clears CFG[18] every time the clock changes, so this sets the
clock first through the normal setup, then enables the short boundary with the
vendor 0x8A command and reads DPIDR plus a few AP words without touching the
clock again.
"""
import sys

sys.path.insert(0, r'E:\zynqlinkPRO\tools')
from dap_pipeline_bench import open_dap, setup, xfer, le  # noqa: E402

dev, out, inp = open_dap()

for speed_khz in (1000, 10000, 25000, 35000, 50000, 60000):
    for boundary in (0, 1):
        try:
            setup(out, inp, speed_khz)
            r = xfer(out, inp, [0x8A, boundary])
            cfg = r[2] if len(r) > 2 else None
            dpidr = xfer(out, inp, [0x05, 0x00, 0x01, 0x02])
            ok = len(dpidr) >= 7 and dpidr[2] == 1 and int.from_bytes(dpidr[3:7], 'little') == 0x1BA01477
            print(f'{speed_khz:6d} kHz boundary={boundary} cfg_bit18={cfg} dpidr={dpidr[:7].hex(" ")} {"OK" if ok else "FAIL"}', flush=True)
        except Exception as exc:
            print(f'{speed_khz:6d} kHz boundary={boundary} error: {exc}', flush=True)
