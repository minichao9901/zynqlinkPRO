"""Native WinUSB stream framing for interface 4 of a J7 integration probe."""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
import secrets
import struct

import libusb_package
import usb.core
import usb.util


HEADER = struct.Struct("<4sBBBBII")


class NativeStatusError(RuntimeError):
    def __init__(self,channel,operation,status,detail):
        super().__init__(f"native channel {channel} operation {operation} status {status}, detail {detail.hex()}")
        self.status=status


@dataclass
class NativeStream:
    device: object
    sequence: int
    dma: bool = False
    max_depth: int = 1
    frame_size: int = 4096
    advertised_frame: int = 4096
    sliding: bool = True

    @property
    def max_bulk(self):
        return ((self.frame_size-33)//32)*32

    def _write(self,channel,op,payload):
        if len(payload)>self.frame_size-17: raise ValueError("native frame exceeds its data capacity")
        seq=self.sequence
        request=HEADER.pack(b"ZLK1",channel,op,0,0,seq,len(payload))+payload
        if len(request)%512==0:request+=b"\0"
        if self.device.write(0x01,request,timeout=3000)!=len(request):
            raise RuntimeError("incomplete native OUT transfer")
        self.sequence=(seq+1)&0xffffffff
        return seq

    def _read(self,channel,op,seq,synchronize=False):
        # A closed WinUSB handle may have left complete IN frames in the
        # endpoint. Only a fresh HELLO can retire them and resynchronize.
        capacity=16384 if synchronize else self.frame_size
        for _ in range(5 if synchronize else 1):
            reply=bytes(self.device.read(0x84,capacity,timeout=3000))
            if len(reply)<HEADER.size:raise RuntimeError("truncated native IN header")
            magic,ch,operation,status,reserved,returned,size=HEADER.unpack_from(reply)
            total=HEADER.size+size
            if (magic!=b"ZLK1" or reserved or size>capacity-17 or len(reply)!=total+int(total%512==0)):
                raise RuntimeError("invalid native frame header or length")
            if (ch,operation,returned)!=(channel,op,seq):
                if synchronize:continue
                raise RuntimeError("native response sequence or command mismatch")
            if status:
                raise NativeStatusError(ch,op,status,reply[16:24])
            return reply[16:total]
        raise RuntimeError("unable to synchronize native reply sequence")

    def exchange(self,channel,op,payload=b""):
        return self._read(channel,op,self._write(channel,op,payload))

    @contextmanager
    def memory(self,port,tap,slot,idle,clock=100000000):
        if clock not in (50000000,100000000):raise ValueError("unsupported SelectIO clock")
        profile=bytes((port,tap,slot,idle))
        self.exchange(1,1,profile if clock==100000000 else profile+struct.pack("<I",clock))
        try:
            yield
        finally:
            self.exchange(1,2)

    def bulk_many(self,requests,depth=4,*,transport_only=False):
        """Submit ordered requests. Retire all submitted replies before raising a device error."""
        if not 1<=depth<=4: raise ValueError("native queue depth must be 1..4")
        requests = tuple(requests)
        for address,size,data in requests:
            if (not 0x20000000<=address<address+size<=0x20010000 or address%4 or
                size<=0 or size%4 or size>self.max_bulk or (data is not None and len(data)!=size)):
                raise ValueError("invalid F103 SRAM range, alignment or payload length")
        depth=min(depth,self.max_depth)
        channel=7 if transport_only else 1
        header=16 if self.dma or transport_only else 8
        op=6 if header==16 else 3
        result=[]
        pending=deque()
        error=None
        def retire():
            nonlocal error
            seq,size,read=pending.popleft()
            try:
                reply=self._read(channel,op,seq)
                if len(reply)!=header+(size if read else 0) or struct.unpack_from("<I",reply)[0]!=size//4:
                    raise RuntimeError("incomplete MEM-AP transfer")
                result.append(reply[header:])
            except RuntimeError as exc:
                if error is None:error=exc

        for address,size,data in requests:
            payload=struct.pack("<BBHI",int(data is not None),0,size//4,address).ljust(header,b"\0")
            seq=self._write(channel,op,payload+(data if data is not None else b""))
            pending.append((seq,size,data is None))
            if len(pending)==depth:
                retire()
                if not self.sliding:
                    while pending:retire()
                if error:break
        while pending:retire()
        if error:raise error
        return result

    def bulk(self,address,size,data=None):
        return self.bulk_many([(address,size,data)],1)[0]

    def memory_stats(self):
        data=self.exchange(1,4)
        hz,rb,wb,rq,wq,rt,wt=struct.unpack_from("<7Q",data)
        return dict(timer_hz=hz,read_bytes=rb,write_bytes=wb,queue_s=[rq/hz,wq/hz],
                    probe_s=[rt/hz,wt/hz],jtag_retry_profile=list(struct.unpack_from("<2Q",data,56)) if len(data)==72 else None)

    def memory_clock(self, port, reference_hz, requested_hz):
        # Earlier firmware programs a fixed profile and lacks queue readback.
        if self.advertised_frame >= 16384:
            try:
                raw = self.exchange(1, 5)
            except NativeStatusError as error:
                if error.status not in (1, 3):
                    raise
            else:
                if len(raw) != 16:
                    raise RuntimeError("invalid memory clock record")
                ref, active_port, timing, tap = struct.unpack("<4I", raw)
                divider = {0: 4, 1: 2, 2: 1}.get(timing & 3) if port == 1 else timing & 7
                if active_port != port or divider not in (1, 2, 4) or not ref:
                    raise RuntimeError("invalid queue clock readback")
                return dict(wire_hz=ref//divider, reference_hz=ref, divider=divider,
                            timing=hex(timing), tap=tap, source="PS clock tree and PL queue registers")
        divider = 4 if requested_hz == 50000000 else 2
        return dict(wire_hz=reference_hz//divider, reference_hz=reference_hz, divider=divider,
                    source="PS clock tree and requested profile")

    def control(self,channel,action,data=b""):
        command={2:0x31,3:0x32}[channel]
        if len(data)>56:
            raise ValueError("control payload is too large")
        request=bytes((1,len(data)+2,command,action))+data
        reply=self.exchange(channel,2,request.ljust(64,b"\0"))
        if len(reply)!=64 or reply[2]!=command:
            raise RuntimeError("invalid stream control reply")
        return struct.unpack_from("b",reply,3)[0],struct.unpack_from("<12I",reply,4)

    def set_frame_size(self,size):
        if size not in (4096,16384) or size>self.advertised_frame:raise ValueError("unsupported frame size")
        if size==self.frame_size:return
        if self.exchange(0,8,struct.pack("<I",size))!=struct.pack("<I",size):
            raise RuntimeError("frame negotiation failed")
        self.frame_size=size

    def usb_descriptors(self):
        device=self.device
        config=device.get_active_configuration()
        interfaces=[]
        for interface in config:
            endpoints=[dict(address=f"0x{ep.bEndpointAddress:02x}",attributes=ep.bmAttributes,
                            max_packet_bytes=ep.wMaxPacketSize) for ep in interface]
            interfaces.append(dict(number=interface.bInterfaceNumber,alternate=interface.bAlternateSetting,
                usb_class=interface.bInterfaceClass,subclass=interface.bInterfaceSubClass,
                protocol=interface.bInterfaceProtocol,endpoints=endpoints))
        return dict(vid=f"{device.idVendor:04x}",pid=f"{device.idProduct:04x}",serial=device.serial_number,
                    bcdDevice=f"0x{device.bcdDevice:04x}",configuration=config.bConfigurationValue,
                    interfaces=interfaces)

    def info(self):
        reply=self._read(0,0,self._write(0,0,b""),synchronize=True)
        if len(reply)!=16 or reply[:4]!=b"SIO1":
            raise RuntimeError("unrecognized native firmware interface")
        ref,features,size=struct.unpack_from("<III",reply,4)
        info=dict(protocol="ZLK1",reference_hz=ref,link_hz=ref/2 if features&0x80 else None,features=hex(features),
                  integrated_pl=bool(features&0x80),max_frame=size)
        try:
            extended=self.exchange(0,5)
        except NativeStatusError as err:
            if err.status!=1:raise
            # The first probe protocol only guaranteed one in-flight legacy bulk request.
            self.dma=False
            self.max_depth=1
        else:
            if len(extended)!=24 or extended[:4]!=b"CAP1":
                raise RuntimeError("invalid probe capability record")
            abi,depth,header,capacity,fclk=struct.unpack_from("<5I",extended,4)
            if abi!=1 or not 1<=depth<=4 or header not in (8,16):
                raise RuntimeError("unsupported SRAM protocol")
            self.dma=header==16
            self.max_depth=depth
            info.update(firmware_abi=abi,bulk_header_bytes=header,serial_buffer_bytes=capacity,fclk0_hz=fclk)
        self.advertised_frame=size
        self.frame_size=4096
        if size>=16384:self.set_frame_size(16384)
        info["negotiated_frame"]=self.frame_size
        info["max_queue_depth"]=self.max_depth
        return info


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
