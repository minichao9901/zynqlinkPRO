"""Correlate new Zynq HID replies without replaying a control operation."""
import secrets
import struct
import time


class HidControl:
    def __init__(self,device):
        self.device=device;self.sequence=secrets.randbits(32);self.correlated=False;self.stale=0

    def negotiate(self):
        payload=bytes([1,0x13])+bytes(61)
        self.exchange(payload,negotiate=True)
        return self.correlated

    def exchange(self,payload,negotiate=False):
        payload=bytes(payload)
        if len(payload)!=63:raise ValueError('HID payload must be 63 bytes')
        if (self.correlated or negotiate) and payload[0]>58:
            raise ValueError('correlated HID request exceeds reserved nonce boundary')
        self.sequence=(self.sequence+1)&0xffffffff
        nonce=struct.pack('<I',self.sequence)
        packet=bytearray(b'\x01'+payload)
        if self.correlated or negotiate:packet[60:64]=nonce
        self.device.write(packet)
        until=time.monotonic()+2
        while time.monotonic()<until:
            reply=bytes(self.device.read(64,100))
            if len(reply)!=64 or reply[0]!=2 or reply[2]!=payload[1]:
                if reply:self.stale+=1
                continue
            advertised=negotiate and b'nonce32' in reply[3:3+min(reply[1],56)]
            if (self.correlated or advertised) and reply[60:64]!=nonce:
                self.stale+=1;continue
            if negotiate:self.correlated=bool(advertised)
            return reply
        raise TimeoutError('HID响应未匹配本次请求；没有重放控制命令')
