"""AI-only physical-input delay control; no target clocks, SRAM or Flash writes.

ELD1 is an explicit capability. A command changes five IDELAY taps only while
both capture paths are idle, sends once, and requires an acknowledged readback.
The access path is Zynq physical MEM-AP0, independent of CPU caches and USB.
"""
import argparse
import json
from pathlib import Path
import re

BASE=0x40030000
SIGNATURE=0x454c4431


def payload(enabled,taps):
    if type(enabled) is not bool or len(taps)!=5 or any(type(v) is not int or not 0<=v<=31 for v in taps):
        raise ValueError('Requires boolean enabled and five taps 0..31 (D0,D1,D2,D3,CLK)')
    return (int(enabled)<<25)|sum(v<<(5*i) for i,v in enumerate(taps))


def decode(words):
    if len(words)!=6 or words[0]!=SIGNATURE:raise ValueError('Loaded bitstream does not advertise ELD1 input delays')
    if words[1]&0xfc000000 or words[2]&~63:raise ValueError('Unknown ELD1 register layout')
    config,status=words[1:3]
    return dict(enabled=bool(config&(1<<25)),taps=[(config>>(5*i))&31 for i in range(5)],
        busy=bool(status&2),ready=bool(status&4),loaded=bool(status&8),fault=bool(status&16),
        rejectedSticky=bool(status&32),accepted=words[3],rejected=words[4],loadFailures=words[5],raw=words)


class LaneDelay:
    def __init__(self,memory):self.memory=memory
    def snapshot(self):return decode(self.memory.read_words(BASE+0x50,6))
    def configure(self,enabled,taps):
        desired=payload(enabled,taps)
        # Validate again inside the same XSCT transaction, then write exactly
        # once. Waiting is observation, never command replay or auto recovery.
        body=f'''
set before [physrd -force -value 0x40030050 6]
if {{[lindex $before 0] != {SIGNATURE}}} {{error "ELD1 capability missing; no write"}}
if {{!([physrd -force -value 0x40030048] & 0x100)}} {{error "DDR CSR not advertised; no write"}}
if {{([physrd -force -value 0x40030004] & 1) || ([physrd -force -value 0x40040008] & 1)}} {{error "Capture active; no tap write"}}
if {{([lindex $before 2] & 2) || !([physrd -force -value 0x40030008] & 8)}} {{error "Pending tap load or IDELAYCTRL not ready; no write"}}
physwr -force 0x40030054 {0xb4000000|desired:#x}
set done 0
for {{set attempt 0}} {{$attempt < 100}} {{incr attempt}} {{
 set current [physrd -force -value 0x40030050 6]
 if {{[lindex $current 4] != [lindex $before 4]}} {{error "Hardware rejected tap command; no replay"}}
 if {{[lindex $current 3] == (([lindex $before 3]+1)&0xffffffff) && !([lindex $current 2]&2)}} {{set done 1;break}}
 after 1
}}
if {{!$done}} {{error "Tap acknowledge timeout; no replay"}}
if {{[lindex $current 1] != {desired} || ([lindex $current 2]&0x1c)!=0x0c || [lindex $current 5] != [lindex $before 5]}} {{error "Tap readback/load failed"}}
puts "ELD_BEFORE $before"
puts "ELD_AFTER $current"
'''
        output=self.memory.run(body)
        def row(marker):
            match=re.search(marker+r' ([^\r\n]+)',output)
            if not match:raise RuntimeError('No acknowledged ELD1 result')
            return decode([int(v,0) for v in match[1].split()])
        before,after=row('ELD_BEFORE'),row('ELD_AFTER')
        if after['enabled']!=enabled or after['taps']!=list(taps) or not after['ready'] or not after['loaded'] or after['fault']:
            raise RuntimeError('ELD1 response did not confirm the requested taps')
        if after['accepted']!=(before['accepted']+1)&0xffffffff or after['rejected']!=before['rejected'] or after['loadFailures']!=before['loadFailures']:
            raise RuntimeError('ELD1 transaction counters did not match')
        return dict(before=before,after=after)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('status','set'))
    p.add_argument('--enabled',type=int,choices=(0,1));p.add_argument('--taps',help='D0,D1,D2,D3,CLK; each 0..31')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--sdk',type=Path,default=Path('E:/Xilinx/SDK/2018.3'))
    p.add_argument('--url',default='tcp:127.0.0.1:3121');a=p.parse_args()
    taps=None
    if a.action=='set':
        if a.enabled is None or a.taps is None:p.error('set requires --enabled and --taps')
        try:taps=[int(v) for v in a.taps.split(',')];payload(bool(a.enabled),taps)
        except ValueError as e:p.error(str(e))
    elif a.enabled is not None or a.taps is not None:p.error('status does not accept set arguments')
    a.out.mkdir(parents=True,exist_ok=False)
    from probe_flash import Session
    from zynq_memory import PhysicalMemory
    interface=LaneDelay(PhysicalMemory(Session(a.out,a.sdk,a.url)))
    report=dict(hardwareAccess=True,targetClockWrites=False,flashWrites=False,requested=dict(enabled=a.enabled,taps=taps))
    try:
        report['result']=interface.snapshot() if a.action=='status' else interface.configure(bool(a.enabled),taps)
        report['passed']=True
    except Exception as e:report.update(passed=False,error=str(e));raise
    finally:(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
