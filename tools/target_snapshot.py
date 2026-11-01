"""Read target identity and clock controls without writing peripheral registers."""


def snapshot(mem):
    cpuid = mem.word(0xe000ed00)
    part = (cpuid >> 4) & 0xfff
    if part == 0xc27:
        device = mem.word(0x5c001000)
        if device & 0xfff != 0x450:
            raise RuntimeError(f'Unsupported M7 device: {device:#x}')
        addresses = [0x58024400, 0x58024410, 0x58024418, 0x5802441c,
                     0x58024420, 0x58024428, 0x5802442c, 0x58024430,
                     0x58024434, 0x58024438, 0x52002000]
        name = 'STM32H743/H742/H750/H753'
    elif part == 0xc23:
        device = mem.word(0xe0042000)
        addresses = [0x40021000, 0x40021004]
        name = 'STM32F103'
    else:
        raise RuntimeError(f'Unsupported target CPUID: {cpuid:#x}')
    return dict(name=name, cpuid=hex(cpuid), device=hex(device),
                registers={hex(a): hex(mem.word(a)) for a in addresses})
