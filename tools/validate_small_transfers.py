"""Check 2..7 mixed transfers and nested block responses without SRAM writes."""
import argparse
import json
import struct
from pathlib import Path

import usb.util
from dap_pipeline_bench import open_dap, setup, xfer, le

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--rounds', type=int, default=100)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
d, out, inp = open_dap()
rows = []

def transfer(ops):
    payload = [5, 0, len(ops)]
    for req, value in ops:
        payload += [req] + (le(value) if not req & 2 else [])
    r = xfer(out, inp, payload)
    assert r[:3] == bytes([5, len(ops), 1]), r.hex()
    return list(struct.unpack('<' + 'I' * ((len(r)-3)//4), r[3:]))

try:
    setup(out, inp, 60000)
    ref = xfer(out, inp, [6, 0, 64, 0, 15])
    assert ref[:4] == bytes([6, 64, 0, 1]), ref.hex()
    memory = struct.unpack('<64I', ref[4:])
    for k in range(a.rounds):
        offset = (k % 8) * 16
        tar = (5, 0x20000000 + offset)
        tar2 = (5, 0x20000000 + offset + 8)
        read = (15, 0)
        dp = (2, 0)
        v = memory[offset//4:offset//4+4]
        cases = [
            ([tar, read], [v[0]]),
            ([tar, read, read], list(v[:2])),
            ([dp, tar, read, dp], [0x1ba01477, v[0], 0x1ba01477]),
            ([tar, read, dp, tar2, read], [v[0], 0x1ba01477, v[2]]),
            ([(8, 0), (1, 0x23000052), tar, read, read, dp], list(v[:2])+[0x1ba01477]),
            ([tar, read, read, tar2, read, read, dp], list(v)+[0x1ba01477]),
        ]
        for ops, expected in cases:
            got = transfer(ops)
            assert got == expected, (k, ops, got, expected)
    # ExecuteCommands offsets the nested response, exercising the private-buffer
    # fallback when a USB-slot-aligned zero-copy DMA would be inappropriate.
    for n in (1, 7, 8, 9, 63, 127, 128, 255):
        transfer([(5, 0x20000000)])
        payload = [0x7f, 2, 5, 0, 1, 2, 6, 0, n & 255, n >> 8, 15]
        r = xfer(out, inp, payload)
        assert r[:9] == bytes([0x7f, 2, 5, 1, 1])+struct.pack('<I', 0x1ba01477), r[:16].hex()
        assert r[9:13] == bytes([6, n & 255, n >> 8, 1]), r[:16].hex()
        assert len(r) == 13+4*n, len(r)
        assert r[13:13+4*min(n, 64)] == ref[4:4+4*min(n, 64)]
        rows.append({'nested_words': n, 'pass': True})
    rows.append({'mixed_2_to_7_commands': 6*a.rounds, 'pass': True})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(rows, indent=2))
    print(f'PASS {6*a.rounds} mixed commands and 8 nested block boundaries')
finally:
    usb.util.release_interface(d, 0)
    usb.util.dispose_resources(d)
