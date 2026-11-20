"""Verify real F103 PB3 MISO transitions in all four 100 MHz SPI modes."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

import numpy as np
from selectio_f103_fixture import low_link
from selectio_native import native_connection
from selectio_wire_test import captured

APB1=0x4002101c
APB2=0x40021018
MAPR=0x40010004
GPIOB_CRL=0x40010c00
DBG=0xe0042004
TIM2=0x40000000
SWJ=7<<24
TIMER_REGS=(0x00,0x04,0x08,0x0c,0x10,0x18,0x20,0x24,0x28,0x2c,0x38)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--seconds",type=float,default=10)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--execute",action="store_true")
    a=ap.parse_args()
    if not a.execute:return print("Guarded F103ZE CDC48 fixture. TIM2_CH2 drives PB3 at 12 MHz; J7 reads MISO.")
    a.out.mkdir(parents=True,exist_ok=False)
    report=dict(source="F103ZE TIM2_CH2 on PB3",target_HCLK=48000000,source_hz=12000000,spi_hz=100000000,modes=[])
    original=timer=None
    changed=False
    try:
        with low_link(a.serial) as m:
            if not m.word(0xe000edf0)&(1<<17) or m.word(0x40021004)!=0x0051040a:
                raise RuntimeError("requires the halted CDC48 F103ZE fixture")
            original={addr:m.word(addr) for addr in (APB1,APB2,MAPR,GPIOB_CRL,DBG)}
            m.write_word(APB1,original[APB1]|1)
            timer={offset:m.word(TIM2+offset) for offset in TIMER_REGS}
            if timer[0]&1 or timer[0x0c] or timer[0x20]:
                raise RuntimeError("TIM2 is already active")
            changed=True
            m.write_word(APB2,original[APB2]|9)
            # Disable JTAG TDO, retain SWD, select TIM2 partial remap 1.
            m.write_word(MAPR,(original[MAPR]&~(SWJ|0x300))|(2<<24)|0x100)
            m.write_word(DBG,original[DBG]&~((1<<11)|0xe0))
            m.write_word(GPIOB_CRL,(original[GPIOB_CRL]&~0xf000)|0xb000)
            for offset,value in [(0,0),(4,0),(8,0),(0x0c,0),(0x20,0),(0x18,6<<12),
                                 (0x28,0),(0x2c,3),(0x38,2),(0x14,1),(0x20,1<<4),(0,1)]:
                m.write_word(TIM2+offset,value)
        with native_connection(a.serial) as port:
            port.info()
            for mode in range(4):
                row=dict(mode=mode,transactions=0,bytes=0,min_run=100,max_run=0)
                report["modes"].append(row)
                started=time.perf_counter()
                while not row["transactions"] or time.perf_counter()-started<a.seconds:
                    data=hashlib.shake_256(struct.pack("<2I",mode,row["transactions"])).digest(2048)
                    cfg=struct.pack("<BBBBIB",0,0,mode,22,100000000,0)
                    got,stat=captured(port,cfg,data)
                    if len(got)!=len(data) or any(stat[:3]):raise RuntimeError(f"SPI mode {mode} incomplete")
                    bits=np.unpackbits(np.frombuffer(got,dtype=np.uint8))
                    edges=np.flatnonzero(bits[1:]!=bits[:-1])+1
                    if len(edges)<3:raise RuntimeError(f"no 12 MHz external PWM on MISO, mode {mode}: {got[:12].hex()}")
                    runs=np.diff(edges)
                    hz=(len(edges)-1)*100000000/(2*(int(edges[-1])-int(edges[0])))
                    row.update(last_hz=hz,min_run=min(row["min_run"],int(runs.min())),max_run=max(row["max_run"],int(runs.max())))
                    if not 11900000<hz<12100000 or runs.min()<3 or runs.max()>6:
                        raise RuntimeError(f"physical MISO edge train differs in mode {mode}: {row}")
                    row["transactions"]+=1;row["bytes"]+=len(got)
                row["passed"]=True
        report["passed"]=True
    finally:
        try:
            if original is not None:
                with low_link(a.serial) as m:
                    if changed:
                        m.write_word(TIM2,0);m.write_word(TIM2+0x20,0)
                        for offset in (0x04,0x08,0x0c,0x18,0x28,0x2c,0x38):
                            m.write_word(TIM2+offset,timer[offset])
                        m.write_word(TIM2+0x14,1)
                        for offset in (0x24,0x10,0x20,0):
                            m.write_word(TIM2+offset,timer[offset])
                        if any(m.word(TIM2+i)!=v for i,v in timer.items()):raise RuntimeError("TIM2 restoration differs")
                        m.write_word(GPIOB_CRL,original[GPIOB_CRL]);m.write_word(DBG,original[DBG])
                        m.write_word(MAPR,original[MAPR]&~SWJ);m.write_word(APB2,original[APB2])
                    m.write_word(APB1,original[APB1])
                    if any((m.word(reg)^v)&(~SWJ if reg==MAPR else 0xffffffff) for reg,v in original.items()):
                        raise RuntimeError("GPIO/RCC recovery differs")
                    report["restored"]=True
        finally:(a.out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
