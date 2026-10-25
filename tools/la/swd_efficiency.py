"""Decode contiguous legacy-core 47-clock OK / 13-clock WAIT SWD frames.

Unlike a gap-only splitter, this also handles adjacent frames with <200 ns gaps.
Rejects bad request headers and parity; partial first/last frames are skipped.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import numpy as np

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('csv',type=Path)
ap.add_argument('--ok-clocks',type=int,default=47,help='47 with one idle, 46 with idle=0')
args=ap.parse_args()
t=[];clk=[];dio=[]
with args.csv.open(newline='',encoding='utf-8-sig',errors='replace') as f:
    rows=csv.reader(f);next(rows)
    for row in rows:
        if row:t.append(float(row[0]));clk.append(int(row[1]));dio.append(int(row[2]))
t=np.array(t);clk=np.array(clk);dio=np.array(dio)
ri=np.where((clk[1:]==1)&(clk[:-1]==0))[0]+1
rt=t[ri]; bits=dio[ri]
frames=[]; k=0
while k+args.ok_clocks<=len(bits):
    h=bits[k:k+8]
    if h[0]!=1 or h[6]!=0 or h[7]!=1 or (sum(h[1:5])&1)!=h[5]:k+=1;continue
    ack=int(bits[k+9])|(int(bits[k+10])<<1)|(int(bits[k+11])<<2)
    n=args.ok_clocks if ack==1 else 13
    if ack not in (1,2,4) or rt[k+n-1]-rt[k]>3e-6:k+=1;continue
    if ack==1:
        d0=k+(12 if h[2] else 13)
        if (sum(bits[d0:d0+32])&1)!=bits[d0+32]:k+=1;continue
    frames.append({'k':k,'n':n,'t':rt[k],'ack':ack,'read':bool(h[2]),'ap':bool(h[1])})
    k+=n
# Request header clocks have no protocol decision stalls; avoid counting
# stretched ACK/data boundaries as part of the clock-rate estimate.
periods=np.concatenate([np.diff(rt[f['k']:f['k']+8]) for f in frames])
# Only consecutive complete frames contribute to the gap metric.
gaps=[]; intervals=[]
for a,b in zip(frames,frames[1:]):
    if a['k']+a['n']==b['k'] and b['t']-a['t']<3e-6:
        gaps.append((b['t']-rt[a['k']+a['n']-1])*1e9)
        if a['ack']==1 and a['ap'] and a['read'] and b['ack']==1:
            intervals.append((b['t']-a['t'])*1e9)
result={'rising_edges':len(rt),'valid_frames':len(frames),
        'decoder_warning':'Raw rising-edge heuristic; glitches/phase can create false WAIT/FAULT. This is not a hardware error counter. Validate known IDCODE and USB data.',
        'ack_counts':dict(Counter(x['ack'] for x in frames)),
        'clock_mean_period_ns':float(np.mean(periods)*1e9),
        'clock_mean_MHz':float(1e-6/np.mean(periods)),
        'interframe_rise_gap_median_ns':float(np.median(gaps)) if gaps else None,
        'consecutive_AP_read_start_median_ns':float(np.median(intervals)) if intervals else None}
print(json.dumps(result,indent=2))
args.csv.with_suffix('.efficiency.json').write_text(json.dumps(result,indent=2))
