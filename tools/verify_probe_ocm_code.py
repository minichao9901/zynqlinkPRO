"""Compare a running probe's OCM code to ELF without downloading or resetting it."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import struct

from probe_flash import Session


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True,help='new directory; never overwrite prior evidence')
    p.add_argument('--require-qspi',action='store_true')
    p.add_argument('--usb-config-cycles',type=int,default=0)
    p.add_argument('--sdk',type=Path,default=Path('E:/Xilinx/SDK/2018.3'))
    a=p.parse_args()
    if not 0<=a.usb_config_cycles<=10:p.error('USB cycles must be between 0 and 10')
    blob=a.elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',blob)
    if h[0][:6]!=b'\x7fELF\x01\x01' or h[2]!=40:p.error('Expected little-endian ARM ELF32')
    all_sections=[struct.unpack_from('<10I',blob,h[6]+i*h[11]) for i in range(h[12])]
    string=all_sections[h[13]];names=blob[string[4]:string[4]+string[5]]
    sections=[s for s in all_sections if s[1]==1 and s[2]&6==6 and s[5]]
    if not sections or any(s[3]+s[5]>0x30000 for s in sections):p.error('Executable sections must be in low OCM')
    end=max(s[3]+s[5] for s in sections)
    dest=a.out_dir.resolve();dest.mkdir(parents=True,exist_ok=False)
    session=Session(dest,a.sdk,'tcp:127.0.0.1:3121')
    report=dict(time_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),elf=str(a.elf.resolve()),
                elf_sha256=hashlib.sha256(blob).hexdigest(),downloads=False,probe_reset_or_continue=False,
                expected_executable_bytes=sum(s[5] for s in sections),cycles=[],passed=False)
    output=dest/'result.json'
    try:
        report['boot_mode']=session.read_words(0xf800025c)[0]&15
        report['boot_trace']=session.read_words(0x03ff0000,8)
        ctrl=session.read_words(0xf8000170)[0];pll=session.read_words(0xf8000108)[0]
        report['FCLK_CTRL']=ctrl;report['IO_PLL_CTRL']=pll
        report['initial_FCLK_Hz']=33333333*((pll>>12)&127)//((ctrl>>8)&63)//((ctrl>>20)&63)
        if a.require_qspi:
            t=report['boot_trace']
            assert report['boot_mode']==1 and t[0]==0x53544730 and t[3]==1 and t[5:8]==[0x600,0,1],t
        for cycle in range(a.usb_config_cycles+1):
            row=dict(cycle=cycle)
            if cycle:
                from dap_pipeline_bench import open_dap
                import usb.util
                dev,_,_=open_dap()
                try:
                    row['GET_CONFIGURATION_before']=list(dev.ctrl_transfer(0x80,8,0,0,1))
                    dev.ctrl_transfer(0,9,1,0,b'')
                    row['GET_CONFIGURATION_after']=list(dev.ctrl_transfer(0x80,8,0,0,1))
                    assert row['GET_CONFIGURATION_before']==row['GET_CONFIGURATION_after']==[1]
                finally:usb.util.dispose_resources(dev)
            image=dest/f'live_code_{cycle}.bin'
            session.run('mrd -force -bin -file {'+image.as_posix()+f'}} 0 {(end+3)//4}\nputs CODE_READ')
            live=image.read_bytes();diff=[];checked=[]
            for s in sections:
                name=names[s[0]:].split(b'\0',1)[0].decode()
                expected=blob[s[4]:s[4]+s[5]];actual=live[s[3]:s[3]+s[5]]
                assert len(actual)==len(expected)
                diff.extend(s[3]+i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y)
                checked.append(dict(name=name,bytes=s[5],address=s[3],equal=expected==actual,
                    expected_sha256=hashlib.sha256(expected).hexdigest(),live_sha256=hashlib.sha256(actual).hexdigest()))
            row.update(sections=checked,differing_addresses=diff,vector_word=f'{struct.unpack_from("<I",live)[0]:08x}')
            report['cycles'].append(row);output.write_text(json.dumps(report,indent=2)+'\n')
            assert not diff,diff[:16]
        report['passed']=True
    finally:output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
