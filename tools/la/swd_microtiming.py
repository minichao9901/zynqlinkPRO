"""Measure per-bit SWCLK widths and visible SWDIO launch delays from CSV.

Targets the 46-clock idle=0 read/write format used by this core. DIO launch
delays refer to observed transitions at the probes, not internal setup/hold.
"""
import argparse,csv,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('csv',type=Path)
ap.add_argument('--ok-clocks',type=int,default=46)
ap.add_argument('--deglitch-ns',type=float,default=0,help='analysis-only removal of isolated returning pulses')
args=ap.parse_args()
rows=[]
with args.csv.open(newline='',encoding='utf-8-sig',errors='replace') as f:
 r=csv.reader(f);next(r)
 for x in r:
  if x:rows.append([float(x[0])*1e9,int(x[1]),int(x[2])])
a=np.array(rows);t=a[:,0];cl=a[:,1].astype(int);di=a[:,2].astype(int)
removed={}
if args.deglitch_ns:
 for name,levels in [('clk',cl),('dio',di)]:
  indices=np.where(levels[1:]!=levels[:-1])[0]+1
  keep=[];j=0;removed[name]=0
  while j<len(indices):
   if j+1<len(indices) and t[indices[j+1]]-t[indices[j]]<=args.deglitch_ns+.001:
    removed[name]+=1;j+=2
   else:keep.append(indices[j]);j+=1
  keep=np.array(keep,dtype=int)
  pos=np.searchsorted(t[keep],t,side='right')
  values=np.concatenate(([levels[0]],levels[keep]))
  if name=='clk':cl=values[pos]
  else:di=values[pos]
tag=f'.filtered{args.deglitch_ns:g}ns' if args.deglitch_ns else ''
ri=np.where((cl[1:]==1)&(cl[:-1]==0))[0]+1
fi=np.where((cl[1:]==0)&(cl[:-1]==1))[0]+1
dx=np.where(di[1:]!=di[:-1])[0]+1
rt=t[ri];ft=t[fi];dt=t[dx];bits=di[ri]
frames=[];words=Counter();k=0;N=args.ok_clocks
while k+N<len(rt):
 h=bits[k:k+8]
 if h[0]!=1 or h[6]!=0 or h[7]!=1 or (sum(h[1:5])&1)!=h[5]:k+=1;continue
 ack=int(bits[k+9])|(int(bits[k+10])<<1)|(int(bits[k+11])<<2)
 if ack!=1 or rt[k+N-1]-rt[k]>3000:k+=1;continue
 start=k+(12 if h[2] else 13)
 if (sum(bits[start:start+32])&1)!=bits[start+32]:k+=1;continue
 if h[2]:words[f'0x{sum(int(bits[start+j])<<j for j in range(32)):08x}']+=1
 frames.append({'k':k,'read':bool(h[2]),'ap':bool(h[1])});k+=N
def stat(v):
 v=np.array(v)
 if not len(v):return None
 return {'n':len(v),'min':float(min(v)),'p10':float(np.percentile(v,10)),
         'median':float(np.median(v)),'p90':float(np.percentile(v,90)),
         'max':float(max(v)),'mean':float(np.mean(v))}
groups={x:{'period':[],'high':[],'low':[]} for x in ('request','ack','data','parity_to_turn')}
delays={'host_request':[],'target_ack':[],'target_data':[]}
target_rise_delays=[]
profiles=[]
for fr in frames:
 k=fr['k'];read=fr['read']
 if not read:continue
 periods=np.diff(rt[k:k+N]);profiles.append(periods)
 for j in range(N-1):
  # Low phase before rise j, high phase after it. Exclude packet gap before j=0.
  fp=np.searchsorted(ft,rt[k+j])-1;fn=fp+1
  if fp<0 or fn>=len(ft):continue
  group='request' if j<8 else ('ack' if j in (9,10,11) else ('data' if 12<=j<44 else None))
  if j==44:group='parity_to_turn'
  if group:
   groups[group]['period'].append(periods[j])
   groups[group]['high'].append(ft[fn]-rt[k+j])
   groups[group]['low'].append(rt[k+j+1]-ft[fn])
  category='host_request' if 1<=j<8 else ('target_ack' if j in (10,11) else ('target_data' if 13<=j<=44 else None))
  if category:
   # Associate a data transition with the nearest launch fall; only count
   # transitions within a half-cycle. Stable bits have no measurable tCO.
   f0=ft[fp];left=np.searchsorted(dt,f0-9);right=np.searchsorted(dt,f0+9)
   if right>left:
    near=dt[left:right];v=float(near[np.argmin(abs(near-f0))]-f0)
    delays[category].append(v)
  if 13<=j<=44 and bits[k+j]!=bits[k+j-1]:
   # The target changes SWDIO on a rising SWCLK edge (ADIv5 B4.3.1).
   # Locate the final transition establishing the next sampled bit; retain
   # its observed delay from the preceding rise, including probe skew.
   l=np.searchsorted(dt,rt[k+j-1],side='right');r=np.searchsorted(dt,rt[k+j])
   candidates=dx[l:r]
   candidates=candidates[di[candidates]==bits[k+j]]
   if len(candidates):target_rise_delays.append(float(t[candidates[-1]]-rt[k+j-1]))
result={'csv':str(args.csv),'valid_read_frames':len(profiles),'resolution_ns':2,
        'analysis_only_filter_ns':args.deglitch_ns,'removed_returning_pulses':removed,
        'decoded_read_words':dict(words.most_common(8)),
        'target_change_after_preceding_rise_ns':stat(target_rise_delays),
        'consecutive_valid_frame_start_ns':stat([rt[b['k']]-rt[a['k']] for a,b in zip(frames,frames[1:]) if b['k']==a['k']+N and rt[b['k']]-rt[a['k']]<3000]),
        'units':'ns; DIO relative to nearest SWCLK launch falling edge',
        'stages':{g:{n:stat(v) for n,v in x.items()} for g,x in groups.items()},
        'visible_DIO_launch_delay':{g:stat(v) for g,v in delays.items()},
        'median_cycle_profile_ns':np.median(profiles,axis=0).tolist()}
args.csv.with_name(args.csv.stem+tag+'.micro.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
# Pick an AP read preceded by a full idle gap, and show the entire word plus launch zoom.
fr=next((f for f in frames if f['read'] and f['ap']),frames[0]);k=fr['k'];origin=rt[k]-10
fig,axs=plt.subplots(3,1,figsize=(14,8),gridspec_kw={'height_ratios':[2,1.4,1.4]})
plt.rcParams['font.family']='DejaVu Sans'
lo=np.searchsorted(t,origin-10);hi=np.searchsorted(t,rt[k+N-1]+30)
for channel,base,color,label in [(cl,1.5,'#9b59b6','SWCLK'),(di,0,'#228be6','SWDIO')]:
 axs[0].step(t[lo:hi]-origin,base+channel[lo:hi]*.7,where='post',color=color,label=label)
for start,end,label,color in [(0,8,'Request','#dbeafe'),(8,9,'TA','#f1f3f5'),(9,12,'ACK','#ffedd5'),(12,44,'Read data','#ffedd5'),(44,45,'P','#ffedd5'),(45,N,'TA','#f1f3f5')]:
 x0=rt[k+start]-origin-10;x1=(rt[k+end]-origin-10) if end<N else rt[k+N-1]-origin+10
 axs[0].axvspan(x0,x1,color=color,alpha=.55,zorder=-5)
 axs[0].text((x0+x1)/2,2.35,label,ha='center',fontsize=9)
axs[0].set_yticks([.35,1.85],['SWDIO','SWCLK']);axs[0].set_ylim(-.2,2.65)
axs[0].set_xlim(0,rt[k+N-1]-origin+25);axs[0].set_xlabel('Time from frame start (ns)')
prof=np.array(profiles)
axs[1].bar(np.arange(N-1),np.median(prof,axis=0),color='#1971c2')
axs[1].axhline(20,color='#d9480f',ls='--',label='20 ns = 50 MHz')
axs[1].set_xticks([0,7,8,9,11,12,31,43,44]);axs[1].set_ylabel('Rise-to-rise period (ns)')
axs[1].set_xlabel('Bit index: request 0-7, TA 8, ACK 9-11, data 12-43, parity 44');axs[1].legend(loc='upper left')
for label,v in delays.items():
 if v:axs[2].hist(v,bins=np.arange(-10,12,2),alpha=.55,label=label)
axs[2].set_xlabel('Visible SWDIO transition - nearest SWCLK falling edge (ns)')
axs[2].set_ylabel('Transition count');axs[2].legend()
fig.suptitle(args.csv.stem+tag+' | 500 MS/s, 2 ns resolution | digital probe measurements',fontsize=13)
fig.tight_layout();fig.savefig(args.csv.with_name(args.csv.stem+tag+'.micro.png'),dpi=160);plt.close(fig)
