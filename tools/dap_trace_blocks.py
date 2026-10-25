"""Per-block-command breakdown of the firmware timing trace."""
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

# sequence of OUT/EXEC/DONE/IN with absolute microseconds
seq = [(us(t), ev, arg) for t, ev, arg in ents]

blocks = []
for idx, (t, ev, arg) in enumerate(seq):
    if ev == 2 and arg == 0x06:
        # nearest preceding OUT
        t_out = next((seq[j][0] for j in range(idx - 1, -1, -1) if seq[j][1] == 1), None)
        # DONE
        t_done = next((seq[j][0] for j in range(idx + 1, len(seq)) if seq[j][1] == 3), None)
        # first IN after DONE
        t_in = next((seq[j][0] for j in range(idx + 1, len(seq)) if seq[j][1] == 4), None)
        blocks.append((t_out, t, t_done, t_in))

print("block  out->exec  exec_us  done->in  out->in  resp_bytes")
prev_in = None
for k, (t_out, t_exec, t_done, t_in) in enumerate(blocks):
    resp = next((a for tt, e, a in seq if e == 4 and tt == t_in), 0)
    print(f"{k:5d} {t_exec - t_out:9.1f} {t_done - t_exec:8.1f} {t_in - t_done:9.1f} {t_in - t_out:8.1f} {resp:9d}")
    if prev_in is not None:
        pass
    prev_in = t_in

if len(blocks) > 1:
    ex = [b[2] - b[1] for b in blocks]
    out_in = [b[3] - b[0] for b in blocks]
    print(f"\nexec per block: median={sorted(ex)[len(ex)//2]:.1f}us  total={sum(ex)/1000:.2f}ms")
    print(f"out->in per block: median={sorted(out_in)[len(out_in)//2]:.1f}us  total={sum(out_in)/1000:.2f}ms")
