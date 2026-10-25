"""USB IN completion timing: submit -> complete (wire time) and complete -> next OUT."""
import struct
from pathlib import Path

data = Path(r"E:\zynqlinkPRO\results\daplink\dap_trace.bin").read_bytes()
words = struct.unpack(f"<{len(data)//4}I", data)
count, hz = words[0], words[1]
ents = []
for i in range(count):
    lo, hi, ev, arg = words[16 + i * 4:20 + i * 4]
    ents.append(((hi << 32) | lo, ev, arg))

def us(t):
    return t / hz * 1e6

seq = [(us(t), ev, arg) for t, ev, arg in ents]
rows = []
for i, (t, ev, arg) in enumerate(seq):
    if ev == 2 and arg == 0x06:
        t_out = next((seq[j][0] for j in range(i - 1, -1, -1) if seq[j][1] == 1), None)
        t_in = next((seq[j][0] for j in range(i + 1, len(seq)) if seq[j][1] == 4), None)
        t_done_in = next((seq[j][0] for j in range(i + 1, len(seq)) if seq[j][1] == 5 and seq[j][0] >= (t_in or 0)), None)
        t_next_out = next((seq[j][0] for j in range(i + 1, len(seq)) if seq[j][1] == 1), None)
        rows.append((t_out, t, t_in, t_done_in, t_next_out))

print("blk  exec_us  in_submit_us  in_wire_us  in_done->next_out_us")
wires, gaps = [], []
for k, (t_out, t_exec, t_in, t_in_done, t_next) in enumerate(rows):
    wire = (t_in_done - t_in) if (t_in and t_in_done) else float("nan")
    gap = (t_next - t_in_done) if (t_next and t_in_done) else float("nan")
    if wire == wire:
        wires.append(wire)
    if gap == gap:
        gaps.append(gap)
    print(f"{k:3d} {2102.7:8.1f} {t_in - t_exec:10.1f} {wire:10.1f} {gap:14.1f}")

if wires:
    print(f"\nIN wire time: median={sorted(wires)[len(wires)//2]:.1f}us  (3084 B -> {3084/sorted(wires)[len(wires)//2]:.2f} MB/s)")
if gaps:
    print(f"IN complete -> next OUT: median={sorted(gaps)[len(gaps)//2]:.1f}us")
