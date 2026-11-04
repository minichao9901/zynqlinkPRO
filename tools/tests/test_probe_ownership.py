import sys
from pathlib import Path
import subprocess
import unittest
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from probe_ownership import Ownership,bind_usb


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'probe.lock'
    def child(self):
        source="import sys;sys.path.insert(0,sys.argv[1]);from probe_ownership import Ownership;x=Ownership(sys.argv[2]);x.close()"
        return subprocess.run([sys.executable,'-c',source,str(Path(__file__).resolve().parents[2]/'etm-service/tools'),str(self.path)],capture_output=True).returncode

    def test_process_exclusion_and_reference_counted_release(self):
        a=Ownership(self.path);b=Ownership(self.path)
        try:
            self.assertNotEqual(self.child(),0)
            a.close();self.assertNotEqual(self.child(),0)
        finally:a.close();b.close()
        self.assertEqual(self.child(),0)
        self.assertLess(self.path.stat().st_size,32)

    def test_usb_dispose_and_reopen_reacquire_ownership(self):
        class Context:
            def managed_open(self):pass
            def dispose(self,device,close_handle=True):pass
        class Device:_ctx=Context()
        lease=Ownership(self.path);device=bind_usb(Device(),lease)
        try:
            device._ctx.dispose(device);self.assertFalse(lease.held)
            device._ctx.managed_open();self.assertTrue(lease.held)
            device._ctx.dispose(device,close_handle=False);self.assertTrue(lease.held)
        finally:lease.close()
