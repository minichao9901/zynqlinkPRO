"""Offline capacity/static-overlap study; never reserves or accesses DDR/USB."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from elftools.elf.elffile import ELFFile

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_BASE=0x10000000
DEFAULT_CAPACITY=0x20000000


def plan(trace_hz=200_000_000,seconds=2,format='raw8',base=DEFAULT_BASE,capacity=DEFAULT_CAPACITY,metadata=65536):
    if trace_hz<=0 or seconds not in (1,2) or format not in ('raw8','record16') or capacity<=0 or metadata<0:
        raise ValueError('positive frequency/capacity, duration 1/2 s and raw8/record16 required')
    header=ROOT/'reference/legacy_zynq/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0/include/xparameters.h'
    text=header.read_text(encoding='utf8')
    bound=lambda name:int(re.search(r'#define\s+XPAR_PS7_DDR_0_S_AXI_'+name+r'\s+(0x[0-9a-fA-F]+)',text).group(1),16)
    ddr_start,ddr_end=bound('BASEADDR'),bound('HIGHADDR')+1
    if base<ddr_start or base+capacity>ddr_end or base%4096 or capacity%4096:
        raise ValueError('candidate must be page-aligned and inside configured DDR map; this is not physical RAM attestation')
    payload=trace_hz*seconds*(1 if format=='raw8' else 2)
    required=(payload+metadata+4095)//4096*4096
    elf=ROOT/'prebuilt/golden/application.elf'
    occupied=[{'name':'linker dap_trace_mem reservation','start':0x3f000000,'end':0x3f100000}]
    with elf.open('rb') as stream:
        for section in ELFFile(stream).iter_sections():
            start,size=int(section['sh_addr']),int(section['sh_size'])
            if section['sh_flags']&2 and size and ddr_start<=start<ddr_end:
                occupied.append({'name':section.name,'start':start,'end':start+size})
    overlaps=[r for r in occupied if base<r['end'] and r['start']<base+capacity]
    return {'schema':'etm-ddr-capacity-study/1','hardwareAccess':False,'frequencyIsCapabilityClaim':False,
        'input':{'pins':4,'doubleDataRate':True,'traceClockHz':trace_hz,'seconds':seconds,'format':format},
        'payloadBytes':payload,'metadataBudgetBytes':metadata,'requiredBytesAligned':required,'candidateBase':base,
        'candidateCapacityBytes':capacity,'configuredDdrStart':ddr_start,'configuredDdrEndExclusive':ddr_end,
        'knownOccupiedRegions':occupied,'staticOverlaps':overlaps,'fitsCapacity':required<=capacity,
        'safeForDeployment':False,'validationPending':['physical DDR size/address alias test','dynamic DMA/USB/heap region audit',
            'linker reservation and build assertions','DMA cache coherence and fences','PL-to-DDR throughput/backpressure/stop/readback test'],
        'baselineFiles':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT/'prebuilt/golden/probe.bit',elf,header)}}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace-hz',type=int,default=200_000_000);p.add_argument('--seconds',type=int,choices=(1,2),default=2)
    p.add_argument('--format',choices=('raw8','record16'),default='raw8')
    p.add_argument('--base',type=lambda v:int(v,0),default=DEFAULT_BASE)
    p.add_argument('--capacity',type=lambda v:int(v,0),default=DEFAULT_CAPACITY)
    p.add_argument('--metadata',type=int,default=65536);p.add_argument('--out',type=Path)
    a=p.parse_args(argv);value=plan(a.trace_hz,a.seconds,a.format,a.base,a.capacity,a.metadata)
    output=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if a.out:
        with a.out.open('x',encoding='utf8') as stream:stream.write(output)
    else:print(output,end='')
    return 0


if __name__=='__main__':raise SystemExit(main())
