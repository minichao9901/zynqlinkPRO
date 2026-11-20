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

    def exchange(self, channel, op, payload=b""):
        if len(payload)>LIMIT:
            raise ValueError("one native frame can carry at most 4079 bytes")
        sequence=self.sequence
        request=HEADER.pack(b"ZLK1",channel,op,0,0,sequence,len(payload))+payload
        if len(request)%512==0:
            request+=b"\0"
        if self.device.write(0x01,request,timeout=3000)!=len(request):
            raise RuntimeError("incomplete native OUT transfer")
        reply=bytes(self.device.read(0x84,4096,timeout=3000))
        if len(reply)<HEADER.size:
            raise RuntimeError("truncated native IN header")
        magic,ch,operation,status,reserved,returned,size=HEADER.unpack_from(reply)
        total=HEADER.size+size
        if ((magic,ch,operation,reserved,returned)!=(b"ZLK1",channel,op,0,sequence) or
                size>LIMIT or len(reply)!=total+int(total%512==0)):
            raise RuntimeError("native frame identity or length mismatch")
        self.sequence=(sequence+1)&0xffffffff
        if status:
            raise RuntimeError(f"native channel {ch} operation {op} status {status}, detail {reply[16:24].hex()}")
        return reply[16:total]

    @contextmanager
    def memory(self,port,tap,slot,idle):
        self.exchange(1,1,bytes((port,tap,slot,idle)))
        try:
            yield
        finally:
            self.exchange(1,2)

    def bulk(self,address,size,data=None):
        if size<=0 or size%4 or size>4032 or (data is not None and len(data)!=size):
            raise ValueError("native block requires 4..4032 aligned bytes")
        payload=struct.pack("<BBHI",int(data is not None),0,size//4,address)
        reply=self.exchange(1,3,payload+(data if data is not None else b""))
        expected=8+(size if data is None else 0)
        if len(reply)!=expected or struct.unpack_from("<I",reply)[0]!=size//4:
            raise RuntimeError("incomplete MEM-AP transfer")
        return reply[8:]

    def memory_stats(self):
        hz,rb,wb,rq,wq,rt,wt=struct.unpack("<7Q",self.exchange(1,4))
        return dict(timer_hz=hz,read_bytes=rb,write_bytes=wb,queue_s=[rq/hz,wq/hz],
                    probe_s=[rt/hz,wt/hz])

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
        return dict(protocol="ZLK1",reference_hz=ref,link_hz=ref/2,features=hex(features),
                    integrated_pl=bool(features&0x80),max_frame=size)


@contextmanager
def native_connection(serial,device=None):
    own=device is None
    if own:
        matches=[d for d in usb.core.find(find_all=True,idVendor=0x0d28,idProduct=0x0204,
                 backend=libusb_package.get_libusb1_backend()) if d.serial_number==serial and d.manufacturer=="CherryUSB"]
        if len(matches)!=1:
            raise RuntimeError(f"expected one J7 with serial {serial}, found {len(matches)}")
        device=matches[0]
    try:
        interface=device.get_active_configuration()[(4,0)]
        if (interface.bInterfaceClass,interface.bInterfaceSubClass,interface.bInterfaceProtocol)!=(255,0x53,1):
            raise RuntimeError("incompatible native interface descriptor")
        usb.util.claim_interface(device,4)
        try:
            yield NativeStream(device,secrets.randbits(32))
        finally:
            usb.util.release_interface(device,4)
    finally:
        if own:
            usb.util.dispose_resources(device)
