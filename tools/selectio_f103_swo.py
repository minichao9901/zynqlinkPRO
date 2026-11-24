"""Reversible ITM/TPIU setup for the F103ZE CDC48 clock profile."""
from contextlib import contextmanager
import usb.util
from dap_pipeline_bench import cmd, open_dap, setup
from test_probe_board import Memory


@contextmanager
def f103_swo(serial,encoding,rate,stimulus_mask,*,expected_cfgr=0x0051040a,swd_khz=1000):
    dev,tx,rx=open_dap(serial)
    mem=Memory(tx,rx)
    saved={}
    def set_saved(addr,value):
        if addr not in saved: saved[addr]=mem.word(addr)
        mem.write_word(addr,value)
    unlocked=False
    try:
        setup(tx,rx,swd_khz,"swd")
        if mem.word(0xe0042000)&0xfff!=0x414 or mem.word(0x40021004)!=expected_cfgr:
            raise RuntimeError("target does not match the requested F103ZE HCLK48 profile")
        symbol_rate=rate*(2 if encoding=="manchester" else 1)
        if symbol_rate<=0 or 48000000%symbol_rate or not 1<=48000000//symbol_rate<=8192:
            raise ValueError("requested bit rate needs an integer F103 trace divider in 1..8192")
        set_saved(0xe000edfc,mem.word(0xe000edfc)|(1<<24))
        devid=mem.word(0xe0040fc8)
        bit=10 if encoding=="manchester" else 11
        if not devid&(1<<bit):raise RuntimeError("target does not report the requested SWO encoder")
        set_saved(0x40021018,mem.word(0x40021018)|9)
        set_saved(0x40010c00,(mem.word(0x40010c00)&~(15<<12))|(11<<12))
        set_saved(0xe0042004,(mem.word(0xe0042004)&~0xe0)|0x20)
        lsr=mem.word(0xe0000fb4)
        if lsr&3==3: mem.write_word(0xe0000fb0,0xc5acce55);unlocked=True
        set_saved(0xe0000e00,0)
        set_saved(0xe0040304,mem.word(0xe0040304)&~2)
        set_saved(0xe0040010,48000000//symbol_rate-1)
        protocol=1 if encoding=="manchester" else 2
        set_saved(0xe00400f0,protocol)
        set_saved(0xe0000e80,0x10011)
        if mem.word(0xe00400f0)!=protocol or mem.word(0xe0040010)!=48000000//symbol_rate-1:
            raise RuntimeError("TPIU readback differs")
        def enable():
            mem.write_word(0xe0000e00,stimulus_mask)
            if mem.word(0xe0000e00)!=stimulus_mask:raise RuntimeError("ITM TER readback differs")
        class Stimulus:
            device=dev
            endpoints=(tx,rx)
            memory=mem
            def start(self):
                enable()
            def send_word(self,port,value):
                if not 0<=port<32 or not stimulus_mask&(1<<port):
                    raise ValueError("ITM port is not enabled")
                mem.write_word(0xe0000000+4*port,value)
        yield Stimulus()
    finally:
        try:
            if 0xe0000e00 in saved:mem.write_word(0xe0000e00,0)
            failures=[]
            for addr,value in reversed(list(saved.items())):
                try:
                    mem.write_word(addr,value)
                    mask=0xff7fffff if addr==0xe0000e80 else 0xffffffff
                    if ((mem.word(addr)^value)&mask):failures.append(hex(addr))
                    if addr==0xe0000e00 and unlocked:mem.write_word(0xe0000fb0,0)
                except Exception as error:failures.append(f"{addr:#x}: {error}")
            if failures:raise RuntimeError("F103 trace restoration failed: "+", ".join(failures))
        finally:
            try:cmd(tx,rx,[3])
            finally:usb.util.dispose_resources(dev)
