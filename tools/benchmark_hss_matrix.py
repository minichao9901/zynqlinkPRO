"""Single-u32 HSS saturation and zero-skip frontier; accepted firmware unchanged."""
import argparse,hashlib,json,math,statistics
from pathlib import Path
import usb.util
from dap_pipeline_bench import open_dap,setup
from probe_stream import Probe
from benchmark_probe_stream import hss_point
from test_probe_board import Memory,stop
from test_swd_lowfreq_board import recover
from probe_build_info import provenance


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=1)
    p.add_argument('--transports',default='swd,jtag')
    p.add_argument('--speeds',default='1000000,10000000,25000000,35000000,50000000,60000000')
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    d,o,i=open_dap();probe=Probe();mem=Memory(o,i);backup=initial=None
    report=dict(artifacts=provenance(a.bit,a.elf),variables=1,variable_bytes=4,rows=[],summary=[])
    def persist():a.output.write_text(json.dumps(report,indent=2)+'\n')
    try:
        stop(probe,d);setup(o,i,50000);initial=mem.word(0xe000edf0)
        if not initial&(1<<17):mem.write_word(0xe000edf0,0xa05f0003)
        backup=mem.read(0x20004000,4096);assert mem.read(0x20004000,4096)==backup
        a.output.with_suffix('.backup.bin').write_bytes(backup)
        report.update(backup_sha256=hashlib.sha256(backup).hexdigest(),RCC_before=[mem.word(0x40021000),mem.word(0x40021004)])
        for transport in a.transports.split(','):
            assert probe.action(0x31,12,bytes([1 if transport=='swd' else 2]))[0]==0
            for speed in map(int,a.speeds.split(',')):
                current=[]
                def point(period,tag,seconds=None):
                    setup(o,i,50000,'swd')
                    row=hss_point(probe,mem,d,speed,period,1,seconds or a.seconds,len(current),True,
                                  lambda:setup(o,i,50000,transport),True)
                    row.update(transport=transport,stage=tag,passed=True)
                    current.append(row);report['rows'].append(row);persist()
                    print(json.dumps({k:row[k] for k in ['transport','speed_hz','period_ticks','effective_Hz','skip_percent','stage','actual_link_Hz']}),flush=True)
                    return row
                periods=sorted({max(24,math.ceil(24000000*den/speed)) for den in [512,256,192,160,128,96,80,64,48,32]}|{24},reverse=True)
                for period in periods:point(period,'coarse')
                zero=[v for v in current if v['skipped']==0]
                if zero:
                    good=min(v['period_ticks'] for v in zero)
                    bad=max([v['period_ticks'] for v in current if v['skipped']>0 and v['period_ticks']<good],default=24)
                    for _ in range(7):
                        if good-bad<=1:break
                        mid=(good+bad)//2;v=point(mid,'refine')
                        if v['skipped']==0:good=mid
                        else:bad=mid
                    verified=[]
                    for attempt in range(5):
                        verified=[point(good,'verify_zero',2) for _ in range(3)]
                        if all(v['skipped']==0 for v in verified):break
                        good=math.ceil(good*1.025)
                    stable=all(v['skipped']==0 for v in verified)
                else:stable=False;good=None
                best=max(current,key=lambda v:v['effective_Hz'])
                repeats=[best]+[point(best['period_ticks'],'verify_peak',2) for _ in range(2)]
                summary=dict(transport=transport,requested_Hz=speed,actual_link_Hz=best['actual_link_Hz'],
                             max_effective_Hz=statistics.median(v['effective_Hz'] for v in repeats),
                             peak_requested_sample_Hz=best['requested_Hz'],peak_period_ticks=best['period_ticks'],
                             peak_skip_percent=statistics.median(v['skip_percent'] for v in repeats),
                             highest_verified_zero_skip_Hz=best['period_clock_Hz']/good if stable else None,
                             zero_period_ticks=good if stable else None,zero_verification_runs=3 if stable else 0,
                             all_data_frames_verified=True,all_sample_counts_match=True,
                             control_sequence_errors=sum(len(v.get('control_sequence_errors',[])) for v in current))
                report['summary'].append(summary);persist();print('SUMMARY '+json.dumps(summary),flush=True)
        report['RCC_after']=[mem.word(0x40021000),mem.word(0x40021004)]
        assert report['RCC_before']==report['RCC_after']
    except BaseException as exc:report['failure']=repr(exc);raise
    finally:
        try:
            try:stop(probe,d)
            except RuntimeError:recover(d,i);stop(probe,d)
            setup(o,i,50000,'swd')
            if backup is not None:
                mem.write(0x20004000,backup);report['restore_match']=mem.read(0x20004000,4096)==backup;assert report['restore_match']
            if initial is not None and not initial&(1<<17):mem.write_word(0xe000edf0,0xa05f0001)
        finally:persist();probe.close();usb.util.release_interface(d,0);usb.util.dispose_resources(d)


if __name__=='__main__':main()
