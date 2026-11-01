import struct
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from f103_ram_image import plan


class RamImageTests(unittest.TestCase):
    def test_ram_commands_reject_flash_elf_before_creating_a_hardware_run(self):
        golden=ROOT/'prebuilt/golden/f103ze-cdc48.elf'
        with tempfile.TemporaryDirectory() as folder:
            for script,options in [
                ('run_f103_ram_fixture.py',['--hclk-mhz','72','--','unused-child']),
                ('test_orbtrace_board.py',['--ram-image','--bit','unused.bit','--elf','unused.elf'])]:
                output=Path(folder)/script
                command=[sys.executable,str(ROOT/'tools'/script),'--target-elf',str(golden),'--output',str(output),*options]
                run=subprocess.run(command,capture_output=True,cwd=ROOT)
                self.assertNotEqual(run.returncode,0)
                self.assertIn(b'SRAM',run.stderr)
                self.assertFalse(output.exists())

    def test_flash_elf_is_rejected_before_any_loader_access(self):
        with self.assertRaisesRegex(ValueError,'SRAM'):
            plan(ROOT/'prebuilt/golden/f103ze-cdc48.elf')

    def test_out_of_range_ram_segment_and_vector_entry_are_rejected(self):
        source=ROOT/'firmware/target/stm32f103_cdc_trace/build/ze-72-ram/fw.elf'
        if not source.exists():self.skipTest('Build the RAM firmware to exercise its ELF')
        raw=source.read_bytes();valid=plan(source)
        self.assertEqual(valid['stack'],0x20010000)
        self.assertEqual(valid['payloads'][0][0],0x20000000)
        phoff=struct.unpack_from('<I',raw,28)[0]
        first_offset=struct.unpack_from('<I',raw,phoff+4)[0]
        for offset,value in [(phoff+12,0x08000000),(first_offset,0x20020000),(first_offset+4,0x20000000)]:
            broken=bytearray(raw);struct.pack_into('<I',broken,offset,value)
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'bad.elf';path.write_bytes(broken)
                with self.assertRaises(ValueError):plan(path)


if __name__=='__main__':unittest.main()
