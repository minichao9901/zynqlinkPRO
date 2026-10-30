"""Check that executable code fits Zynq OCM; report DDR buffers separately."""
import argparse
import json
from pathlib import Path
import struct


def inspect(path):
    data = Path(path).read_bytes()
    if data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('Expected little-endian ELF32')
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    shoff, shentsize, shnum, shstrndx = header[6], header[11], header[12], header[13]
    sections = [struct.unpack_from('<10I', data, shoff+i*shentsize) for i in range(shnum)]
    names_section = sections[shstrndx]
    names = data[names_section[4]:names_section[4]+names_section[5]]
    banks = [dict(name='low', start=0, limit=0x30000, sections=[]),
             dict(name='high', start=0xffff0000, limit=0xfffffe00, sections=[])]
    ddr_sections = []
    for s in sections:
        name = names[s[0]:].split(b'\0', 1)[0].decode()
        if not s[2] & 2 or not s[5]:
            continue
        addr, end = s[3], s[3]+s[5]
        bank = next((b for b in banks if b['start'] <= addr < end <= b['limit']), None)
        if bank is None:
            if s[2] & 4:
                raise ValueError(f'Executable section {name} outside OCM: {addr:#x}..{end:#x}')
            if not 0x100000 <= addr < end <= 0x40000000:
                raise ValueError(f'Data section {name} outside OCM/DDR: {addr:#x}..{end:#x}')
            ddr_sections.append(dict(name=name, address=addr, size=s[5], end=end))
            continue
        bank['sections'].append(dict(name=name, address=addr, size=s[5], end=end))
    for bank in banks:
        ordered = sorted(bank['sections'], key=lambda s:s['address'])
        for a,b in zip(ordered, ordered[1:]):
            if a['end'] > b['address']:
                raise ValueError(f'Overlapping sections: {a["name"]}, {b["name"]}')
        bank['span_bytes'] = max((s['end'] for s in ordered), default=bank['start'])-bank['start']
        bank['free_bytes'] = bank['limit']-bank['start']-bank['span_bytes']
    return dict(elf=str(path), banks=banks,
                ddr_sections=ddr_sections,
                ddr_section_bytes=sum(s['size'] for s in ddr_sections),
                executable_bytes=sum(s[5] for s in sections if s[2]&6==6),
                span_bytes=sum(b['span_bytes'] for b in banks),
                free_bytes=sum(b['free_bytes'] for b in banks),
                reserved_bytes=512, hardware_validation='not performed')


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf', type=Path)
    ap.add_argument('--output', type=Path)
    args=ap.parse_args()
    report=json.dumps(inspect(args.elf), indent=2)
    if args.output: args.output.write_text(report, encoding='utf-8')
    print(report)
