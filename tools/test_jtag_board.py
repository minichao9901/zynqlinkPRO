"""F103CB JTAG acceptance: IDCODE, AP memory and block read/write, SRAM restore."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time
import usb.util

from dap_pipeline_bench import open_dap,setup,cmd
from test_probe_board import Memory,stop
from probe_stream import Probe
from benchmark_rtt_forward import DHCSR

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speeds',default='1000000,10000000,30000000,50000000,60000000')
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    p=Probe();dev,out,inp=open_dap();m=Memory(out,inp)
    saved=initial=None;report={'transport':'jtag','rows':[]}
    try:
        stop(p,dev)
        for hz in map(int,a.speeds.split(',')):
            reply=setup(out,inp,hz//1000,'jtag')
            idcode=int.from_bytes(reply[2:6],'little')
            assert idcode not in (0,0xffffffff),hex(idcode)
            if saved is None:
                initial=m.word(DHCSR);m.write_word(DHCSR,0xa05f0003)
                saved=m.read(0x20004000,4096)
                a.output.with_suffix('.backup.bin').write_bytes(saved)
                report['backup_sha256']=hashlib.sha256(saved).hexdigest()
            pattern=random.Random(0x4a544147).randbytes(4096)
            m.write(0x20004000,pattern)
            t=time.perf_counter()
            for i in range(20):
                assert m.read(0x20004000,4096)==pattern
                assert m.read(0x200043f1,1301)==pattern[0x3f1:0x3f1+1301]
            row={'clock_hz':hz,'idcode':hex(idcode),'bytes_verified':20*(4096+1301),
                 'read_MB_s_including_USB_commands':20*(4096+1301)/(time.perf_counter()-t)/1e6}
            state=cmd(out,inp,[0x80,255]);timing=cmd(out,inp,[0x89,255])
            row.update(actual_fclk_hz=int.from_bytes(state[4:8],'little'),sampling_mode=timing[2])
            row['actual_tck_hz']=row['actual_fclk_hz']//2
            report['rows'].append(row);print(json.dumps(row),flush=True)
    finally:
        try:
            if saved is not None:
                setup(out,inp,1000,'jtag');m.write(0x20004000,saved)
                report['restore_match']=m.read(0x20004000,4096)==saved
                assert report['restore_match']
                if initial is not None and not initial&(1<<17):m.write_word(DHCSR,0xa05f0001)
        finally:
            a.output.write_text(json.dumps(report,indent=2));p.close()
            usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)

if __name__=='__main__':main()
