from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.test_etm_ddr_memory import reservation,expected_chunk


class MemoryPilotGuard(unittest.TestCase):
    def test_pattern_matches_address_dependent_little_endian_words_and_partial_tail(self):
        seed=0x12345678
        self.assertEqual(expected_chunk(0,13,seed),struct.pack('<4I',*[0xddaa0000^seed^i for i in range(4)])[:13])
        self.assertEqual(expected_chunk(16,7,seed),struct.pack('<2I',0xddaa0000^seed^4,0xddaa0000^seed^5)[:7])
        with self.assertRaises(ValueError):expected_chunk(1,8,seed)

    def test_plain_golden_elf_is_rejected_before_loading_or_writing(self):
        with self.assertRaisesRegex(ValueError,'explicit absolute reservation'):
            reservation(Path(__file__).resolve().parents[2]/'prebuilt/golden/application.elf')

    def test_reservation_rejects_allocated_overlap_and_nonabsolute_symbols(self):
        rows={'__etm_ddr_base':{'st_value':0x10000000,'st_shndx':'SHN_ABS'},
              '__etm_ddr_end':{'st_value':0x30000000,'st_shndx':'SHN_ABS'}}
        symbols=SimpleNamespace(get_symbol_by_name=lambda name:[rows[name]])
        sections=[];image=SimpleNamespace(get_section_by_name=lambda name:symbols,iter_sections=lambda:iter(sections))
        with tempfile.TemporaryDirectory() as folder:
            elf=Path(folder)/'reserved.elf';elf.write_bytes(b'mocked ELF for guard branches')
            with patch('elftools.elf.elffile.ELFFile',return_value=image):
                self.assertEqual(reservation(elf),(0x10000000,0x30000000))
                class Section(dict):name='unexpected data'
                sections.append(Section(sh_addr=0x20000000,sh_size=64,sh_flags=2))
                with self.assertRaisesRegex(ValueError,'overlaps DDR capture'):reservation(elf)
                sections.clear();rows['__etm_ddr_base']['st_shndx']=3
                with self.assertRaisesRegex(ValueError,'absolute reservation'):reservation(elf)


if __name__=='__main__':unittest.main()
