from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from f103_capture_entry import CaptureEntry, UsbReconnect, resolve_entry, DHCSR, DCRDR, FP_CTRL, FP_COMP


class Memory:
    def __init__(self):
        self.values = {FP_CTRL: 0x61, FP_COMP: 0x48000101, DCRDR: 0x08002278,
                       DHCSR: (1 << 17) | (1 << 16)}
        self.writes = []

    def word(self, address):
        return self.values.get(address, 0)

    def write_word(self, address, value):
        self.writes.append((address, value))
        if address != DHCSR:
            self.values[address] = value


class EntryTests(unittest.TestCase):
    def test_resolves_actual_elf_function_and_rejects_non_code_addresses(self):
        elf = ROOT / 'etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf'
        self.assertEqual(resolve_entry(elf, 'usbd_initialize'), 0x08002278)
        self.assertEqual(resolve_entry(elf, '0x08002279'), 0x08002278)
        for entry in ('missing_function', 0x20000000, True):
            with self.assertRaises(ValueError):
                resolve_entry(elf, entry)

    def test_entry_comparator_is_removed_for_capture_and_originals_are_restored(self):
        memory = Memory()
        entry = CaptureEntry(memory)
        report = entry.prepare(0x08002278)
        self.assertTrue(report['matched'])
        self.assertEqual(memory.word(FP_COMP), 0)
        self.assertIn((FP_COMP, 0x48002279), memory.writes)
        self.assertTrue(entry.restore())
        self.assertEqual(memory.word(FP_COMP), 0x48000101)

    def test_wrong_pc_is_failure_and_original_breakpoints_remain_recoverable(self):
        memory = Memory()
        memory.values[DCRDR] = 0x08000300
        entry = CaptureEntry(memory)
        with self.assertRaisesRegex(RuntimeError, 'PC'):
            entry.prepare(0x08002278)
        self.assertTrue(entry.failed)
        self.assertIn((DHCSR, 0xA05F0003), memory.writes)
        self.assertTrue(entry.restore())

    def test_usb_reconnect_preserves_other_gpio_pins_and_trace_clock_enable(self):
        memory = Memory()
        memory.values.update({0x40021018: 0x4D, 0x40010804: 0x44444444, 0x4001080C: 0x1000})
        usb = UsbReconnect(memory)
        usb.disconnect()
        self.assertEqual(memory.word(0x40010804), 0x44424444)
        memory.values[0x40021018] |= 0x80
        usb.restore()
        self.assertEqual(memory.word(0x40010804), 0x44444444)
        self.assertEqual(memory.word(0x40021018), 0xCD)


if __name__ == '__main__':
    unittest.main()
