"""Physical Zynq MEM-AP0 access, independent of Cortex-A9 cache/debug context.

CPU-context mrd can return old 32-byte cache lines after autonomous PL writes.
Use this path to verify DMA destinations; this does not make CPU/DMA accesses
cache coherent. The caller still owns address ranges and quiescence checks.
"""
import re


class PhysicalMemory:
    def __init__(self,session):self.session=session

    def run(self,body):
        # Installed SDK 2018.3 xsdb.tcl documents AP<n> address spaces and
        # requires selecting APU. Do not inject CPU loads or flush dirty CPU
        # cache lines over newly written DMA data during an MMIO command.
        return self.session.run('''targets -set -filter {name =~ "APU"}
proc physrd {args} {return [mrd -address-space AP0 {*}$args]}
proc physwr {args} {return [mwr -address-space AP0 -bypass-cache-sync {*}$args]}
'''+body)

    def read_words(self,address,count=1):
        output=self.run(f'puts "VALUES [physrd -force -value {address:#x} {count}]"')
        found=re.search(r'VALUES ([^\r\n]+)',output)
        if not found:raise RuntimeError('XSCT did not return physical memory values: '+output)
        words=[int(word,0) for word in found[1].split()]
        if len(words)!=count:raise RuntimeError('Incomplete physical memory read')
        return words
