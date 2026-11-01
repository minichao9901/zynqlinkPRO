"""Validated SRAM load plans for F103ZE clock/ETM experiments; no Flash writer."""
import struct
from elftools.elf.elffile import ELFFile

START, END = 0x20000000, 0x20010000


def plan(path):
    with open(path, 'rb') as stream:
        elf = ELFFile(stream)
        if elf.elfclass != 32 or not elf.little_endian or elf['e_machine'] != 'EM_ARM':
            raise ValueError('Requires a little-endian ARM ELF32')
        loads = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        if not loads:
            raise ValueError('No SRAM load segments')
        for s in loads:
            for field in ('p_paddr', 'p_vaddr'):
                if not START <= s[field] < END or s['p_memsz'] > END-s[field]:
                    raise ValueError('Every load segment must stay in F103ZE SRAM')
            if s['p_filesz'] > s['p_memsz']:
                raise ValueError('Invalid segment file/memory size')
        payloads = sorted((s['p_paddr'], s.data()) for s in loads if s['p_filesz'])
        for (a, data), (b, _) in zip(payloads, payloads[1:]):
            if a+len(data) > b:
                raise ValueError('Overlapping physical load segments')
        if not payloads or payloads[0][0] != START or len(payloads[0][1]) < 8:
            raise ValueError('SRAM vector table must start at 0x20000000')
        stack, entry = struct.unpack_from('<II', payloads[0][1])
        if not START < stack <= END or stack & 7:
            raise ValueError('Invalid SRAM initial stack')
        executable = [(s['p_vaddr'], s['p_vaddr']+s['p_filesz']) for s in loads if s['p_flags'] & 1]
        if not entry & 1 or elf['e_entry'] != entry or not any(a <= (entry & ~1) < b for a,b in executable):
            raise ValueError('SRAM vector/ELF entry mismatch')
        symbols = elf.get_section_by_name('.symtab')
        named = {s.name:int(s['st_value']) for s in symbols.iter_symbols()} if symbols else {}
        for name in ('g_sysclk_hz', 'g_clock_err'):
            if not START <= named.get(name, 0) <= END-4:
                raise ValueError('Missing SRAM firmware diagnostic symbol: '+name)
        return dict(stack=stack, entry=entry, payloads=payloads, symbols=named)
