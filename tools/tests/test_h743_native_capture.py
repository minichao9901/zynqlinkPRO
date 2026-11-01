"""Verify H7 routing and restoration on both success and transport failure."""
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import h743_trace_capture as h7


class Registers:
    def __init__(self):
        self.values={0xe000edf0:0x1010001,h7.ETM+0x10:1,h7.ETM+0xc:1,
                     h7.ETF+0xc:4,h7.TPIU+0x300:2,h7.ETM+0x1e4:0x4100f401}
        for base in (h7.ETM,h7.FUNNEL,h7.ETF,h7.TPIU):self.values[base+0xfb4]=3
        self.writes=[]
        self.fail_restore=False

    def word(self,address):return self.values.get(address,0)
    def read(self,address,size):return bytes(size)
    def write_word(self,address,value):
        if self.fail_restore and address==h7.ETM+0x10 and value==1:
            raise RuntimeError('injected cleanup failure')
        self.writes.append((address,value))
        self.values[address]=value
        if address==0xe000edf0:self.values[address]=0x1010000|(value&3)|(0x20000 if value&2 else 0)
        if address&0xfff==0xfb0:self.values[address+4]=1 if value else 3
        if address==h7.ETF+0x304:self.values[address]&=~0x40


class NativeH743Tests(unittest.TestCase):
    def exercise(self,failed):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);elf=folder/'target.elf';elf.write_bytes(b'elf-mocked')
            args=SimpleNamespace(entry=None,reset_to_entry=False,usb_reconnect=False,ram_image=False,
                hclk_div=1,raw=False,ddr_physical=False,sync=False,transport='auto',target_elf=elf,
                gpio_speed=2,output=folder,trace_id=2,ready_file=None,elf=elf,milliseconds=10,
                verify_ddr_physical=False)
            mem=Registers();before=dict(mem.values);report={}
            segment={'p_type':'PT_LOAD','p_paddr':0x08000000,'p_filesz':4}
            segment=type('Segment',(dict,),{'data':lambda self:bytes(4)})(segment)
            device=Mock();device.ctrl_transfer.return_value=struct.pack('<4I',200000000,0,0,0x301)
            clocks=dict(device='0x20036450',registers={})
            with patch.object(h7,'snapshot',return_value=clocks),patch.object(h7,'ELFFile') as reader,patch('etm_ddr_usb_capture.capture') as capture:
                reader.return_value.iter_segments.return_value=[segment]
                if failed=='cleanup':
                    def finish(*args):
                        mem.fail_restore=True
                        return b'etm',dict(quality={'loss':False},actualWindowSeconds=.01,usbOwnerReleased=True)
                    capture.side_effect=finish
                elif failed=='usbcleanup':capture.return_value=(b'etm',dict(quality={'loss':False},cleanupError='injected USB owner release failure'))
                elif failed:capture.side_effect=RuntimeError('injected USB download failure')
                else:capture.return_value=(b'etm',dict(quality={'loss':False},actualWindowSeconds=.01,usbOwnerReleased=True))
                if failed=='cleanup':
                    with self.assertRaisesRegex(RuntimeError,'injected cleanup'):h7.capture(args,device,None,None,mem,report)
                elif failed=='usbcleanup':
                    with self.assertRaisesRegex(RuntimeError,'injected USB owner'):h7.capture(args,device,None,None,mem,report)
                elif failed:
                    with self.assertRaisesRegex(RuntimeError,'injected USB'):h7.capture(args,device,None,None,mem,report)
                else:h7.capture(args,device,None,None,mem,report)
            if failed=='cleanup':
                self.assertIn('injected cleanup failure',report['target_cleanup_error'])
                self.assertFalse(report['capture_passed'])
                return
            self.assertTrue(report['restored'])
            self.assertEqual(report['rcc_before'],report['rcc_after'])
            self.assertEqual(report['config']['protocol'],'ETMv4')
            self.assertEqual(report['config']['config'],0x1011)
            self.assertNotIn(h7.ETM,[a for a,v in mem.writes])
            for address,value in before.items():self.assertEqual(mem.word(address),value,hex(address))
            self.assertEqual(bool(report.get('capture_passed')),not failed)

    def test_success_restores_h7_registers(self):self.exercise(False)
    def test_download_failure_restores_h7_registers(self):self.exercise(True)
    def test_cleanup_failure_cannot_be_accepted(self):self.exercise('cleanup')
    def test_usb_owner_release_failure_cannot_be_accepted(self):self.exercise('usbcleanup')

    def test_f103_entry_options_are_rejected_before_memory_access(self):
        mem=Mock()
        with self.assertRaisesRegex(ValueError,'continuous DDR'):
            h7.capture(SimpleNamespace(entry='main'),None,None,None,mem,{})
        mem.word.assert_not_called();mem.write_word.assert_not_called()


if __name__=='__main__':unittest.main()
