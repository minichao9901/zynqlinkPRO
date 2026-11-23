"""CMSIS-DAP SWO via the optional dedicated Bulk IN or polled SWO_Data."""
import struct

from usb.core import USBTimeoutError
from contextlib import contextmanager
from dap_pipeline_bench import cmd


class CmsisSwo:
    def __init__(self, tx, rx):
        self.tx,self.rx=tx,rx
        self.stream_endpoint=None

    def request(self,command,data=b""):
        return cmd(self.tx,self.rx,bytes((command,))+data)[1:]

    def set(self,command,value):
        if self.request(command,bytes((value,)))!=b"\0":
            raise RuntimeError(f"SWO configuration {command:#x}={value} rejected")

    def pull(self):
        if self.stream_endpoint is not None:
            try:
                return bytes(self.tx.device.read(self.stream_endpoint,4096,timeout=30))
            except USBTimeoutError:
                return b""
        reply=self.request(0x1c,struct.pack("<H",4092))
        if len(reply)<3:
            raise RuntimeError("truncated SWO_Data")
        status,size=struct.unpack_from("<BH",reply)
        if status&0xc0 or len(reply)!=size+3:
            raise RuntimeError(f"SWO_Data status {status:#x}, byte count {size}")
        return reply[3:]

    def stop(self):
        self.set(0x1a,0)

    def status(self):
        status,pending,index,ticks=struct.unpack("<BIII",self.request(0x1e,b"\x07"))
        return dict(status=status,pending=pending,index=index,timestamp=ticks)


@contextmanager
def cmsis_swo(tx,rx,encoding,rate):
    source=CmsisSwo(tx,rx)
    caps=source.request(0,b"\xf0")
    flag=4 if encoding=="uart" else 8
    if len(caps)<2 or not caps[1]&flag:
        raise RuntimeError(f"the running CMSIS-DAP firmware does not advertise SWO {encoding}")
    buffer=source.request(0,b"\xfd")
    if len(buffer)!=5 or not struct.unpack_from("<I",buffer,1)[0]:
        raise RuntimeError("invalid CMSIS-DAP trace buffer size")
    if caps[1]&0x40:
        interface=tx.device.get_active_configuration()[(0,0)]
        endpoints=list(interface)
        if len(endpoints)<3 or endpoints[2].bEndpointAddress&0x80==0:
            raise RuntimeError("SWO streaming capability lacks the third Bulk IN descriptor")
        source.stream_endpoint=endpoints[2].bEndpointAddress
    source.set(0x17,2 if source.stream_endpoint is not None else 1)
    try:
        source.set(0x18,1 if encoding=="uart" else 2)
        source.rate,=struct.unpack("<I",source.request(0x19,struct.pack("<I",rate)))
        if not source.rate:
            raise RuntimeError("requested SWO baud rate rejected")
        source.set(0x1a,1)
        try:
            yield source
        finally:source.stop()
    finally:
        source.set(0x18,0)
        source.set(0x17,0)
