"""AI board acceptance using the same USB DDR transport as the Web service."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'etm-service/tools'))
from zynq_ddr import Transport,quality
from native_framed import run as deformat
from test_etm_ddr_memory import reservation


def capture(out,probe_elf,dev,tx,rx,seconds,ref_hz,resume,trace_id=2,verify_physical=False):
    base,end=reservation(Path(probe_elf))
    work=Path(out)/'ddr';work.mkdir(exist_ok=False)
    report=dict(hardwareAccess=True,transport='USB post-capture DDR download',passed=False,flashWrites=False)
    def save():(work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    t=Transport(dev,tx,rx);save()
    try:
        t.arm(seconds,ref_hz);t.wait_source();resume()
        t.wait(max(5,seconds+3))
        result=t.download(work/'capture.frm1');q=quality(result)
        report.update(result,quality=q,actualWindowSeconds=result['ticks']/ref_hz,
            droppedFrames=result['registers'][19],parserErrors=result['registers'][20],
            readyLosses=result['registers'][26],fifoHighwater=result['registers'][25])
        save()
        if verify_physical:
            from probe_flash import Session
            from zynq_memory import PhysicalMemory
            if any(c in str(work.resolve()) for c in '{}\r\n'):raise ValueError('unsafe Tcl output path')
            jtag=work/'physical';jtag.mkdir()
            memory=PhysicalMemory(Session(jtag,Path('E:/Xilinx/SDK/2018.3'),'tcp:127.0.0.1:3121'))
            digest=hashlib.sha256()
            for offset in range(0,result['bytes'],16<<20):
                count=min(16<<20,result['bytes']-offset);part=jtag/f'{offset:08x}.bin'
                memory.run(f'physrd -force -bin -file {{{part.resolve().as_posix()}}} {base+offset:#x} {(count+3)//4}\nputs DDR_PHYSICAL_READ')
                if part.stat().st_size!=(count+3)//4*4:raise RuntimeError('short physical DDR readback')
                with part.open('rb') as stream:
                    left=count
                    while left:
                        data=stream.read(min(left,1<<20));digest.update(data);left-=len(data)
            report.update(physicalSha256=digest.hexdigest(),physicalBytes=result['bytes'],
                usbMatchesPhysical=digest.hexdigest()==result['sha256'])
            save()
            if not report['usbMatchesPhysical']:raise RuntimeError('USB bytes differ from physical MEM-AP0')
        if q['loss'] or not q['synced'] or not q['ended'] or not q['captureComplete']:
            raise RuntimeError('DDR hardware quality/window failed; raw data retained')
        report['demux']=deformat(work/'capture.frm1',work/'demux',tail_bytes=result['tailBytes'],trace_id=trace_id)
        report['passed']=True;save()
        return Path(report['demux']['selectedStream']).read_bytes(),report
    except Exception as exc:
        report['error']=str(exc);save();raise
    finally:
        if t.capture_id is not None:
            try:
                t.stop();t.wait();t.release()
                report['usbOwnerReleased']=True
            except Exception as exc:report['cleanupError']=str(exc)
            save()
