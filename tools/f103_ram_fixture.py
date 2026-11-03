"""Scoped RAM producer/static HSS fixtures with verified SRAM/core restoration."""
import hashlib
import json
from pathlib import Path
import random
import struct
import usb.util
from dap_pipeline_bench import open_dap, setup, xfer
from test_probe_board import Memory, stop
from benchmark_rtt_forward import core_read, core_write
from target_snapshot import snapshot
from probe_stream import Probe


class Fixture:
    def __init__(self, out):
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.dev,self.tx,self.rx=open_dap();self.mem=Memory(self.tx,self.rx)
        self.probe=Probe();self.backup=None;self.regs=None
        self.report={}

    def __enter__(self):
        stop(self.probe,self.dev);setup(self.tx,self.rx,1000)
        self.report['initialDHCSR']=hex(self.mem.word(0xe000edf0))
        self.report['clockBefore']=snapshot(self.mem)
        self.mem.write_word(0xe000edf0,0xa05f0003)
        self.regs={i:core_read(self.mem,i) for i in list(range(19))+[20]}
        (self.out/'core-private.json').write_text(json.dumps(self.regs))
        self.backup=self.mem.read(0x20000000,20480)
        (self.out/'sram-private.bin').write_bytes(self.backup)
        self.report['backupSha256']=hashlib.sha256(self.backup).hexdigest()
        self.save();return self

    def save(self):
        (self.out/'restoration.json').write_text(json.dumps(self.report,indent=2))

    def prepare_rtt(self):
        self.mem.write_word(0xe000edf0,0xa05f0003)
        code=Path('build/rtt_ram_20000000/producer.bin').read_bytes()
        assert len(code)<512
        self.mem.write(0x20000000,code)
        self.mem.write(0x20000200,struct.pack('<16sII6II',b'SEGGER RTT',1,0,0,0x20001000,8192,0,0,0,0))
        assert self.mem.read(0x20000000,len(code))==code
        core_write(self.mem,16,0x01000000);core_write(self.mem,20,1);core_write(self.mem,15,0x20000001)

    def resume(self):self.mem.write_word(0xe000edf0,0xa05f0001)

    def halt_producer(self):
        self.mem.write_word(0xe000edf0,0xa05f0003)
        counter=self.mem.word(0x20000230)*4;wr=self.mem.word(0x20000224)
        pending=(wr-(counter&8191))&8191;assert pending in (0,4),(wr,counter)
        return counter+pending

    def prepare_hss(self,pattern=None):
        self.mem.write_word(0xe000edf0,0xa05f0003)
        self.pattern=pattern if pattern is not None else random.Random(0x485353).randbytes(4096)
        assert len(self.pattern)==4096
        self.mem.write(0x20004000,self.pattern)
        assert self.mem.read(0x20004000,4096)==self.pattern
        # Release native ownership before the real Web path configures the stream.
        assert xfer(self.tx,self.rx,[3])==b'\x03\x00'
        self.release_dap()

    def release_dap(self):
        if self.dev is not None:
            usb.util.release_interface(self.dev,0);usb.util.dispose_resources(self.dev);self.dev=None
        self.release_hid()

    def release_hid(self):
        if self.probe is not None:self.probe.close();self.probe=None

    def __exit__(self,typ,value,tb):
        try:
            if self.probe is None:self.probe=Probe()
            if self.dev is None:
                self.dev,self.tx,self.rx=open_dap();self.mem=Memory(self.tx,self.rx)
            stop(self.probe,self.dev);setup(self.tx,self.rx,1000)
            self.mem.write_word(0xe000edf0,0xa05f0003)
            if self.backup is not None:
                self.mem.write(0x20000000,self.backup)
                self.report['sramRestored']=self.mem.read(0x20000000,len(self.backup))==self.backup
                assert self.report['sramRestored']
            if self.regs is not None:
                for i,v in self.regs.items():core_write(self.mem,i,v)
                self.report['registersRestored']={i:core_read(self.mem,i) for i in self.regs}==self.regs
                assert self.report['registersRestored']
            self.report['clockAfter']=snapshot(self.mem)
            assert self.report['clockAfter']==self.report['clockBefore']
            if not int(self.report['initialDHCSR'],16)&(1<<17):self.resume()
            self.report['finalDHCSR']=hex(self.mem.word(0xe000edf0))
            self.report['restored']=True
        finally:
            if value:self.report['testError']=repr(value)
            self.save();self.release_dap()
