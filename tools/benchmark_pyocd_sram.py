"""Measure unmodified pyOCD SRAM APIs, bypass caches, verify and restore data."""
import argparse
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
import random
import struct
import time

from pyocd.core.helpers import ConnectHelper

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed',type=int,default=60000,help='SWCLK kHz')
    ap.add_argument('--loops',type=int,default=100)
    ap.add_argument('--sessions',type=int,default=3)
    ap.add_argument('--size',type=int,default=20480)
    ap.add_argument('--api',choices=['32','8'],default='32')
    ap.add_argument('--limit-packets',action='store_true')
    ap.add_argument('--uid',default='12345678')
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    if not 0<a.size<=20480 or a.size%4 or a.loops<1 or a.sessions<1:
        ap.error('Use an aligned 1..20KiB window and positive session/loop counts')
    logging.basicConfig(level=logging.WARNING)
    options={'target_override':'cortex_m','frequency':a.speed*1000,
             'connect_mode':'attach','resume_on_disconnect':False,'auto_unlock':False,
             'cache.enable_memory':False,'cache.enable_register':False,
             'cache.read_code_from_elf':False,'no_config':True,
             'cmsis_dap.limit_packets':a.limit_packets}
    result={'pyocd_version':importlib.metadata.version('pyocd'),'options':options,
            'size_bytes':a.size,'loops':a.loops,'api':a.api,'sessions':[]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    pattern=random.Random(0x20261026).randbytes(a.size)
    values=list(struct.unpack('<'+'I'*(a.size//4),pattern)) if a.api=='32' else list(pattern)
    try:
        for index in range(a.sessions):
            session=ConnectHelper.session_with_chosen_probe(unique_id=a.uid,options=options)
            if session is None:raise RuntimeError('DAP probe not found')
            with session:
                target=session.target
                target.halt();target.flush()
                before=[target.read32(0x40021000),target.read32(0x40021004)]
                assert target.read32(0xe000edf0)&(1<<17),'Target did not halt'
                reader=target.read_memory_block32 if a.api=='32' else target.read_memory_block8
                writer=target.write_memory_block32 if a.api=='32' else target.write_memory_block8
                read_count=a.size//4 if a.api=='32' else a.size
                original=list(reader(0x20000000,read_count))
                original_bytes=struct.pack('<'+'I'*len(original),*original) if a.api=='32' else bytes(original)
                a.output.with_name(a.output.stem+f'.session{index}.backup.bin').write_bytes(original_bytes)
                row={'session':index,'packet_size':session.probe._link._packet_size,
                     'packet_count':session.probe._link._packet_count,
                     'AP_wrap_bytes':[v.auto_increment_page_size for v in target.aps.values()],
                     'RCC_before':[hex(x) for x in before],
                     'backup_sha256':hashlib.sha256(original_bytes).hexdigest()}
                try:
                    writer(0x20000000,values);target.flush()
                    assert list(reader(0x20000000,read_count))==values,'Warmup SRAM mismatch'
                    t0=time.perf_counter()
                    for _ in range(a.loops):
                        got=reader(0x20000000,read_count)
                        assert list(got)==values,'Timed SRAM read mismatch'
                    read_s=time.perf_counter()-t0
                    t0=time.perf_counter()
                    for _ in range(a.loops):
                        writer(0x20000000,values)
                        target.flush()  # Include completion rather than timing queued writes only.
                    write_s=time.perf_counter()-t0
                    assert list(reader(0x20000000,read_count))==values,'Final SRAM write mismatch'
                    row.update(read_s=read_s,write_s=write_s,
                               read_MB_s=a.size*a.loops/read_s/1e6,
                               write_MB_s=a.size*a.loops/write_s/1e6,data_match=True)
                finally:
                    writer(0x20000000,original);target.flush()
                    row['restore_match']=list(reader(0x20000000,read_count))==original
                    row['RCC_after']=[hex(target.read32(0x40021000)),hex(target.read32(0x40021004))]
                    assert row['restore_match'],'SRAM restoration mismatch'
                    assert row['RCC_after']==row['RCC_before'],'Target clock changed'
                    result['sessions'].append(row)
                    print(json.dumps(row),flush=True)
        total=a.size*a.loops*a.sessions
        result['read_MB_s']=total/sum(x['read_s'] for x in result['sessions'])/1e6
        result['write_MB_s']=total/sum(x['write_s'] for x in result['sessions'])/1e6
        print('TOTAL',result['read_MB_s'],result['write_MB_s'],flush=True)
    except BaseException as exc:
        result['error']=str(exc)
        raise
    finally:
        a.output.write_text(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
