"""HSS end-to-end with a running F103CB SRAM counter, full RAM/register restore."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import time

import numpy as np
import usb.util

from benchmark_probe_stream import HssReader
from benchmark_rtt_forward import core_read,core_write,DHCSR
from dap_pipeline_bench import open_dap,setup
from probe_build_info import provenance
from probe_stream import Probe
from test_probe_board import Memory,stop,drain_hss


class CounterReader(HssReader):
    def __init__(self,dev,period):
        super().__init__(dev,b'\0'*4,period)
        self.last_value=None
        self.changes=0

    def validate_values(self,data,n,seq,stamp):
        values=np.frombuffer(data,dtype='<u4')
        assert len(values)==n
        delta=np.diff(values)
        assert np.all(delta<0x80000000),('backwards/stale counter',seq,stamp)
        if self.last_value is not None:
            assert ((int(values[0])-self.last_value)&0xffffffff)<0x80000000,('packet counter order',seq)
        self.changes+=int(np.count_nonzero(delta))
        self.last_value=int(values[-1])


def point(p,mem,dev,code,speed,period,seconds):
    mem.write_word(DHCSR,0xa05f0003)
    mem.write(0x20000000,code)
    mem.write_word(0x20004000,0)
    core_write(mem,16,0x01000000);core_write(mem,20,1);core_write(mem,15,0x20000001)
    assert p.action(0x32,3,struct.pack('<I',speed))[0]==0
    cfg=struct.pack('<IBBIBB',period,0,1,0x20004000,4,4)
    assert p.action(0x32,10,cfg)[0]==0
    drain_hss(dev)
    r=CounterReader(dev,period);r.start()
    try:
        # Start the producer before sampling: no halted constant prefix.
        mem.write_word(DHCSR,0xa05f0001)
        assert p.action(0x32,1)[0]==0
        time.sleep(.25)
        rc,m0=p.action(0x32,11);assert rc==0,(rc,m0)
        time.sleep(seconds)
        rc,m1=p.action(0x32,11);assert rc==0,(rc,m1)
        for _ in range(100):
            rc,_=p.action(0x32,0)
            if rc==0:break
            assert rc==-7,rc
            if r.error:raise RuntimeError(r.error)
            time.sleep(.01)
        else:raise RuntimeError('HSS STOP timeout')
        time.sleep(.12);r.quit.set();r.join(2)
        assert not r.is_alive() and r.error is None,r.error
        drain_hss(dev,r.consume)
        rc,final=p.action(0x32,11)
        assert rc==0 and r.samples==final[3],(r.samples,final)
        assert r.changes>r.samples*.9,(r.changes,r.samples)
        delta=[(b-a)&0xffffffff for a,b in zip(m0,m1)]
        dt=delta[1]/24e6
        assert delta[6]==0,delta
        return dict(speed_hz=speed,period_ticks=period,requested_Hz=24e6/period,
                    effective_Hz=delta[3]/dt,produced=delta[3],skipped=delta[4],
                    skip_percent=100*delta[4]/(delta[3]+delta[4]),counter_window_s=dt,
                    session_samples=r.samples,changed_adjacent_values=r.changes,
                    timeline_skipped=r.timeline_skips,all_counter_values_ordered=True,
                    sample_count_match=True,swd_errors=delta[6],m0=m0,m1=m1,final=final)
    finally:
        p.action(0x32,0);r.quit.set();r.join(2)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed',type=int,default=60000000)
    ap.add_argument('--periods',default='48,40,32,24')
    ap.add_argument('--seconds',type=float,default=2)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--bit',type=Path);ap.add_argument('--elf',type=Path)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    build=root/'build/hss_ram';build.mkdir(parents=True,exist_ok=True)
    gcc=Path(shutil.which('arm-none-eabi-gcc'))
    objcopy=gcc.with_name('arm-none-eabi-objcopy.exe' if gcc.suffix=='.exe' else 'arm-none-eabi-objcopy')
    subprocess.run([str(gcc),'-mcpu=cortex-m3','-mthumb','-nostdlib','-Wl,-Ttext=0x20000000','-Wl,-e,producer',
                    str(root/'firmware/target/probe_hss_ram.S'),'-o',str(build/'producer.elf')],check=True)
    subprocess.run([str(objcopy),'-O','binary',str(build/'producer.elf'),str(build/'producer.bin')],check=True)
    code=(build/'producer.bin').read_bytes()
    p=Probe();dev,out,inp=open_dap();mem=Memory(out,inp)
    backup=regs=initial=None
    report=dict(artifacts=provenance(a.bit,a.elf),kind='running F103CB counter HSS',rows=[])
    try:
        stop(p,dev);setup(out,inp,50000)
        initial=mem.word(DHCSR);mem.write_word(DHCSR,0xa05f0003)
        regs={i:core_read(mem,i) for i in list(range(19))+[20]}
        backup=mem.read(0x20000000,20480);a.output.with_suffix('.backup.bin').write_bytes(backup)
        report.update(backup_sha256=hashlib.sha256(backup).hexdigest(),registers_before=regs,
                      RCC_before=[mem.word(0x40021000),mem.word(0x40021004)])
        for period in map(int,a.periods.split(',')):
            row=point(p,mem,dev,code,a.speed,period,a.seconds);report['rows'].append(row)
            a.output.write_text(json.dumps(report,indent=2))
            print(json.dumps({k:v for k,v in row.items() if k not in ('m0','m1','final')}),flush=True)
    finally:
        try:
            stop(p,dev);setup(out,inp,50000);mem.write_word(DHCSR,0xa05f0003)
            if backup is not None:
                mem.write(0x20000000,backup);report['restore_match']=mem.read(0x20000000,20480)==backup
                assert report['restore_match']
            if regs is not None:
                for i,v in regs.items():core_write(mem,i,v)
                report['registers_after']={i:core_read(mem,i) for i in regs}
                report['registers_match']=report['registers_after']==regs
                assert report['registers_match']
            report['RCC_after']=[mem.word(0x40021000),mem.word(0x40021004)]
            assert report.get('RCC_before',report['RCC_after'])==report['RCC_after']
            if initial is not None and not initial&(1<<17):mem.write_word(DHCSR,0xa05f0001)
        finally:
            a.output.write_text(json.dumps(report,indent=2));p.close()
            usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)


if __name__=='__main__':main()
