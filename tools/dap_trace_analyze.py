"""Parse the firmware timing trace (count, hz, entries[lo,hi,ev,arg])."""
import struct
from pathlib import Path

RAW = Path(r"E:\zynqlinkPRO\results\daplink\dap_trace.bin")
data = RAW.read_bytes()
words = struct.unpack(f"<{len(data)//4}I", data)
count = words[0]
hz = words[1]
ents = []
for i in range(count):
    lo, hi, ev, arg = words[16 + i * 4:20 + i * 4]
    ticks = (hi << 32) | lo
    ents.append((ticks / hz * 1e6, ev, arg))

print(f"count={count} hz={hz} first_t={ents[0][0]:.3f}us last_t={ents[-1][0]:.3f}us")

# event names
names = {1: "OUT", 2: "EXEC", 3: "DONE", 4: "IN"}

# pair EXEC/DONE
pairs = []
pending = None
for t, ev, arg in ents:
    if ev == 2:
        pending = (t, arg)
    elif ev == 3 and pending:
        pairs.append((pending[0], t, pending[1], arg))
        pending = None

from collections import defaultdict
by_cmd = defaultdict(list)
for t0, t1, cmd, resp in pairs:
    by_cmd[cmd].append((t1 - t0, resp))

print("\nEXEC durations by command:")
for cmd, lst in sorted(by_cmd.items()):
    durs = [d for d, _ in lst]
    durs.sort()
    print(f"  cmd=0x{cmd:02x} n={len(durs):3d} median={durs[len(durs)//2]:8.1f}us "
          f"min={durs[0]:7.1f} max={durs[-1]:7.1f} total={sum(durs)/1000:.2f}ms")

# OUT intervals
outs = [t for t, ev, arg in ents if ev == 1]
if len(outs) > 1:
    gaps = [b - a for a, b in zip(outs, outs[1:])]
    gaps_sorted = sorted(gaps)
    print(f"\nOUT packets={len(outs)} interval median={gaps_sorted[len(gaps)//2]:.1f}us "
          f"min={gaps_sorted[0]:.1f} max={gaps_sorted[-1]:.1f}")
    print("  first intervals:", " ".join(f"{g:.0f}" for g in gaps[:12]))

# per-cycle: OUT -> EXEC -> DONE -> IN -> next OUT
print("\nFirst 24 events:")
for t, ev, arg in ents[:24]:
    print(f"  {t:9.3f}us {names.get(ev, ev)} arg={arg}")

# aggregate: time from OUT to IN for each command
lat = []
i = 0
while i < len(ents):
    if ents[i][1] == 1:
        t_out = ents[i][0]
        j = i + 1
        while j < len(ents) and ents[j][1] != 4:
            j += 1
        if j < len(ents):
            lat.append(ents[j][0] - t_out)
        i = j
    i += 1
if lat:
    lat.sort()
    print(f"\nOUT->IN latency n={len(lat)} median={lat[len(lat)//2]:.1f}us min={lat[0]:.1f} max={lat[-1]:.1f}")
