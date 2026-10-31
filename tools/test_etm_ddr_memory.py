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


def pattern_case(session,out,base,end,length,seed,clock,save):
    report=dict(bytes=length,seed=seed,actualClocks=clock,passed=False,stage='preflight')
    save(report)
    before=session.read_words(CSR,16)
    if before[0]!=0x45444d31 or before[11]!=3 or before[12:14]!=[base,end]:raise ValueError('DDR pilot signature/capabilities/range mismatch')
    if before[2]&1:raise ValueError('Previous hardware operation is still active; no start issued')
    expected_id=(before[10]+1)&0xffffffff
    report['expectedCaptureId']=expected_id
    tail_address=base+(length//4)*4;tail_words=min(4,(end-tail_address)//4)
    guards_before={'head':session.read_words(base-16,4),'tail':session.read_words(tail_address,tail_words) if tail_words else []}
    report.update(guardBefore=guards_before,stage='pattern-start');save(report)
    log=session.run(f'''physwr -force {CSR+12:#x} {base:#x}
physwr -force {CSR+16:#x} {length}
physwr -force {CSR+20:#x} {seed}
physwr -force {CSR+4:#x} 1
set terminal 0
for {{set n 0}} {{$n<10000}} {{incr n}} {{
  set id [physrd -force -value {CSR+40:#x}]
  set status [physrd -force -value {CSR+8:#x}]
  if {{$id=={expected_id} && !($status&1) && ($status&2)}} {{set terminal 1;break}}
  after 1
}}
puts "DDR_STATUS [physrd -force -value {CSR:#x} 16]"
if {{!$terminal}} {{
  catch {{physwr -force {CSR+4:#x} 2}}
  error "Writer timeout; abort requested, pending AXI retirement not proven"
}}
''')
    found=re.search(r'DDR_STATUS ([^\r\n]+)',log)
    if not found:raise ValueError('No hardware status')
    words=[int(w,0) for w in found[1].split()];report['hardwareRegisters']=words;save(report)
    if len(words)!=16 or words[2]&0x1d or not words[2]&2 or words[6:8]!=[length,length] or words[9] or words[10]!=expected_id or words[3:6]!=[base,length,seed]:
        raise RuntimeError('Writer status/identity mismatch: '+str(words))
    elapsed=words[8]/clock['FCLK_Hz']
    report.update(writerSeconds=elapsed,responseRateMBps=length/elapsed/1e6,stage='guard-readback',
        timingBasis='FCLK cycles through final OKAY B; counter rate is not verified payload throughput')
    guards_after={'head':session.read_words(base-16,4),'tail':session.read_words(tail_address,tail_words) if tail_words else []}
    tail_before=b''.join(w.to_bytes(4,'little') for w in guards_before['tail'])
    tail_after=b''.join(w.to_bytes(4,'little') for w in guards_after['tail'])
    guard_ok=guards_before['head']==guards_after['head'] and tail_before[length%4:]==tail_after[length%4:]
    report.update(guardAfter=guards_after,adjacentGuardsUnchanged=guard_ok,stage='full-readback');save(report)
    image=out/'ddr-readback.bin'
    # Bound each TCF binary response instead of constructing a 512MiB Tcl
    # string, and expose progress while the independently running PL is idle.
    report['readbackChunks']=[]
    with image.open('xb') as combined:
        for part_index,offset in enumerate(range(0,length,16<<20)):
            size=min(16<<20,length-offset);part=out/f'ddr-part-{part_index:03}.bin'
            session.run('physrd -force -bin -file {'+part.as_posix()+f'}} {base+offset:#x} {(size+3)//4}\nputs PHYSICAL_CHUNK_READ')
            expected_size=(size+3)//4*4
            if part.stat().st_size!=expected_size:raise RuntimeError('Incomplete physical readback chunk')
            digest=hashlib.sha256()
            with part.open('rb') as stream:
                while data:=stream.read(1<<20):combined.write(data);digest.update(data)
            combined.flush()
            report['readbackChunks'].append(dict(offset=offset,bytes=size,storedBytes=expected_size,sha256=digest.hexdigest()))
            report['readbackProgressBytes']=offset+size;save(report)
            if length>16<<20:print('physical readback',offset+size,'/',length,'bytes',flush=True)
    if image.stat().st_size!=(length+3)//4*4:raise RuntimeError('Incomplete JTAG readback')
    actual_sha=hashlib.sha256();expected_sha=hashlib.sha256();offset=0;mismatches=[]
    with image.open('rb') as f:
        while offset<length:
            size=min(1<<20,length-offset);actual=f.read(size);expected=expected_chunk(offset,size,seed)
            actual_sha.update(actual);expected_sha.update(expected)
            if actual!=expected and len(mismatches)<8:
                mismatches.extend(offset+i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y and len(mismatches)<8)
            offset+=size
    from probe_build_info import live_clock_snapshot
    after=live_clock_snapshot();stable=after['FCLK_Hz']==clock['FCLK_Hz']
    report.update(readbackBytesVerified=offset,readbackSha256=actual_sha.hexdigest(),expectedSha256=expected_sha.hexdigest(),
        firstMismatches=mismatches,clocksAfter=after,clockStable=stable,
        passed=guard_ok and stable and actual_sha.digest()==expected_sha.digest(),stage='done')
    if report['passed']:report['verifiedPatternMBps']=length/elapsed/1e6
    save(report)
    if not report['passed']:raise RuntimeError('DDR payload, adjacent guard or clock mismatch; first failure retained')
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--bytes',type=lambda x:int(x,0),default=1048576)
    p.add_argument('--seed',type=lambda x:int(x,0),default=0x13dba917)
    p.add_argument('--rounds',type=int,default=1)
    p.add_argument('--clock-mode',choices=['dap','current'],default='dap',help='current isolates the initialized clock; dap exercises normal DAP setup')
    p.add_argument('--loader',type=Path,default=ROOT/'tools/download_dap_fpga.tcl',help='Explicit loader for controlled initialization A/B experiments')
    a=p.parse_args(argv);pair=a.pair.resolve();out=a.out.resolve();loader=a.loader.resolve()
    if not 1<=a.bytes<=0x20000000 or not 0<=a.seed<=0xffffffff or not 1<=a.rounds<=100 or a.bytes*a.rounds>1<<30:p.error('invalid finite count/seed/rounds; total readback limited to 1GiB')
    for path in [pair,out,loader]:
        if any(c in str(path) for c in '{}\r\n'):p.error('Tcl paths must not contain braces or newlines')
    if not loader.is_file():p.error('Loader not found')
    manifest=json.loads((pair/'manifest.json').read_text(encoding='utf8'))
    for name in ('probe.bit','application.elf','ps7_init.tcl'):
        expected=manifest['files'][name];expected=expected['sha256'] if isinstance(expected,dict) else expected
        if hashlib.sha256((pair/name).read_bytes()).hexdigest()!=expected:raise ValueError('Pair hash mismatch: '+name)
    base,end=reservation(pair/'application.elf')
    if base+a.bytes>end:raise ValueError('Test exceeds reservation')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(hardware=True,traceCapture=False,flashWrites=False,source='address-dependent PL pattern',
        pair=str(pair),pairFiles=manifest['files'],base=base,bytesPerRound=a.bytes,seed=a.seed,requestedRounds=a.rounds,
        reloadBetweenRounds=False,retryFailedRounds=False,clockMode=a.clock_mode,loader=str(loader),
        loaderSha256=hashlib.sha256(loader.read_bytes()).hexdigest(),runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        readbackPath='physical MEM-AP0; no Cortex-A9 memory/cache context',cases=[],passed=False,stage='load')
    result=out/'result.json'
    def save():result.write_text(json.dumps(report,indent=2)+'\n')
    def checked(command,log):
        run=subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=120)
        (out/log).write_text(run.stdout+run.stderr,encoding='utf8')
        if run.returncode:raise RuntimeError('Failed; inspect '+str(out/log))
    save()
    try:
        checked([sys.executable,str(ROOT/'tools/run_xsct.py'),str(loader),str(pair/'application.elf'),str(pair/'probe.bit'),str(pair/'ps7_init.tcl')],'load.txt')
        report['stage']='code-identity';save()
        checked([sys.executable,str(ROOT/'tools/verify_probe_ocm_code.py'),'--elf',str(pair/'application.elf'),'--out-dir',str(out/'identity')],'identity.txt')
        import time,usb.core,usb.util,libusb_package
        report['stage']='usb-enumeration';save()
        deadline=time.monotonic()+15
        while usb.core.find(idVendor=0x0d28,idProduct=0x0204,backend=libusb_package.get_libusb1_backend()) is None:
            if time.monotonic()>deadline:raise RuntimeError('Probe did not enumerate after explicit load; no DDR pattern write issued')
            time.sleep(.1)
        report['usbEnumeratedBeforePattern']=True;report['stage']='clock-selection';save()
        if a.clock_mode=='dap':
            from dap_pipeline_bench import open_dap,setup
            dev,tx,rx=open_dap()
            try:setup(tx,rx,1000)
            finally:usb.util.dispose_resources(dev)
        from probe_build_info import live_clock_snapshot
        from probe_flash import Session
        from zynq_memory import PhysicalMemory
        session=PhysicalMemory(Session(out,Path('E:/Xilinx/SDK/2018.3'),'tcp:127.0.0.1:3121'))
        for n in range(a.rounds):
            case_out=out/f'round-{n+1:03}';case_out.mkdir()
            seed=(a.seed+n*0x9e3779b9)&0xffffffff
            case={};report['cases'].append(case)
            def save_case(value):
                case.clear();case.update(value);save()
            report['stage']='pattern-'+str(n+1)
            pattern_case(session,case_out,base,end,a.bytes,seed,live_clock_snapshot(),save_case)
            print('pattern',n+1,'verified',a.bytes,'bytes',flush=True)
        report.update(passed=True,stage='done')
    except Exception as error:
        report.update(passed=False,error=str(error),failedStage=report['stage']);save();raise
    finally:save()
    print(json.dumps(dict(passed=True,rounds=len(report['cases']),clockMode=a.clock_mode)))
    return 0


if __name__=='__main__':raise SystemExit(main())
