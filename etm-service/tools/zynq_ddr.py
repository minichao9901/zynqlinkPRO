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


def flight_options(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('飞行记录参数必须为对象')
    capacity=value.get('capacityBytes',8<<20);timeout=value.get('timeout',60)
    trigger=value.get('trigger','manual');after=value.get('after',1)
    if type(capacity) is not int or not 128<=capacity<=100*1024*1024 or capacity%128:
        raise ValueError('环形容量必须128字节对齐且不超过100MiB')
    if type(timeout) not in (int,float) or not 0<timeout<=86400:
        raise ValueError('飞行记录等待时限必须为0..86400秒')
    if trigger not in ('manual','fault','after') or type(after) not in (int,float) or not 0<=after or (trigger=='after' and after>=timeout):
        raise ValueError('无效触发源/延时')
    return dict(capacityBytes=capacity,timeout=timeout,trigger=trigger,after=after)


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
        self.flight=False

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

    def arm(self,seconds,ref_hz,byte_limit=None,nonce=None):
        if not 0<seconds<=2 or not 190000000<=ref_hz<=210000000:
            raise ValueError('invalid bounded DDR window/clock/capacity')
        before=self.snapshot()
        if not before['available']:raise DdrError('PS did not advertise DDR download')
        if before['active']:raise DdrError('previous DDR source remains active')
        r=before['registers'];capacity=r[13]-r[12]
        if (r[12],r[13]) not in ((0x39c00000,0x40000000),(0x10000000,0x30000000)):
            raise DdrError('unrecognized reserved DDR region')
        if byte_limit is None:byte_limit=capacity
        if not 1<=byte_limit<=capacity or (capacity==100*1024*1024 and byte_limit!=capacity):
            raise ValueError('capture uses the fixed 100 MiB region')
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

    def arm_flight(self,post_seconds,ref_hz,capacity_bytes):
        if not 0<post_seconds<=2 or not 190000000<=ref_hz<=210000000:
            raise ValueError('invalid post-trigger window/reference clock')
        before=self.snapshot();r=before['registers']
        if not before['available'] or not r[11]&0x100:
            raise DdrError('loaded bit/ELF does not advertise flight recording')
        if before['active'] or before['downloadState']&0xffff:
            raise DdrError('previous capture/download remains active')
        if type(capacity_bytes) is not int or capacity_bytes<128 or capacity_bytes>r[13]-r[12] or capacity_bytes%128:
            raise ValueError('ring capacity must be a multiple of 128 bytes in reserved DDR')
        self.flight=True;self.ref_hz=ref_hz;self.requested_ticks=round(post_seconds*ref_hz)
        self.nonce=secrets.randbits(64) or 1;self.capture_id=(before['captureId']+1)&0xffffffff
        self.arm_before_unix=time.time()
        status=self.command(5,self.requested_ticks,capacity_bytes,self.nonce&0xffffffff,self.nonce>>32)
        self._identity(status);return status

    def trigger(self):
        if not self.flight:raise DdrError('not a flight recording')
        status=self.command(6,self.capture_id,self.nonce&0xffffffff,self.nonce>>32)
        self._identity(status);return status

    def flight_info(self):
        w=self.command(7)['registers'][:11]
        if w[0]!=0x31525246:raise DdrError('flight metadata protocol mismatch')
        return dict(words=w,oldestOffset=w[1],retainedBytes=w[2],totalBytes=w[3]|w[4]<<32,
                    triggerTicks=w[5]|w[6]<<32,elapsedHigh=w[7],flags=w[8],postTicks=w[9],capacityBytes=w[10])

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
        if status['format']!=0x46524d31 or regs[33] not in (2,3) or not 0<=count<=regs[13]-regs[12]:
            raise DdrError('DDR record is not a bounded FRM1 capture')
        flight=self.flight_info() if regs[33]==3 else None
        if flight and (count!=flight['retainedBytes'] or not 0<=flight['oldestOffset']<flight['capacityBytes'] or count>flight['capacityBytes']):
            raise DdrError('flight retained range mismatch')
        if path.exists():raise FileExistsError(path)
        started=time.perf_counter()
        issued=self.command(3,self.capture_id,self.nonce&0xffffffff,self.nonce>>32,0,count)
        header=self._read_exact(512)
        h=struct.unpack('<128I',header)
        expected=(0x3144445a,2 if flight else 1,issued['transferId'],self.capture_id,self.nonce&0xffffffff,self.nonce>>32,0,count,count,
                  0x46524d31,status['tailBytes'],status['qualityFlags'],status['ticks'],int(status['tailAmbiguous']),512)
        if h[:15]!=expected or h[15]&1:raise DdrError('DDR USB header does not match frozen record/range')
        if flight:
            if list(h[16:27])!=flight['words'] or any(h[27:]):raise DdrError('flight USB metadata changed')
        elif any(h[16:]):raise DdrError('unexpected DDR USB metadata')
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
        if flight:
            status['flight']=flight
            status['totalHardwareTicks']=status['ticks']+(flight['elapsedHigh']<<32)
            status['actualWindowSeconds']=status['totalHardwareTicks']/self.ref_hz
        path.with_suffix('.usb.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf8')
        return status


def quality(status):
    r=status['registers']
    loss=bool(r[2]&12 or r[9] or status['qualityFlags'])
    full=bool(r[27]) and status['bytes']==r[13]-r[12] and status['stopReason']==2
    timed=status['ticks']==status['requestedTicks'] and status['stopReason']==0
    flight=status.get('flight')
    if flight:
        timed=bool(flight['flags']&2) and status['stopReason']==0 and status['totalHardwareTicks']-flight['triggerTicks']==flight['postTicks']
        full=False
    result=dict(transport='ddr-usb/1',captureId=status['captureId'],captureNonce=status['nonce'],
        loss=loss,synced=bool(r[24]),bufferFull=full,bufferCapacityBytes=r[13]-r[12],
        captureComplete=(timed or full) and not loss,requestedWindowComplete=timed and not loss,
        completionReason='buffer-full' if full else ('time' if timed else 'stopped'),
        ended=status['done'] and not status['active'],records=status['bytes']//16,
        hardwareTicks=status['ticks'],requestedTicks=status['requestedTicks'],
        refClockHz=status['referenceHz'],hardwareSeconds=status['actualWindowSeconds'],
        hardwareStartBracketUnix=status['hardwareStartBracketUnix'],
        stopReason=status['stopReason'],formatterBytes=status['bytes'],tailBytes=status['tailBytes'],
        tailAmbiguous=status['tailAmbiguous'],usbSeconds=status['usbSeconds'],usbPayloadMBps=status['usbPayloadMBps'],
        diagnostics=dict(implemented=True,frameDrops=r[19],parserErrors=r[20],idelayReadyLosses=r[26],
            frameHighwater=r[25],syncAcquisitions=r[24],observedFrames=r[21],capacityReached=bool(r[27]),writerError=r[9]))
    if flight:
        result.update(flight=flight,completionReason='trigger' if timed else 'stopped',
            bufferCapacityBytes=flight['capacityBytes'],
            historyOverwritten=bool(flight['flags']&4),retainedHistoryBytes=flight['retainedBytes'],
            discardedHistoryBytes=flight['totalBytes']-flight['retainedBytes'],
            overwrittenBytes=max(0,flight['totalBytes']-flight['capacityBytes']),
            alignmentDiscardedBytes=min(flight['totalBytes'],flight['capacityBytes'])-flight['retainedBytes'],
            initialExecutionUnknown=True,windowBasis='trigger-post-window; retained prefix is byte bounded',
            hardwareTicks=status['totalHardwareTicks'])
    return result
