"""Verify matched HSS periods on one loaded H743 probe pair; no frontier search."""
import argparse
import hashlib
import json
from pathlib import Path

import usb.util
from benchmark_probe_stream import hss_point
from dap_pipeline_bench import open_dap, setup
from probe_build_info import provenance
from probe_stream import Probe
from target_snapshot import snapshot
from test_probe_board import Memory, stop
from test_swd_lowfreq_board import recover


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--points',default='swd:50000000:25,swd:60000000:24,jtag:50000000:89,jtag:60000000:74',help='transport:Hz:period_ticks, comma separated')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    d,o,i=open_dap();probe=Probe();mem=Memory(o,i);backup=initial=None
    report=dict(artifacts=provenance(a.bit,a.elf),rows=[])
    def save():(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    try:
        stop(probe,d);setup(o,i,1000);initial=mem.word(0xe000edf0)
        mem.write_word(0xe000edf0,0xa05f0003)
        backup=mem.read(0x20004000,4096);(a.out/'backup.bin').write_bytes(backup)
        report.update(backup_sha256=hashlib.sha256(backup).hexdigest(),target_before=snapshot(mem))
        assert (int(report['target_before']['cpuid'],16)>>4)&0xfff==0xc27
        for point in a.points.split(','):
            transport,speed,period=point.split(':');speed,period=int(speed),int(period)
            assert transport in ('swd','jtag') and period>=24
            assert probe.action(0x31,12,bytes([1 if transport=='swd' else 2]))[0]==0
            for repeat in range(3):
                setup(o,i,1000)
                row=hss_point(probe,mem,d,speed,period,1,2,repeat,True,
                              lambda:setup(o,i,1000,transport,jtag_ir_lengths=(4,5)),True)
                row['transport']=transport;report['rows'].append(row);save()
                assert row['skipped']==0 and abs(row['actual_link_Hz']-speed)<10,row
                print(transport,speed,period,repeat,'PASS',flush=True)
        report['passed']=True
    except BaseException as exc:report['failure']=repr(exc);raise
    finally:
        try:
            stop(probe,d);recover(d,i);setup(o,i,1000)
            if backup is not None:
                mem.write(0x20004000,backup);report['restore_match']=mem.read(0x20004000,4096)==backup
                assert report['restore_match']
            report['target_after']=snapshot(mem)
            assert report.get('target_before',report['target_after'])==report['target_after']
            if initial is not None and not initial&(1<<17):mem.write_word(0xe000edf0,0xa05f0001)
        finally:save();probe.close();usb.util.dispose_resources(d)


if __name__=='__main__':main()
