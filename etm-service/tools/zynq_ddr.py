"""Bounded DDR capture and identity-bound binary USB download; no instruction JSON."""
import hashlib
import json
from pathlib import Path
import secrets
import struct
import threading
import time

from dap_pipeline_bench import xfer

WORDS=44
COMMAND=0x8c


class DdrError(RuntimeError):
    pass


def unpack(data):
    if len(data)!=WORDS*4: raise DdrError('DDR status length mismatch')
    w=list(struct.unpack('<44I',data))
    if w[:2]!=[0x31554445,1]: raise DdrError('DDR status protocol mismatch')
    regs=w[4:38]
    return dict(protocol='zynq-ddr-usb/1',available=bool(w[2]),result=w[3],registers=regs,
        captureId=regs[10],nonce=regs[31]|regs[32]<<32,active=bool(regs[2]&1),done=bool(regs[2]&2),
        sourceActive=bool(regs[2]&32),bytes=regs[7],acceptedBytes=regs[6],ticks=regs[17],
        qualityFlags=regs[18],tailBytes=regs[22],stopReason=regs[23],format=regs[28],
        tailAmbiguous=bool(regs[29]),transferId=w[38],rangeOffset=w[39],rangeBytes=w[40],
        sentBytes=w[41],downloadState=w[42],submitErrors=w[43])


class Transport:
    def __init__(self,dev,out,inp):
        self.dev,self.out,self.inp=dev,out,inp
        self.capture_id=None;self.nonce=None;self.ref_hz=None;self.requested_ticks=None
        self.command_lock=threading.Lock()

    def snapshot(self):
        return unpack(bytes(self.dev.ctrl_transfer(0xc0,0x63,0,0x4554,176,timeout=3000)))

    def command(self,op,*args):
        if len(args)>6:raise ValueError('DDR command has six arguments')
        payload=struct.pack('<BBH6I',COMMAND,op,0x4445,*(list(args)+[0]*(6-len(args))))
        with self.command_lock:
            reply=xfer(self.out,self.inp,payload)
        if len(reply)!=178 or reply[0]!=COMMAND:raise DdrError('DDR command reply mismatch')
        status=unpack(reply[2:])
        if reply[1] or status['result']:
            raise DdrError(f"DDR command {op} rejected ({status['result']})")
        return status

    def _identity(self,status):
        if (status['captureId'],status['nonce'])!=(self.capture_id,self.nonce):
            raise DdrError('DDR capture ID/nonce changed; refusing mixed data')

    def arm(self,seconds,ref_hz,byte_limit=0x20000000,nonce=None):
        if not 0<seconds<=2 or not 190000000<=ref_hz<=210000000 or not 1<=byte_limit<=0x20000000:
            raise ValueError('invalid bounded DDR window/clock/capacity')
        before=self.snapshot()
        if not before['available']:raise DdrError('PS did not advertise DDR download')
        if before['active']:raise DdrError('previous DDR source remains active')
        self.nonce=nonce if nonce is not None else secrets.randbits(64) or 1
        if not 1<=self.nonce<=0xffffffffffffffff:raise ValueError('nonzero 64-bit nonce required')
        self.capture_id=(before['captureId']+1)&0xffffffff
        self.ref_hz=ref_hz;self.requested_ticks=round(seconds*ref_hz)
        self.arm_before_unix=time.time()
        status=self.command(1,self.requested_ticks,byte_limit,self.nonce&0xffffffff,self.nonce>>32)
        self._identity(status)
        return status

    def wait_source(self,timeout=2):
        until=time.monotonic()+timeout
        while True:
            s=self.snapshot();self._identity(s)
            if s['sourceActive']:
                self.active_observed_unix=time.time()
                return s
            if s['done'] and not s['active']:raise DdrError('DDR window ended before target resume')
            if time.monotonic()>until:raise DdrError('DDR source did not arm')
            time.sleep(.001)

    def wait(self,timeout=5):
        until=time.monotonic()+timeout
        while True:
            s=self.snapshot();self._identity(s)
            if not s['active'] and s['done']:return s
            if time.monotonic()>until:raise DdrError('DDR capture did not retire')
            time.sleep(.005)

    def stop(self):
        if self.capture_id is not None:
            return self.command(2,self.capture_id,self.nonce&0xffffffff,self.nonce>>32)

    def release(self):
        if self.capture_id is not None:
            return self.command(4,self.capture_id,self.nonce&0xffffffff,self.nonce>>32)

    def _read_exact(self,count):
        data=bytearray()
        while len(data)<count:
            part=bytes(self.dev.read(0x82,count-len(data),timeout=5000))
            if not part:raise DdrError('unexpected short/empty DDR USB read')
            data.extend(part)
        return bytes(data)

    def download(self,path):
        path=Path(path)
        status=self.snapshot();self._identity(status)
        regs=status['registers'];count=status['bytes']
        if status['active'] or not status['done'] or regs[2]&16 or status['acceptedBytes']!=count:
            raise DdrError('DDR writer is not retired')
        if status['format']!=0x46524d31 or regs[33]!=2 or not 0<=count<=0x20000000:
            raise DdrError('DDR record is not a bounded FRM1 capture')
        if path.exists():raise FileExistsError(path)
        started=time.perf_counter()
        issued=self.command(3,self.capture_id,self.nonce&0xffffffff,self.nonce>>32,0,count)
        header=self._read_exact(512)
        h=struct.unpack('<128I',header)
        expected=(0x3144445a,1,issued['transferId'],self.capture_id,self.nonce&0xffffffff,self.nonce>>32,0,count,count,
                  0x46524d31,status['tailBytes'],status['qualityFlags'],status['ticks'],int(status['tailAmbiguous']),512)
        if h[:15]!=expected or h[15]&1 or any(h[16:]):raise DdrError('DDR USB header does not match frozen record/range')
        digest=hashlib.sha256()
        with path.open('xb') as output:
            remaining=count
            while remaining:
                chunk=self._read_exact(min(1<<20,remaining))
                output.write(chunk);digest.update(chunk);remaining-=len(chunk)
        # Host receipt can precede the final device TX callback. Wait for it;
        # a following START cannot reuse the same storage prematurely.
        until=time.monotonic()+3
        while True:
            retired=self.snapshot();self._identity(retired)
            if retired['transferId']!=issued['transferId']:raise DdrError('DDR transfer identity changed')
            if retired['sentBytes']==count and not retired['downloadState']&0xffff:break
            if time.monotonic()>until:raise DdrError('DDR USB last descriptor did not retire')
            time.sleep(.001)
        if retired['bytes']!=count or retired['ticks']!=status['ticks']:raise DdrError('DDR record changed after USB read')
        elapsed=time.perf_counter()-started
        status.update(sha256=digest.hexdigest(),usbSeconds=elapsed,usbPayloadMBps=count/elapsed/1e6,
            transferId=issued['transferId'],submitErrorsAfter=retired['submitErrors'],
            requestedTicks=self.requested_ticks,referenceHz=self.ref_hz,
            hardwareStartBracketUnix=[self.arm_before_unix,self.active_observed_unix],
            actualWindowSeconds=status['ticks']/self.ref_hz)
        path.with_suffix('.usb.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf8')
        return status


def quality(status):
    r=status['registers']
    return dict(transport='ddr-usb/1',captureId=status['captureId'],captureNonce=status['nonce'],
        loss=bool(r[2]&12 or r[9] or status['qualityFlags'] or r[27]),synced=bool(r[24]),
        ended=status['done'] and not status['active'],records=r[21],
        hardwareTicks=status['ticks'],requestedTicks=status['requestedTicks'],
        refClockHz=status['referenceHz'],hardwareSeconds=status['actualWindowSeconds'],
        hardwareStartBracketUnix=status['hardwareStartBracketUnix'],
        stopReason=status['stopReason'],formatterBytes=status['bytes'],tailBytes=status['tailBytes'],
        tailAmbiguous=status['tailAmbiguous'],usbSeconds=status['usbSeconds'],usbPayloadMBps=status['usbPayloadMBps'],
        diagnostics=dict(implemented=True,frameDrops=r[19],parserErrors=r[20],idelayReadyLosses=r[26],
            frameHighwater=r[25],syncAcquisitions=r[24],capacityReached=bool(r[27]),writerError=r[9]))
