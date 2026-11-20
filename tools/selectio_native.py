"""Native WinUSB stream framing for interface 4 of a J7 integration probe."""
from contextlib import contextmanager
from dataclasses import dataclass
import secrets
import struct

import libusb_package
import usb.core
import usb.util


HEADER = struct.Struct("<4sBBBBII")
LIMIT = 4079


@dataclass
class NativeStream:
    device: object
    sequence: int
    dma: bool = False

    def _write(self,channel,op,payload):
        if len(payload)>LIMIT: raise ValueError("native frame exceeds its data capacity")
        seq=self.sequence
        request=HEADER.pack(b"ZLK1",channel,op,0,0,seq,len(payload))+payload
        if len(request)%512==0:request+=b"\0"
        if self.device.write(0x01,request,timeout=3000)!=len(request):
            raise RuntimeError("incomplete native OUT transfer")
        self.sequence=(seq+1)&0xffffffff
        return seq

    def _read(self,channel,op,seq):
        reply=bytes(self.device.read(0x84,4096,timeout=3000))
        if len(reply)<HEADER.size: raise RuntimeError("truncated native IN header")
        magic,ch,operation,status,reserved,returned,size=HEADER.unpack_from(reply)
        total=HEADER.size+size
        if ((magic,ch,operation,reserved,returned)!=(b"ZLK1",channel,op,0,seq) or
                size>LIMIT or len(reply)!=total+int(total%512==0)):
            raise RuntimeError("native frame identity or length mismatch")
        if status:
            raise RuntimeError(f"native channel {ch} operation {op} status {status}, detail {reply[16:24].hex()}")
        return reply[16:total]

    def exchange(self,channel,op,payload=b""):
        return self._read(channel,op,self._write(channel,op,payload))

    @contextmanager
    def memory(self,port,tap,slot,idle):
        self.exchange(1,1,bytes((port,tap,slot,idle)))
        try:
            yield
        finally:
            self.exchange(1,2)

    def bulk_many(self,requests,depth=4):
        """Submit ordered requests. Retire all submitted replies before raising a device error."""
        if not 1<=depth<=4: raise ValueError("native queue depth must be 1..4")
        for address,size,data in requests:
            if (not 0x20000000<=address<address+size<=0x20010000 or address%4 or
                size<=0 or size%4 or size>4032 or (data is not None and len(data)!=size)):
                raise ValueError("invalid F103 SRAM range, alignment or payload length")
        header=16 if self.dma else 8
        op=6 if self.dma else 3
        result=[]
        for index in range(0,len(requests),depth):
            pending=[]
            for address,size,data in requests[index:index+depth]:
                payload=struct.pack("<BBHI",int(data is not None),0,size//4,address).ljust(header,b"\0")
                seq=self._write(1,op,payload+(data if data is not None else b""))
                pending.append((seq,size,data is None))
            error=None
            for seq,size,read in pending:
                try:
                    reply=self._read(1,op,seq)
                    if len(reply)!=header+(size if read else 0) or struct.unpack_from("<I",reply)[0]!=size//4:
                        raise RuntimeError("incomplete MEM-AP transfer")
                    result.append(reply[header:])
                except RuntimeError as exc:
                    error=error or exc
            if error:raise error
        return result

    def bulk(self,address,size,data=None):
        return self.bulk_many([(address,size,data)],1)[0]

    def memory_stats(self):
        data=self.exchange(1,4)
        hz,rb,wb,rq,wq,rt,wt=struct.unpack_from("<7Q",data)
        return dict(timer_hz=hz,read_bytes=rb,write_bytes=wb,queue_s=[rq/hz,wq/hz],
                    probe_s=[rt/hz,wt/hz],jtag_retry_profile=list(struct.unpack_from("<2Q",data,56)) if len(data)==72 else None)

    def control(self,channel,action,data=b""):
        command={2:0x31,3:0x32}[channel]
        if len(data)>56:
            raise ValueError("control payload is too large")
        request=bytes((1,len(data)+2,command,action))+data
        reply=self.exchange(channel,2,request.ljust(64,b"\0"))
        if len(reply)!=64 or reply[2]!=command:
            raise RuntimeError("invalid stream control reply")
        return struct.unpack_from("b",reply,3)[0],struct.unpack_from("<12I",reply,4)

    def info(self):
        reply=self.exchange(0,0)
        if len(reply)!=16 or reply[:4]!=b"SIO1":
            raise RuntimeError("unrecognized native firmware interface")
        ref,features,size=struct.unpack_from("<III",reply,4)
        self.dma=bool(features&0x400)
        return dict(protocol="ZLK1",reference_hz=ref,link_hz=ref/2 if features&0x80 else None,features=hex(features),
                    integrated_pl=bool(features&0x80),max_frame=size)


@contextmanager
def native_connection(serial,device=None):
    from dap_pipeline_bench import Ownership
    own=device is None
    lease=Ownership() if own else None
    try:
        if own:
            matches=[d for d in usb.core.find(find_all=True,idVendor=0x0d28,idProduct=0x0204,
                     backend=libusb_package.get_libusb1_backend()) if d.serial_number==serial and d.manufacturer=="CherryUSB"]
            if len(matches)!=1:raise RuntimeError(f"expected one J7 with serial {serial}, found {len(matches)}")
            device=matches[0]
        interface=device.get_active_configuration()[(4,0)]
        if (interface.bInterfaceClass,interface.bInterfaceSubClass,interface.bInterfaceProtocol)!=(255,0x53,1):
            raise RuntimeError("incompatible native interface descriptor")
        usb.util.claim_interface(device,4)
        try:yield NativeStream(device,secrets.randbits(32))
        finally:usb.util.release_interface(device,4)
    finally:
        try:
            if own and device is not None:usb.util.dispose_resources(device)
        finally:
            if lease is not None:lease.close()
