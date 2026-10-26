"""Real linear SRAM API over standard CMSIS-DAP, with cross-page pipelining.

Each access covers unique addresses, sets TAR at each MEM-AP page and waits for
all responses. No wrap-only throughput, filesystem IO or cached target data is
included in the timed API. The complete original SRAM window is restored.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import time

import usb.util
from dap_pipeline_bench import open_dap,setup,send,xfer,le

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--speed',type=int,default=50000)
ap.add_argument('--size',type=int,default=20480)
ap.add_argument('--loops',type=int,default=100)
ap.add_argument('--sessions',type=int,default=3)
ap.add_argument('--depth',type=int,default=16)
ap.add_argument('--idle',type=int,choices=[0,1,2],default=1)
ap.add_argument('--prefix-words',type=int,choices=[0,2],default=0,
                help='Merge TAR plus two data words in 0x05 to avoid a tail USB command')
ap.add_argument('--output',type=Path,required=True)
a=ap.parse_args()
if not 0<a.size<=20480 or a.size%4 or not 1<=a.depth<=16 or a.loops<1 or a.sessions<1:
    ap.error('Use aligned 1..20480 bytes, depth1..16, positive loop/session counts')
pattern=random.Random(0x20261026).randbytes(a.size)
result={'kind':'linear_SRAM_standard_CMSIS_DAP','speed_kHz':a.speed,'idle':a.idle,'size_bytes':a.size,
        'depth':a.depth,'loops':a.loops,'sessions':[],'page_bytes':4096,'prefix_words':a.prefix_words}
a.output.parent.mkdir(parents=True,exist_ok=True)

def commands(reading,data=None):
    items=[]
    for page in range(0,a.size,4096):
        n=min(a.prefix_words,(a.size-page)//4)
        prefix=bytes([5,0,1+n,5])+struct.pack('<I',0x20000000+page)
        for j in range(n):
            prefix+=b'\x0f' if reading else b'\x0d'+data[page+j*4:page+j*4+4]
        items.append((prefix,page,n,reading and n>0))
        for offset in range(page+n*4,min(page+4096,a.size),4088):
            count=min(4088,page+4096-offset,a.size-offset)//4
            payload=bytes([6,0,count&255,count>>8,15 if reading else 13])
            if not reading:payload+=data[offset:offset+count*4]
            items.append((payload,offset,count,reading))
    return items

try:
 for index in range(a.sessions):
    dev,out,inp=open_dap();original=None;row={'session':index}
    def execute(items):
        reads=[]
        for base in range(0,len(items),a.depth):
            group=items[base:base+a.depth]
            for p,_,_,_ in group:send(out,p)
            for p,offset,count,reading in group:
                r=bytes(inp.read(4096,timeout=5000))
                expected=bytes([5,p[2],1]) if p[0]==5 else bytes([6,count&255,count>>8,1])
                length=len(expected)+(count*4 if reading else 0)
                if r[:len(expected)]!=expected or len(r)!=length:
                    raise RuntimeError(f'CMSIS response offset={offset} command={p[0]:x} bytes={r[:16].hex()} len={len(r)}')
                if reading:reads.append(r[len(expected):])
        return b''.join(reads)
    try:
        setup(out,inp,a.speed)
        assert xfer(out,inp,[4,a.idle,0x40,0,0,0])==bytes([4,0])
        row['configuration']=xfer(out,inp,[0x80,255]).hex()
        row['actual_idle']=(struct.unpack_from('<I',bytes.fromhex(row['configuration']),8)[0]>>4)&15
        assert row['actual_idle']==a.idle,'Firmware clamped requested idle; zero requires an experimental build'
        def read_reg(addr):
            assert xfer(out,inp,[5,0,1,5]+le(addr))==bytes([5,1,1])
            r=xfer(out,inp,[6,0,1,0,15]);assert r[:4]==bytes([6,1,0,1]),r.hex()
            return struct.unpack('<I',r[4:])[0]
        assert read_reg(0xe000edf0)&(1<<17),'Target must already be halted'
        row['RCC_before']=[hex(read_reg(0x40021000)),hex(read_reg(0x40021004))]
        read_commands=commands(True)
        original=execute(read_commands)
        assert len(original)==a.size
        a.output.with_name(a.output.stem+f'.session{index}.backup.bin').write_bytes(original)
        row['backup_sha256']=hashlib.sha256(original).hexdigest()
        writes=commands(False,pattern)
        execute(writes)
        assert execute(read_commands)==pattern,'Warmup data mismatch'
        start=time.perf_counter()
        for _ in range(a.loops):
            assert execute(read_commands)==pattern,'Timed read mismatch'
        read_s=time.perf_counter()-start
        start=time.perf_counter()
        for _ in range(a.loops):execute(writes)
        write_s=time.perf_counter()-start
        assert execute(read_commands)==pattern,'Final written data mismatch'
        row.update(read_s=read_s,write_s=write_s,read_MB_s=a.size*a.loops/read_s/1e6,
                   write_MB_s=a.size*a.loops/write_s/1e6,data_match=True,
                   CMSIS_commands_per_access=len(read_commands))
    finally:
        try:
            if original is not None:
                try:
                    execute(commands(False,original))
                except Exception as restore_error:
                    row['restore_recovery_reason']=str(restore_error)
                    import usb.core
                    for _ in range(64):
                        try:inp.read(4096,timeout=50)
                        except usb.core.USBTimeoutError:break
                    setup(out,inp,a.speed)
                    assert xfer(out,inp,[4,1,64,0,0,0])==bytes([4,0])
                    execute(commands(False,original))
                    row['restore_used_idle1_reconnect']=True
                row['restore_match']=execute(commands(True))==original
                assert row['restore_match'],'Original SRAM restoration mismatch'
                row['RCC_after']=[hex(read_reg(0x40021000)),hex(read_reg(0x40021004))]
                assert row['RCC_before']==row['RCC_after'],'Target clock changed'
        finally:
            usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
            result['sessions'].append(row);print(json.dumps(row),flush=True)
 total=a.size*a.loops*a.sessions
 result['read_MB_s']=total/sum(r['read_s'] for r in result['sessions'])/1e6
 result['write_MB_s']=total/sum(r['write_s'] for r in result['sessions'])/1e6
 print('TOTAL',result['read_MB_s'],result['write_MB_s'])
except BaseException as exc:
 result['error']=str(exc);raise
finally:a.output.write_text(json.dumps(result,indent=2))
