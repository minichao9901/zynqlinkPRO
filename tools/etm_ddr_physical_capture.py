"""AI acceptance transport: hardware-window FRM1 capture, physical AP0 readback.

No PS USB download API is implied by this temporary JTAG acceptance path.
Caller owns target preparation/restoration and must load the exact probe pair.
"""
import json
from pathlib import Path
import re
import secrets
import sys
import threading
import time

from probe_flash import Session
from zynq_memory import PhysicalMemory
from test_etm_ddr_memory import reservation
from probe_build_info import live_clock_snapshot

CSR = 0x40040000
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'etm-service/tools'))


def capture(out, probe_elf, seconds, ref_hz, resume, trace_id=2):
    from native_framed import run as native_demux
    base, end = reservation(Path(probe_elf))
    work = Path(out)/'ddr'; work.mkdir(exist_ok=False)
    if any(c in str(work) for c in '{}\r\n'):
        raise ValueError('Tcl output path must not contain braces or newlines')
    memory = PhysicalMemory(Session(work, Path('E:/Xilinx/SDK/2018.3'), 'tcp:127.0.0.1:3121'))
    before = memory.read_words(CSR, 34)
    if before[0] != 0x45444d31 or before[11] & 7 != 7 or before[12:14] != [base,end]:
        raise ValueError('loaded PL has no validated FRM1 capability/range')
    if before[2] & 1: raise ValueError('previous DDR capture remains active')
    expected_id = (before[10]+1) & 0xffffffff
    ticks = round(ref_hz*seconds)
    if not 1 <= ticks <= 0xffffffff: raise ValueError('window outside reference counter range')
    nonce = secrets.randbits(64)
    marker, cancelled = work/'armed.json', work/'cancel'
    clock = live_clock_snapshot()
    report = dict(hardwareAccess=True, transport='physical MEM-AP0 after capture; not USB download',
                  bytesLimit=64<<20, requestedTicks=ticks, referenceHz=ref_hz,
                  expectedCaptureId=expected_id, nonce=nonce, actualClocks=clock, passed=False)
    result = work/'result.json'
    def save(): result.write_text(json.dumps(report,indent=2)+'\n')
    save()
    output, errors = [], []
    def acquire():
        try:
            output.append(memory.run(f'''physwr -force {CSR+60:#x} 2
physwr -force {CSR+12:#x} {base:#x}
physwr -force {CSR+16:#x} {64<<20}
physwr -force {CSR+64:#x} {ticks}
physwr -force {CSR+124:#x} {nonce&0xffffffff}
physwr -force {CSR+128:#x} {nonce>>32}
physwr -force {CSR+4:#x} 1
set terminal 0
set marked 0
for {{set n 0}} {{$n<10000}} {{incr n}} {{
  set status [physrd -force -value {CSR+8:#x}]
  set id [physrd -force -value {CSR+40:#x}]
  if {{!$marked && ($status&32) && $id=={expected_id}}} {{
    set f [open {{{marker.as_posix()}}} w];puts $f {{"armed"}};close $f;set marked 1
  }}
  if {{[file exists {{{cancelled.as_posix()}}}] && ($status&1)}} {{catch {{physwr -force {CSR+4:#x} 2}}}}
  if {{$id=={expected_id} && !($status&1) && ($status&2)}} {{set terminal 1;break}}
  after 1
}}
puts "TRACE_DDR_REGS [physrd -force -value {CSR:#x} 34]"
if {{!$terminal}} {{catch {{physwr -force {CSR+4:#x} 2}};error "capture timed out; stop requested"}}
'''))
        except BaseException as error: errors.append(error)
    worker = threading.Thread(target=acquire, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic()+20
        while not marker.exists():
            if errors: raise errors[0]
            if not worker.is_alive(): raise RuntimeError('DDR source ended before arm acknowledgement')
            if time.monotonic()>deadline: raise TimeoutError('waiting for DDR source arm')
            time.sleep(.002)
        report['hostResumeMonotonic'] = time.monotonic(); save()
        resume()
        worker.join(30)
        if worker.is_alive(): raise TimeoutError('DDR worker remains active')
        if errors: raise errors[0]
        match = re.search(r'TRACE_DDR_REGS ([^\r\n]+)',output[0])
        if not match: raise RuntimeError('missing frozen DDR status')
        words = [int(w,0) for w in match[1].split()]
        report['registers'] = words; save()
        if len(words)!=34 or words[10]!=expected_id or words[31:33]!=[nonce&0xffffffff,nonce>>32] or words[33]!=2:
            raise RuntimeError('DDR capture identity mismatch')
        count = words[7]
        if count > 64<<20 or words[2]&1 or not words[2]&2 or words[6] != count:
            raise RuntimeError('DDR writer has not safely retired')
        data = work/'capture.frm1'
        # Keep binary TCF replies bounded, including a 2s acquisition.
        with data.open('xb') as combined:
            for offset in range(0,count,16<<20):
                size = min(16<<20,count-offset); part=work/f'part-{offset:08x}.bin'
                memory.run(f'physrd -force -bin -file {{{part.as_posix()}}} {base+offset:#x} {(size+3)//4}\nputs READ_PART')
                if part.stat().st_size != (size+3)//4*4: raise RuntimeError('physical readback short')
                with part.open('rb') as stream:
                    remaining=size
                    while remaining:
                        block=stream.read(min(1<<20,remaining))
                        if not block: raise RuntimeError('physical readback changed while assembling')
                        combined.write(block);remaining-=len(block)
        report.update(actualWindowSeconds=words[17]/ref_hz, bytes=count,
                      qualityFlags=words[18], droppedFrames=words[19], parserErrors=words[20],
                      tailBytes=words[22], stopReason=words[23], syncs=words[24], fifoHighwater=words[25],
                      readyLosses=words[26], capacityReached=bool(words[27]), tailAmbiguous=bool(words[29]))
        save()
        if words[28]!=0x46524d31: raise RuntimeError('record is not FRM1')
        # Preserve the failing raw capture and diagnostics before rejecting it.
        if words[2]&0x1c or words[9] or words[18] or words[27] or words[17]!=ticks or words[23]!=0:
            raise RuntimeError('DDR hardware quality/window failed')
        demux = native_demux(data,work/'demux',tail_bytes=words[22],trace_id=trace_id)
        report.update(demux=demux, passed=True); save()
        return Path(demux['selectedStream']).read_bytes(), report
    except BaseException as error:
        cancelled.write_text('stop requested')
        worker.join(30)
        report.update(error=repr(error), workerRetired=not worker.is_alive()); save()
        raise
