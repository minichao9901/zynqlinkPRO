"""Byte-accurate RTT DOWN writes for a native MEM-AP session."""
import time
import struct


def read_bytes(native,address,size):
    if not size:return b""
    start=address&~3
    end=(address+size+3)&~3
    data=bytearray()
    for addr in range(start,end,4032):
        data.extend(native.bulk(addr,min(4032,end-addr)))
    return bytes(data[address-start:address-start+size])


def write_bytes(native,address,data):
    if not data:return
    start=address&~3
    end=(address+len(data)+3)&~3
    image=bytearray(end-start)
    prefix=address-start
    if prefix:image[:4]=native.bulk(start,4)
    if end!=address+len(data):image[-4:]=native.bulk(end-4,4)
    image[prefix:prefix+len(data)]=data
    for i in range(0,len(image),4032):
        chunk=bytes(image[i:i+4032]);native.bulk(start+i,len(chunk),chunk)


class Ring:
    def __init__(self,native,cb,channel,down):
        self.native=native
        signature,up_count,down_count=struct.unpack("<16sII",read_bytes(native,cb,24))
        if signature[:10]!=b"SEGGER RTT" or up_count>64 or down_count>64:
            raise ValueError("invalid SEGGER RTT control block")
        if not 0<=channel<(down_count if down else up_count):
            raise ValueError("target firmware does not define that RTT channel")
        self.desc=cb+24+24*((up_count if down else 0)+channel)
        self.down=down

    def state(self):
        _,base,size,wr,rd,_=struct.unpack("<6I",read_bytes(self.native,self.desc,24))
        if size<2 or not 0x20000000<=base<base+size<=0x20010000 or max(rd,wr)>=size:
            raise RuntimeError("invalid RTT ring or offsets")
        return base,size,wr,rd

    def send(self,data):
        base,size,wr,rd=self.state()
        count=min(len(data),(rd-wr-1)%size,size-wr,4032)
        if not count:return 0
        payload=data[:count]
        write_bytes(self.native,base+wr,payload)
        if read_bytes(self.native,base+wr,count)!=payload:raise RuntimeError("RTT data changed before publication")
        value=struct.pack("<I",(wr+count)%size)
        self.native.bulk(self.desc+12,4,value)
        if self.native.bulk(self.desc+12,4)!=value: raise RuntimeError("RTT WrOff could not be confirmed")
        return count

    def receive(self,sink):
        base,size,wr,rd=self.state()
        count=min((wr-rd)%size,size-rd,4032)
        if not count:return 0
        data=read_bytes(self.native,base+rd,count)
        if sink.write(data)!=count:raise RuntimeError("RTT output sink accepted a partial write")
        sink.flush()
        value=struct.pack("<I",(rd+count)%size)
        self.native.bulk(self.desc+16,4,value)
        if self.native.bulk(self.desc+16,4)!=value:raise RuntimeError("RTT RdOff could not be confirmed")
        return count
