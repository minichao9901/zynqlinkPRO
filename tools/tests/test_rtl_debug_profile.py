from pathlib import Path
import tkinter
import unittest

ROOT=Path(__file__).resolve().parents[2]


class RtlDebugProfileTests(unittest.TestCase):
    def interpreter(self):
        t=tkinter.Tcl()
        present=t.eval('info exists ::env(ZYNQLINK_RTL_DEBUG)')=='1'
        original=t.getvar('::env(ZYNQLINK_RTL_DEBUG)') if present else None
        self.addCleanup(lambda:t.setvar('::env(ZYNQLINK_RTL_DEBUG)',original) if present else t.eval('unset -nocomplain ::env(ZYNQLINK_RTL_DEBUG)'))
        t.eval('unset -nocomplain ::env(ZYNQLINK_RTL_DEBUG)')
        t.call('source',str(ROOT/'fpga/rtl_debug_profile.tcl'))
        return t

    def test_explicit_release_debug_and_legacy_selection(self):
        t=self.interpreter()
        self.assertEqual(int(t.call('zynqlink_rtl_debug_mode','')),0)
        self.assertEqual(int(t.call('zynqlink_rtl_debug_mode','--diagnostics')),1)
        t.setvar('::env(ZYNQLINK_RTL_DEBUG)','0')
        self.assertEqual(int(t.call('zynqlink_rtl_debug_mode','')),0)
        with self.assertRaises(tkinter.TclError):t.call('zynqlink_rtl_debug_mode','--diagnostics')
        t.setvar('::env(ZYNQLINK_RTL_DEBUG)','1')
        self.assertEqual(int(t.call('zynqlink_rtl_debug_mode','')),1)
        for invalid in ('false','2','-1',''):
            t.setvar('::env(ZYNQLINK_RTL_DEBUG)',invalid)
            with self.assertRaises(tkinter.TclError):t.call('zynqlink_rtl_debug_mode','')


if __name__=='__main__':unittest.main()
