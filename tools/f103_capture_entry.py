"""F103 hardware breakpoint entry, with comparator state kept for restoration."""
import time
from elftools.elf.elffile import ELFFile

DHCSR, DCRSR, DCRDR, DEMCR = 0xE000EDF0, 0xE000EDF4, 0xE000EDF8, 0xE000EDFC
FP_CTRL, FP_COMP = 0xE0002000, 0xE0002008


class UsbReconnect:
    """Hold F103 PA12 low while stopped before USB initialization.

    F103 boards with an external D+ pull-up otherwise keep the old host device
    address across a CPU/peripheral reset. Restore only the touched pin/clock.
    """
    def __init__(self, memory):
        self.mem, self.saved = memory, None

    def disconnect(self):
        m = self.mem
        self.saved = (m.word(0x40021018) & 4, m.word(0x40010804) & 0xF0000,
                      m.word(0x4001080C) & 0x1000)
        m.write_word(0x40021018, m.word(0x40021018) | 4)
        m.write_word(0x40010810, 1 << 28)
        m.write_word(0x40010804, (m.word(0x40010804) & ~0xF0000) | 0x20000)
        time.sleep(.02)

    def restore(self):
        if self.saved is None:
            return
        m = self.mem
        clock, mode, level = self.saved
        m.write_word(0x40010810, 1 << (12 if level else 28))
        m.write_word(0x40010804, (m.word(0x40010804) & ~0xF0000) | mode)
        m.write_word(0x40021018, (m.word(0x40021018) & ~4) | clock)
        self.saved = None


def resolve_entry(elf, entry):
    if entry is None:
        return None
    if isinstance(entry, bool) or not isinstance(entry, (str, int)):
        raise ValueError('断点起点须为函数名或地址')
    with open(elf, 'rb') as stream:
        image = ELFFile(stream)
        if isinstance(entry, int) or entry.lower().startswith('0x'):
            address = entry if isinstance(entry, int) else int(entry, 16)
        else:
            symbols = image.get_section_by_name('.symtab')
            found = {int(s['st_value']) & ~1 for s in symbols.iter_symbols()
                     if s.name == entry and s['st_info']['type'] == 'STT_FUNC'} if symbols else set()
            if len(found) != 1:
                raise ValueError('ELF起点函数不存在或不唯一：' + entry)
            address = found.pop()
        address &= ~1
        if not any(s['p_type'] == 'PT_LOAD' and int(s['p_flags']) & 1 and
                   int(s['p_vaddr']) <= address < int(s['p_vaddr']) + int(s['p_filesz'])
                   for s in image.iter_segments()):
            raise ValueError('起点不在此ELF可执行加载段内')
        if not 0x08000000 <= address < 0x08080000:
            raise ValueError('本入口只支持F103ZE Flash硬件断点')
        return address


class CaptureEntry:
    def __init__(self, memory):
        self.mem = memory
        self.saved = None
        self.failed = False

    def pc(self):
        self.mem.write_word(DCRSR, 15)
        # REGRDY may still describe the preceding transfer at the write boundary.
        time.sleep(.001)
        for _ in range(100):
            if self.mem.word(DHCSR) & (1 << 16):
                return self.mem.word(DCRDR) & ~1
            time.sleep(.001)
        raise RuntimeError('读取断点PC超时')

    def wait_halt(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.mem.word(DHCSR) & (1 << 17):
                return
            time.sleep(.001)
        raise RuntimeError('等待采集起点超时；目标保持暂停')

    def prepare(self, address, reset=False, timeout=5):
        m = self.mem
        control = m.word(FP_CTRL)
        count = ((control >> 8) & 0x70) | ((control >> 4) & 15)
        if not 1 <= count <= 16:
            raise RuntimeError('目标没有可用的FPB代码比较器')
        self.saved = {'control': control, 'comparators': [m.word(FP_COMP + 4*i) for i in range(count)]}
        demcr = m.word(DEMCR)
        try:
            for i in range(count):
                m.write_word(FP_COMP + 4*i, 0)
            if reset:
                m.write_word(DEMCR, demcr | 1)
                m.write_word(0xE000ED0C, 0x05FA0004)
                time.sleep(.01)
                self.wait_halt(timeout)
                m.write_word(DEMCR, demcr)
            m.write_word(FP_CTRL, control | 3)
            comparator = (address & 0x1FFFFFFC) | (0x80000000 if address & 2 else 0x40000000) | 1
            m.write_word(FP_COMP, comparator)
            m.write_word(0xE000ED30, 0x1F)
            m.write_word(DHCSR, 0xA05F0001)
            self.wait_halt(timeout)
            actual = self.pc()
            if actual != address:
                raise RuntimeError(f'断点命中PC不符：{actual:#x}，预期{address:#x}')
            # Capture must run past the trigger without retriggering the FPB.
            m.write_word(FP_COMP, 0)
            return {'address': address, 'pc': actual, 'resetToEntry': reset, 'matched': True,
                    'savedFpb': self.saved}
        except BaseException:
            self.failed = True
            m.write_word(DHCSR, 0xA05F0003)
            m.write_word(DEMCR, demcr)
            raise

    def restore(self):
        if self.saved is None:
            return True
        m = self.mem
        for i, value in enumerate(self.saved['comparators']):
            m.write_word(FP_COMP + 4*i, value)
        m.write_word(FP_CTRL, self.saved['control'] | 2)
        return all(m.word(FP_COMP + 4*i) == value for i, value in enumerate(self.saved['comparators'])) and \
            bool(m.word(FP_CTRL) & 1) == bool(self.saved['control'] & 1)
