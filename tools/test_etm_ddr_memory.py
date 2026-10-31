"""Load an explicit pilot bit/ELF pair, write a bounded PL pattern, verify DDR.

AI hardware acceptance only. No Flash or target clock writes. DDR contents in
the new ELF's explicit ETM reservation are disposable; other memory is guarded.
JTAG readback is deliberately independent of the future USB download path.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CSR=0x40040000


def reservation(elf):
    from elftools.elf.elffile import ELFFile
    with elf.open('rb') as f:
        image=ELFFile(f);symbols=image.get_section_by_name('.symtab')
        def symbol(name):
            rows=symbols.get_symbol_by_name(name) if symbols else None
            if not rows or rows[0]['st_shndx']!='SHN_ABS':raise ValueError('ELF lacks explicit absolute reservation: '+name)
            return rows[0]['st_value']
        lo,hi=symbol('__etm_ddr_base'),symbol('__etm_ddr_end')
        if (lo,hi)!=(0x10000000,0x30000000):raise ValueError('Unvalidated DDR reservation')
        for section in image.iter_sections():
            address,length=section['sh_addr'],section['sh_size']
            if section['sh_flags']&2 and length and address<hi and lo<address+length:
                raise ValueError('Allocated section overlaps DDR capture: '+section.name)
        return lo,hi


def expected_chunk(offset,count,seed):
    if offset%4:raise ValueError('word-aligned verification chunks required')
    words=array('I',(0xddaa0000 ^ seed ^ (offset//4+i) for i in range((count+3)//4)))
    if sys.byteorder!='little':words.byteswap()
    return words.tobytes()[:count]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--bytes',type=lambda x:int(x,0),default=1048576)
    p.add_argument('--seed',type=lambda x:int(x,0),default=0x13dba917)
    a=p.parse_args(argv);pair=a.pair.resolve();out=a.out.resolve()
    if not 1<=a.bytes<=0x20000000 or not 0<=a.seed<=0xffffffff:p.error('invalid finite byte count or seed')
    for path in [pair,out]:
        if any(c in str(path) for c in '{}\r\n'):p.error('Tcl paths must not contain braces or newlines')
    manifest=json.loads((pair/'manifest.json').read_text(encoding='utf8'))
    for name in ('probe.bit','application.elf','ps7_init.tcl'):
        expected=manifest['files'][name]
        expected=expected['sha256'] if isinstance(expected,dict) else expected
        if hashlib.sha256((pair/name).read_bytes()).hexdigest()!=expected:raise ValueError('Pair hash mismatch: '+name)
    base,end=reservation(pair/'application.elf')
    if base+a.bytes>end:raise ValueError('Test exceeds reservation')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(hardware=True,traceCapture=False,flashWrites=False,source='address-dependent PL pattern',
        pair=str(pair),pairFiles=manifest['files'],base=base,bytes=a.bytes,seed=a.seed,passed=False)
    result=out/'result.json';result.write_text(json.dumps(report,indent=2)+'\n')
    def checked(command,log):
        run=subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=120)
        (out/log).write_text(run.stdout+run.stderr,encoding='utf8')
        if run.returncode:raise RuntimeError('Failed; inspect '+str(out/log))
    checked([sys.executable,str(ROOT/'tools/run_xsct.py'),str(ROOT/'tools/download_dap_fpga.tcl'),
             str(pair/'application.elf'),str(pair/'probe.bit'),str(pair/'ps7_init.tcl')],'load.txt')
    checked([sys.executable,str(ROOT/'tools/verify_probe_ocm_code.py'),'--elf',str(pair/'application.elf'),
             '--out-dir',str(out/'identity')],'identity.txt')
    from dap_pipeline_bench import open_dap,setup
    import usb.util
    dev,tx,rx=open_dap()
    try:setup(tx,rx,1000)
    finally:usb.util.dispose_resources(dev)
    from probe_build_info import live_clock_snapshot
    report['actualClocks']=live_clock_snapshot()
    from probe_flash import Session
    session=Session(out,Path('E:/Xilinx/SDK/2018.3'),'tcp:127.0.0.1:3121')
    before=session.read_words(CSR,16)
    if before[0]!=0x45444d31 or before[11]!=3 or before[12:14]!=[base,end]:raise ValueError('DDR pilot signature/capabilities/range mismatch')
    if before[2]&1:raise ValueError('Hardware still active after explicit reload')
    tail_address=base+(a.bytes//4)*4
    tail_words=min(4,(end-tail_address)//4)
    guards_before={'head':session.read_words(base-16,4),
                   'tail':session.read_words(tail_address,tail_words) if tail_words else []}
    report['guardBefore']=guards_before
    print('Loaded verified pair; starting PL pattern:',a.bytes,'bytes',flush=True)
    log=session.run(f'''mwr -force {CSR+12:#x} {base:#x}
mwr -force {CSR+16:#x} {a.bytes}
mwr -force {CSR+20:#x} {a.seed}
mwr -force {CSR+4:#x} 1
set terminal 0
for {{set n 0}} {{$n<10000}} {{incr n}} {{
  set status [mrd -force -value {CSR+8:#x}]
  if {{!($status&1)}} {{set terminal 1;break}}
  after 1
}}
puts "DDR_STATUS [mrd -force -value {CSR:#x} 16]"
if {{!$terminal}} {{
  catch {{mwr -force {CSR+4:#x} 2}}
  error "Writer timeout; abort requested, do not assume pending AXI writes retired"
}}
''')
    found=re.search(r'DDR_STATUS ([^\r\n]+)',log)
    if not found:raise ValueError('No hardware status')
    words=[int(w,0) for w in found[1].split()];report['hardwareRegisters']=words
    result.write_text(json.dumps(report,indent=2)+'\n')
    if len(words)!=16 or words[2]&0x1d or not words[2]&2 or words[6:8]!=[a.bytes,a.bytes] or words[9]:
        raise RuntimeError('Writer did not finish successfully: '+str(words))
    fclk=report['actualClocks']['FCLK_Hz'];elapsed=words[8]/fclk
    report.update(writerSeconds=elapsed,writerResponseMBps=a.bytes/elapsed/1e6,
                  timingBasis='FCLK hardware cycles from start command to controller observing final OKAY B; not USB/trace speed')
    guards_after={'head':session.read_words(base-16,4),
                  'tail':session.read_words(tail_address,tail_words) if tail_words else []}
    tail_before=b''.join(w.to_bytes(4,'little') for w in guards_before['tail'])
    tail_after=b''.join(w.to_bytes(4,'little') for w in guards_after['tail'])
    guard_ok=guards_before['head']==guards_after['head'] and tail_before[a.bytes%4:]==tail_after[a.bytes%4:]
    report.update(guardAfter=guards_after,adjacentGuardsUnchanged=guard_ok)
    result.write_text(json.dumps(report,indent=2)+'\n')
    image=out/'ddr-readback.bin'
    print('PL write ended; reading every byte independently through PS JTAG',flush=True)
    session.run('mrd -force -bin -file {'+image.as_posix()+f'}} {base:#x} {(a.bytes+3)//4}\nputs FULL_READBACK')
    if image.stat().st_size!=(a.bytes+3)//4*4:raise RuntimeError('Incomplete JTAG readback')
    actual_sha=hashlib.sha256();expected_sha=hashlib.sha256();offset=0;mismatches=[]
    with image.open('rb') as f:
        while offset<a.bytes:
            size=min(1<<20,a.bytes-offset);actual=f.read(size);expected=expected_chunk(offset,size,a.seed)
            actual_sha.update(actual);expected_sha.update(expected)
            if actual!=expected and len(mismatches)<8:
                mismatches.extend(offset+i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y and len(mismatches)<8)
            offset+=size
    report.update(readbackBytesVerified=offset,readbackSha256=actual_sha.hexdigest(),expectedSha256=expected_sha.hexdigest(),
                  firstMismatches=mismatches,passed=guard_ok and actual_sha.digest()==expected_sha.digest(),
                  limitations=['pattern only; ETM input and hardware capture timer not connected','JTAG readback; no USB download bandwidth claim','not a cache-coherence acceptance for CPU USB reads'])
    result.write_text(json.dumps(report,indent=2)+'\n')
    if not report['passed']:raise RuntimeError('DDR content mismatch; inspect result.json')
    print(json.dumps(report,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
