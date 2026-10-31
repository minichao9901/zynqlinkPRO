"""Bounded, restored PS DDR address-alias experiment; no Flash or bulk writes.

Four 16-byte samples at +8MiB in each 256MiB quarter. This checks aliasing
at these addresses, not every DDR cell, sustained throughput, or cache policy.
Run only while capture/DMA clients are idle; the running ELF is checked first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
ADDRESSES=(0x00800000,0x10800000,0x20800000,0x30800000)


def script_for(elf):
    from elftools.elf.elffile import ELFFile
    with elf.open('rb') as f:
        image=ELFFile(f)
        occupied=[(s['sh_addr'],s['sh_addr']+s['sh_size'],s.name) for s in image.iter_sections() if s['sh_flags']&2 and s['sh_size']]
    for address in ADDRESSES:
        for lo,hi,name in occupied:
            if address<hi and lo<address+16:raise ValueError('Test address overlaps allocated ELF section '+name)
    addresses=' '.join(hex(a) for a in ADDRESSES)
    return '''connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
set addresses {'''+addresses+'''}
set backup [dict create]
# Gather all backups before the first write. No CPU reset, stop or continue.
foreach a $addresses {
  set words [mrd -force -value $a 4]
  if {[llength $words]!=4} {error "Incomplete backup"}
  dict set backup $a $words
  puts "DDR_BACKUP $a $words"
}
set rc [catch {
  puts DDR_WRITE_BEGIN
  set i 0
  foreach a $addresses {
    for {set j 0} {$j<4} {incr j} {
      mwr -force [expr {$a+4*$j}] [expr {0xa5190000 | ($i<<8) | $j}]
    }
    incr i
  }
  foreach a $addresses {puts "DDR_PATTERN $a [mrd -force -value $a 4]"}
} why]
# Every sampled location is restored even when a write/read raised an error.
# Aliased backups are equal because they were all collected before mutation.
set restore_errors {}
foreach a [lreverse $addresses] {
  set j 0
  foreach word [dict get $backup $a] {
    if {[catch {mwr -force [expr {$a+4*$j}] $word} msg]} {lappend restore_errors $msg}
    incr j
  }
}
foreach a $addresses {
  set restored [mrd -force -value $a 4]
  puts "DDR_RESTORED $a $restored"
  if {$restored ne [dict get $backup $a]} {lappend restore_errors "Restore mismatch at $a"}
}
disconnect
if {[llength $restore_errors]} {error $restore_errors}
if {$rc} {error $why}
puts DDR_RESTORE_VERIFIED
exit
'''


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True,help='ELF actually running on PS; code identity is checked before writes')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv);out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    script=script_for(a.elf.resolve())
    identity=subprocess.run([sys.executable,str(ROOT/'tools/verify_probe_ocm_code.py'),'--elf',str(a.elf.resolve()),'--out-dir',str(out/'identity')],capture_output=True,text=True)
    (out/'identity-console.txt').write_text(identity.stdout+identity.stderr,encoding='utf8')
    if identity.returncode:raise RuntimeError('Running PS code identity check failed; no DDR test writes issued')
    path=out/'geometry.tcl';path.write_text(script,encoding='utf8')
    run=subprocess.run([sys.executable,str(ROOT/'tools/run_xsct.py'),str(path)],capture_output=True,text=True,timeout=120)
    log=run.stdout+run.stderr;(out/'geometry.log').write_text(log,encoding='utf8')
    report=dict(elfSha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),hardware=True,flashWrites=False,
                cpuResetOrStop=False,addresses=[hex(x) for x in ADDRESSES],bytesPerAddress=16,
                restored='DDR_RESTORE_VERIFIED' in log,exitCode=run.returncode,
                writesAttempted='DDR_WRITE_BEGIN' in log,
                limitation='Four small samples only; not a full capacity, cache coherence or sustained DDR acceptance test')
    patterns={}
    for address,words in re.findall(r'DDR_PATTERN (0x[0-9a-fA-F]+) ([^\r\n]+)',log):
        patterns[int(address,16)]=[int(w,0) for w in words.split()]
    report['patterns']={hex(k):v for k,v in patterns.items()}
    report['distinctQuarterSamples']=len({tuple(v) for v in patterns.values()})
    report['allQuarterSamplesIndependent']=len(patterns)==4 and report['distinctQuarterSamples']==4
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    if run.returncode or not report['restored'] or len(patterns)!=4:raise RuntimeError('DDR geometry experiment incomplete; inspect geometry.log and backups')
    print(json.dumps(report,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
