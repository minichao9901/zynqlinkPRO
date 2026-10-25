"""Summarize firmware USB event timing using the ELF's actual symbol layout."""
import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import statistics
import struct
import subprocess

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('binary', type=Path)
ap.add_argument('--elf', type=Path, default=Path('build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf'))
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
nm = Path(r'E:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-nm.exe')
symbols = {}
for line in subprocess.check_output([str(nm), str(a.elf)], text=True).splitlines():
    fields = line.split()
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)
data = a.binary.read_bytes()
base = symbols['__dap_trace_start']
def word(name):
    return struct.unpack_from('<I', data, symbols[name] - base)[0]
count, hz = word('dap_trace_count'), word('dap_trace_hz')
if count > 4096 or not hz:
    raise ValueError(f'Invalid trace header count={count} hz={hz}')
events = []
for n in range(count):
    lo, hi, ev, arg = struct.unpack_from('<4I', data, symbols['dap_trace_buf'] - base + n*16)
    events.append((((hi << 32) | lo)*1e6/hz, ev, arg))
groups = defaultdict(list)
requests, responses, submitted = deque(), deque(), deque()
commands = []
pending = None
for t, ev, arg in events:
    if ev == 1:
        requests.append(t)
    elif ev == 2:
        pending = {'cmd': arg, 'start': t}
        if requests:
            pending['out'] = requests.popleft()
    elif ev == 3 and pending:
        pending.update(done=t, response_bytes=arg)
        commands.append(pending)
        responses.append(pending)
        pending = None
    elif ev == 4 and responses:
        response = responses.popleft()
        response['submit'] = t
        submitted.append(response)
    elif ev == 5 and submitted:
        submitted.popleft()['complete'] = t
for c in commands:
    if c['cmd'] != 6 or 'submit' not in c:
        continue
    row = {'execute_us': c['done']-c['start'],
           'done_to_submit_us': c['submit']-c['done'],
           'response_bytes': c['response_bytes']}
    if 'out' in c:
        row['out_to_execute_us'] = c['start']-c['out']
    if 'complete' in c:
        row['submit_to_complete_us'] = c['complete']-c['submit']
    groups['read' if c['response_bytes'] > 4 else 'write'].append(row)
result = {'events': count, 'timer_Hz': hz, 'groups': {}}
for name, rows in groups.items():
    summary = {'commands': len(rows)}
    for field in sorted(set().union(*(r.keys() for r in rows))):
        values = [r[field] for r in rows if field in r]
        summary[field] = {'median': statistics.median(values), 'mean': statistics.mean(values),
                          'min': min(values), 'max': max(values)}
    result['groups'][name] = summary
result['rows'] = dict(groups)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(result, indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='rows'}, indent=2))
