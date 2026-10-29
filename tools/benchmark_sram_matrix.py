"""Verified 1KiB sequential/pipelined SRAM throughput with complete restoration."""
import argparse,hashlib,json,random,statistics,struct,time
from pathlib import Path
import usb.util
from dap_pipeline_bench import open_dap,setup,send,xfer,block_read_req
from test_probe_board import Memory
from test_swd_lowfreq_board import recover
from probe_build_info import provenance,swd_clock_details
from probe_stream import Probe
from test_probe_board import stop


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--output',type=Path,required=True)
    a.add_argument('--bit',type=Path,required=True);a.add_argument('--elf',type=Path,required=True)
    a.add_argument('--seconds',type=float,default=.4);a.add_argument('--repeats',type=int,default=3)
    a.add_argument('--transport',choices=['both','swd','jtag'],default='both')
    args=a.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    d,o,i=open_dap();p=Probe();m=Memory(o,i);saved=initial=None;base=0x20004000
    report=dict(artifacts=provenance(args.bit,args.elf),block_bytes=1024,pipeline_depth=4,rows=[])
    pattern=random.Random(0x20261029).randbytes(1024)
    def run(mode,loops):
        m.address(base);req=block_read_req(256) if mode.startswith('read') else bytes([6,0,0,1,13])+pattern
        depth=1 if mode=='read_seq' else 4
        t=time.perf_counter()
        for k in range(0,loops,depth):
            n=min(depth,loops-k)
            for _ in range(n):send(o,req)
            for _ in range(n):
                reply=bytes(i.read(4096,timeout=5000))
                assert reply[:4]==b'\x06\x00\x01\x01',reply[:16].hex()
                if mode.startswith('read'):assert reply[4:]==pattern,'read data mismatch'
                else:assert len(reply)==4,reply.hex()
        dt=time.perf_counter()-t
        if mode=='write_pipe':assert m.read(base,4096)==pattern*4,'write readback mismatch'
        return dt
    try:
        stop(p,d);setup(o,i,50000);initial=m.word(0xe000edf0)
        if not initial&(1<<17):m.write_word(0xe000edf0,0xa05f0003)
        report['RCC_before']=[m.word(0x40021000),m.word(0x40021004)]
        saved=m.read(base,4096);assert m.read(base,4096)==saved
        args.output.with_suffix('.backup.bin').write_bytes(saved)
        report['backup_sha256']=hashlib.sha256(saved).hexdigest()
        transports=['swd','jtag'] if args.transport=='both' else [args.transport]
        for transport in transports:
            for khz in [1000,10000,25000,35000,50000,60000]:
                row=dict(transport=transport,requested_Hz=khz*1000,passed=False)
                try:
                    setup(o,i,khz,transport)
                    diag=xfer(o,i,[0x80,255]);hz,cfg=struct.unpack_from('<II',diag,4)
                    row.update(FCLK_Hz=hz,cfg=hex(cfg),waveform=swd_clock_details(hz,cfg))
                    row['actual_link_Hz']=row['waveform']['SWCLK_Hz']
                    if transport=='jtag':row['JTAG_sampling_mode']=xfer(o,i,[0x89,255])[2]
                    m.write(base,pattern*4);assert m.read(base,4096)==pattern*4
                    # Discover the actual MEM-AP wrap rather than assuming
                    # its architectural minimum 1KiB is the device's wrap.
                    m.address(base)
                    for n in range(4):
                        reply=xfer(o,i,block_read_req(256))
                        assert reply[:4]==b'\x06\x00\x01\x01' and reply[4:]==pattern
                        if n in (0,3):
                            tar=xfer(o,i,[5,0,2,7,14]);assert tar[:3]==b'\x05\x02\x01',tar.hex()
                            # JTAG AP reads return current data; SWD AP reads
                            # are posted and need the following RDBUFF value.
                            value=tar[3:7] if transport=='jtag' else tar[-4:]
                            row['TAR_after_'+str(n+1)+'KiB']=hex(int.from_bytes(value,'little'))
                    assert row['TAR_after_4KiB']==hex(base),'TAR would leave the backed-up 4KiB window'
                    for mode in ['read_seq','read_pipe','write_pipe']:
                        warm=run(mode,8);loops=max(32,min(4096,int(args.seconds*8/max(warm,.00001))))
                        loops=((loops+3)//4)*4
                        times=[run(mode,loops) for _ in range(args.repeats)]
                        rates=[loops*1024/v/1e6 for v in times]
                        row[mode]=dict(MB_s=statistics.median(rates),repeats_MB_s=rates,loops=loops,
                                       bytes_per_repeat=loops*1024,seconds=times)
                    row['passed']=True
                except Exception as exc:row['error']=repr(exc)
                finally:
                    recover(d,i);setup(o,i,50000)
                    m.write(base,saved);row['restore_match']=m.read(base,4096)==saved
                    assert row['restore_match']
                    report['rows'].append(row);args.output.write_text(json.dumps(report,indent=2)+'\n')
                    print(json.dumps(row),flush=True)
        report['RCC_after']=[m.word(0x40021000),m.word(0x40021004)]
        assert report['RCC_before']==report['RCC_after']
    except BaseException as exc:report['fatal_error']=repr(exc);raise
    finally:
        try:
            recover(d,i);setup(o,i,50000)
            if saved is not None:
                m.write(base,saved);report['restore_match']=m.read(base,4096)==saved;assert report['restore_match']
            if initial is not None and not initial&(1<<17):m.write_word(0xe000edf0,0xa05f0001)
        finally:
            args.output.write_text(json.dumps(report,indent=2)+'\n');p.close()
            usb.util.release_interface(d,0);usb.util.dispose_resources(d)
    assert len(report['rows'])==6*len(transports) and all(v['passed'] for v in report['rows'])


if __name__=='__main__':main()
