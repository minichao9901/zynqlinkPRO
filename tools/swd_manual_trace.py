"""Read DPIDR via stopped, per-edge CSR writes, bypassing the SWD engine.

The caller must explicitly load and identify a main-probe bit/ELF pair.
XSCT sets the clock and data pins directly; this does not write target RAM.
"""
import argparse,json,re
from pathlib import Path
from jtag_internal_trace import run
from probe_build_info import provenance


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bit',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    body=r'''
set original [mrd -force -value 0x40010080]
proc pins {clock data release} {
 mwr -force 0x40010080 [expr {$release ? 0 : 2}]
 mwr -force 0x40010094 [expr {0x100 | $clock | ($data<<1)}]
}
proc tick {data release} {pins 0 $data $release;pins 1 $data $release}
set failure [catch {
 pins 1 1 0
 set observer [mrd -force -value 0x400100f8]
 if {($observer>>16)==0x5343} {mwr -force 0x400100f8 1;mwr -force 0x400100f8 0}
 for {set i 0} {$i<64} {incr i} {tick 1 0}
 for {set i 0} {$i<16} {incr i} {tick [expr {(0xe79e>>$i)&1}] 0}
 for {set i 0} {$i<64} {incr i} {tick 1 0}
 for {set i 0} {$i<8} {incr i} {tick 0 0}
 for {set i 0} {$i<8} {incr i} {tick [expr {(0xa5>>$i)&1}] 0}
 pins 1 1 1
 tick 1 1
 for {set i 0} {$i<36} {incr i} {
  pins 0 1 1;set lo [expr {([mrd -force -value 0x40010094]>>1)&1}]
  pins 1 1 1;set hi [expr {([mrd -force -value 0x40010094]>>1)&1}]
  puts "EDGE $i $lo $hi"
 }
 tick 1 1
 for {set i 0} {$i<8} {incr i} {tick 0 0}
 if {($observer>>16)==0x5343} {
  puts [format "CLOCK %08X %08X" [mrd -force -value 0x400100f8] [mrd -force -value 0x400100fc]]
 }
} message]
catch {mwr -force 0x40010094 0}
catch {mwr -force 0x40010080 $original}
if {$failure} {error $message}
'''
    output=run(body)
    rows=[dict(index=int(i),before_rise=int(lo),after_rise=int(hi))
          for i,lo,hi in re.findall(r'EDGE (\d+) ([01]) ([01])',output)]
    assert len(rows)==36,output
    bits=[v['before_rise'] for v in rows]
    ack=sum(v<<i for i,v in enumerate(bits[:3]))
    data=sum(v<<i for i,v in enumerate(bits[3:35]))
    parity=bits[35]
    report=dict(artifacts=provenance(a.bit,a.elf),kind='main probe manual CSR DPIDR',
                bits=rows,ack=ack,data=hex(data),parity=parity,
                parity_matches=(data.bit_count()&1)==parity,
                passed=ack==1 and data==0x1ba01477 and (data.bit_count()&1)==parity)
    match=re.search(r'CLOCK ([0-9A-Fa-f]{8}) ([0-9A-Fa-f]{8})',output)
    if match:
        c,f=[int(v,16) for v in match.groups()]
        report['clock_observer']=dict(pad_rises=(c>>8)&255,intended_rises=c&255,
                                      rise_while_low=bool(f&8),fall_while_high=bool(f&4))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.with_suffix('.log').write_text(output)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='bits'}))
    return int(not report['passed'])


if __name__=='__main__':raise SystemExit(main())
