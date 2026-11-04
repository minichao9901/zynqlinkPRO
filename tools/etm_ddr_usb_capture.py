"""AI board acceptance using the same USB DDR transport as the Web service."""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'etm-service/tools'))
from zynq_ddr import Transport,quality
from native_framed import run as deformat
from test_etm_ddr_memory import reservation


def capture(out,probe_elf,dev,tx,rx,seconds,ref_hz,resume,trace_id=2,verify_physical=False,flight=None,fault_read=None):
    base,end=reservation(Path(probe_elf))
    work=Path(out)/'ddr';work.mkdir(exist_ok=False)
    report=dict(hardwareAccess=True,transport='USB post-capture DDR download',passed=False,flashWrites=False)
    def save():(work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    t=Transport(dev,tx,rx);save()
    try:
        if flight:t.arm_flight(seconds,ref_hz,flight['capacityBytes'])
        else:t.arm(seconds,ref_hz)
        t.wait_source();resume()
        if flight:
            armed=time.monotonic();triggered=False;reason=None
            report['flightArmed']=dict(unix=time.time(),options=flight);save()
            while time.monotonic()-armed < flight['timeout']:
                age=time.monotonic()-armed
                control=Path(flight['controlFile']) if flight.get('controlFile') else None
                if control and control.with_suffix('.cancel').exists():
                    reason='cancelled';break
                observed=fault_read() if flight['trigger']=='fault' and fault_read else None
                if (control and control.exists()) or (flight['trigger']=='after' and age>=flight['after']) or (observed is not None and (observed&0x1ff) in (3,4,5,6)):
                    reason='manual' if control and control.exists() else flight['trigger']
                    t.trigger();triggered=True
                    report['flightTrigger']=dict(source=reason,observedValue=observed,unix=time.time(),
                        detection='host polling, 10ms requested interval; not a physical fault trigger')
                    save();break
                s=t.snapshot();t._identity(s)
                if not s['active']:raise RuntimeError('flight recorder stopped before trigger')
                time.sleep(.01)
            if not triggered:
                t.stop();report['flightTrigger']=dict(source=reason or 'arm-timeout');save()
        t.wait(max(5,seconds+3))
        result=t.download(work/'capture.frm1');q=quality(result)
        report.update(result,quality=q,actualWindowSeconds=result['actualWindowSeconds'],
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
            offset=0
            capacity=result.get('flight',{}).get('capacityBytes',end-base)
            oldest=result.get('flight',{}).get('oldestOffset',0)
            while offset<result['bytes']:
                physical=(oldest+offset)%capacity
                count=min(16<<20,result['bytes']-offset,capacity-physical);part=jtag/f'{offset:08x}.bin'
                memory.run(f'physrd -force -bin -file {{{part.resolve().as_posix()}}} {base+physical:#x} {(count+3)//4}\nputs DDR_PHYSICAL_READ')
                if part.stat().st_size!=(count+3)//4*4:raise RuntimeError('short physical DDR readback')
                with part.open('rb') as stream:
                    left=count
                    while left:
                        data=stream.read(min(left,1<<20));digest.update(data);left-=len(data)
                offset+=count
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
