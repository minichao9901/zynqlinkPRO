"""Native breakpoint boundaries must match the retained ELF/Capstone reference."""
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'etm-service'),str(ROOT/'etm-service/tools')]
import decode_trace
import native_core
import breakpoint_resolver
from breakpoint_resolver import instruction_starts,resolve_breakpoint
from trace_cli import engine_environment

ELFS=[ROOT/'prebuilt/golden/f103ze-cdc48.elf',
      ROOT/'prebuilt/targets/stm32h743-cdc-trace-20261101/cpu60-trace20/fw.elf',
      ROOT/'prebuilt/targets/f103ze-hal-storage-20261104/fw.elf']

class NativeBreakpointTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{});self.env.start();engine_environment()

    def tearDown(self):self.env.stop()

    def reference(self,path):
        with patch.dict(os.environ,{'ETM_NATIVE_STATIC':'0'}):return decode_trace.Image(path)

    def test_every_instruction_start_matches_reference_including_literal_pool_exclusion(self):
        for path in ELFS:
            with self.subTest(elf=path.name):
                reference=self.reference(path);native=native_core.Image(path)
                try:
                    expected=instruction_starts(reference)
                    self.assertTrue(expected)
                    self.assertEqual(instruction_starts(native),expected)
                    symbols=reference.elf.get_section_by_name('.symtab')
                    data=[s['st_value'] for s in symbols.iter_symbols() if s.name=='$d' or s.name.startswith('$d.')]
                    self.assertTrue(data)
                    for address in data:self.assertNotIn(address,instruction_starts(native))
                finally:native.close()

    def test_function_source_and_raw_candidates_match_and_invalid_locations_stay_rejected(self):
        for path in ELFS:
            reference=self.reference(path);native=native_core.Image(path)
            try:
                starts=instruction_starts(reference)
                functions=[f for f in reference.functions if f[0] in starts and reference.location(f[0])[1]][:2]
                self.assertTrue(functions)
                for address,_,name in functions:
                    _,file,line=reference.location(address)
                    for spec in [name,f'b *{address:#x}',f'{file}:{line}',f'{name}:{line}']:
                        self.assertEqual(resolve_breakpoint(native,spec),resolve_breakpoint(reference,spec))
                for spec in ['b no_such_function','b *0x08000001','main.c:0','b *0x08000000']:
                    with self.assertRaises(ValueError):resolve_breakpoint(native,spec)
                    with self.assertRaises(ValueError):resolve_breakpoint(reference,spec)
            finally:native.close()

    def test_real_http_breakpoint_endpoint_does_not_enter_python_elf_parser(self):
        import server
        def forbidden(*args,**kwargs):raise AssertionError('Python ELF parsing entered native Web breakpoint path')
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder,patch.object(server,'RECORDS',Path(folder)),\
                patch.dict(os.environ,{'ETM_NATIVE_STATIC':'1'}),patch.object(decode_trace.Image,'_parse',forbidden),\
                patch.object(breakpoint_resolver,'Cs',forbidden):
            client=server.app.test_client()
            response=client.post('/api/elf',data={'elf':(io.BytesIO(ELFS[0].read_bytes()),'f103ze-cdc48.elf')})
            self.assertEqual(response.status_code,200,response.get_data(as_text=True))
            elf_id=response.json['elfId']
            result=client.post(f'/api/elf/{elf_id}/breakpoint',json={'spec':'b cdc_poll'})
            self.assertEqual(result.status_code,200,result.get_data(as_text=True))
            self.assertEqual(result.json['candidates'][0]['function'],'cdc_poll')
            bad=client.post(f'/api/elf/{elf_id}/breakpoint',json={'spec':'b *0x08000001'})
            self.assertNotEqual(bad.status_code,200)

if __name__=='__main__':unittest.main()
