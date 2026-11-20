"""Verify physical probe CDC TX/RX with the F103 GPIO echo fixture at 115200 8N1."""
import argparse
import hashlib
import json
from contextlib import contextmanager,nullcontext
from dap_pipeline_bench import setup,cmd
from selectio_cli import connection
import struct
import time
from pathlib import Path
import serial
import serial.tools.list_ports

from benchmark_rtt_forward import core_read,core_write
from selectio_f103_fixture import low_link
from selectio_native import native_connection


@contextmanager
def concurrent_streams(native,base,slot,expected,report):
    config=struct.pack("<4BIIBB2xI",1,8,slot,2,base+0x240,24000,1,0,base+0x200)
    received=bytearray()
    samples=[]
    def pull():
        chunk=native.exchange(6,1)
        received.extend(chunk)
        wave=native.exchange(6,2)
        samples.extend(struct.iter_unpack("<II",wave))
        return len(chunk)+len(wave)
    native.exchange(6,0,config)
    try:yield pull
    finally:
        native.exchange(6,3)
        while pull():pass
        state=struct.unpack("<8I",native.exchange(6,4))
        native.exchange(6,5)
        if received!=expected or state[1] or state[3]!=len(received) or state[4]!=len(received):
            raise RuntimeError("RTT content or completion counters differ while CDC is active")
        values=[g[1] for g in samples]
        if not values or values!=sorted(values) or values[-1]<=values[0] or values[-1]>256 or state[5]!=len(samples) or state[6]!=len(samples):
            raise RuntimeError("CDC target counter differs from simultaneous scope samples")
        report["concurrent_native"]=dict(rtt_bytes=len(received),sample_groups=len(samples),skipped=state[7],
                                         first_sample=values[0],last_sample=values[-1],rtt_sha256=hashlib.sha256(received).hexdigest())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--binary",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--combo",action="store_true",help="run RTT plus 1 kHz sampling on SWD while Windows exchanges physical CDC bytes")
    ap.add_argument("--swd-slot",type=int,help="perform 100 MHz SRAM reads during physical CDC TX and RX")
    ap.add_argument("--execute",action="store_true")
    a=ap.parse_args()
    if a.combo and a.swd_slot is None:ap.error("--combo requires --swd-slot")
    if not a.execute:
        print("Requires the guarded F103ZE fixture. Use PA15 for target UART RX and PB3 for target UART TX.")
        return
    a.out.mkdir(parents=True,exist_ok=False)
    BASE=0x20008000;DHCSR=0xe000edf0;DEMCR=0xe000edfc;DWT=0xe0001000
    APB=0x40021018;MAPR=0x40010004;AH=0x40010804;BL=0x40010c00;BO=0x40010c0c;DBG=0xe0042004
    code=a.binary.read_bytes()
    if not 0<len(code)<512:raise ValueError("echo code must fit below the fixture status words")
    seed=hashlib.shake_256(b"RTT during physical CDC").digest(96)
    register_ids=[*range(17),20]
    report=dict(passed=False,binary_sha256=hashlib.sha256(code).hexdigest())
    registers=peripherals=page=None
    try:
        with low_link(a.serial) as m:
            if not m.word(DHCSR)&(1<<17):raise RuntimeError("target must already be halted")
            registers={i:core_read(m,i) for i in register_ids}
            apb=m.word(APB)
            page=m.read(BASE,1024);(a.out/"page.bin").write_bytes(page)
            m.write_word(APB,apb|13)
            peripherals={addr:m.word(addr) for addr in (MAPR,AH,BL,BO,DBG,DEMCR,DWT)}
            peripherals[MAPR]&=~(7<<24);peripherals[APB]=apb
            report.update(registers=registers,peripherals=peripherals)
            (a.out/"state.json").write_text(json.dumps(report,indent=2))
            m.write_word(MAPR,peripherals[MAPR]|(2<<24))
            m.write_word(DBG,peripherals[DBG]&~0xe0)
            m.write_word(AH,(peripherals[AH]&0x0fffffff)|(4<<28))
            m.write_word(0x40010c10,8)
            m.write_word(BL,(peripherals[BL]&~(15<<12))|(3<<12))
            m.write_word(DEMCR,peripherals[DEMCR]|(1<<24));m.write_word(DWT,peripherals[DWT]|1)
            m.write(BASE,code);assert m.read(BASE,len(code))==code
            if a.combo:
                m.write(BASE+0x240,struct.pack("<16sII6I",b"SEGGER RTT",1,0,0,BASE+0x300,256,len(seed),0,0))
                m.write(BASE+0x300,seed)
            core_write(m,16,0x01000000);core_write(m,20,1);core_write(m,15,BASE+1)
            m.write_word(DHCSR,0xa05f0001)
            if m.word(BASE+0x208)!=0x4543484f:raise RuntimeError("echo producer did not start")
        ports=[x.device for x in serial.tools.list_ports.comports() if x.vid==0xd28 and x.pid==0x204 and x.serial_number==a.serial]
        if len(ports)!=1:raise RuntimeError("CDC COM mapping is not unique")
        report["com"]=ports[0]
        with connection(a.serial) as (tx,rx),native_connection(a.serial,tx.device) as n:
            n.info()
            if a.swd_slot is not None:setup(tx,rx,1000,"swd")
            n.exchange(0,3,b"\x01")
            try:
                with serial.Serial(ports[0],57600,timeout=1,write_timeout=1) as port:
                    time.sleep(.03)
                    report["coding_57600"]=struct.unpack("<8I",n.exchange(0,4))
                    port.baudrate=115200
                    for _ in range(100):
                        state=struct.unpack("<8I",n.exchange(0,4))
                        if state[1] and state[2]==115200:break
                        time.sleep(.01)
                    report["coding_115200"]=state
                    if state[:3]!=(1,1,115200):raise RuntimeError(f"CDC binding failed {state}")
                    port.reset_input_buffer()
                    data=hashlib.shake_256(b"J7 physical CDC").digest(256)
                    guard=(concurrent_streams(n,BASE,a.swd_slot,seed,report) if a.combo else
                           n.memory(1,8,a.swd_slot,2) if a.swd_slot is not None else nullcontext())
                    with guard as service:
                        for i,b in enumerate(data):
                            port.write(bytes([b]))
                            if a.combo: service()
                            elif a.swd_slot is not None and n.bulk(BASE,4)!=code[:4]:
                                raise RuntimeError("concurrent 100 MHz SWD SRAM value differs")
                            value=port.read(1)
                            if value!=bytes([b^0xa5]):
                                raise RuntimeError(f"target reply differs at {i}: {value.hex()}")
                    report["concurrent_swd_reads"]=len(data) if a.swd_slot is not None and not a.combo else 0
                    report["bytes_each"]=len(data)
                    report["end_status"]=struct.unpack("<8I",n.exchange(0,4))
            finally:
                n.exchange(0,3,b"\0")
                for _ in range(100):
                    if not struct.unpack("<8I",n.exchange(0,4))[1]:break
                    time.sleep(.01)
                if a.swd_slot is not None:cmd(tx,rx,[3])
        with low_link(a.serial) as m:
            m.write_word(DHCSR,0xa05f0003)
            report["target_count"]=m.word(BASE+0x200);report["target_errors"]=m.word(BASE+0x204)
            if report["target_count"]!=256 or report["target_errors"]:raise RuntimeError("physical target counter differs")
        report["passed"]=True
    except Exception as exc:
        report["error"]=str(exc);raise
    finally:
        try:
            if peripherals is not None:
                with low_link(a.serial) as m:
                    m.write_word(DHCSR,0xa05f0003)
                    for addr in (DWT,DEMCR,DBG,BL,AH):m.write_word(addr,peripherals[addr])
                    m.write_word(0x40010c10,8 if peripherals[BO]&8 else 8<<16)
                    m.write_word(MAPR,peripherals[MAPR]);m.write_word(APB,peripherals[APB])
                    m.write(BASE,page)
                    for i in [*range(15),20,16,15]:core_write(m,i,registers[i])
                    if any(core_read(m,i)!=v for i,v in registers.items()) or m.read(BASE,1024)!=page:
                        raise RuntimeError("local CPU/page restore failed")
                    report["restored"]=True
        finally:(a.out/"state.json").write_text(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
