import sys
from pathlib import Path
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from probe_coordinator import ProbeCoordinator, ProbeCancelled


class CoordinatorTests(unittest.TestCase):
    def test_capture_keeps_ownership_until_original_browser_restores_target(self):
        c=ProbeCoordinator();c.begin_capture('record','browser')
        with self.assertRaises(ValueError):c.acquire('usb','browser')
        self.assertTrue(c.finish_capture('record'))
        with self.assertRaises(ValueError):c.acquire('usb','other')
        c.acquire('usb','browser')
        with self.assertRaises(ValueError):c.complete_capture('record','other')
        c.complete_capture('record','browser');self.assertNotIn('capture',c.snapshot()['resources'])
        self.assertIn('usb',c.snapshot()['resources'])

    def test_capture_cannot_overtake_usb_or_failed_cleanup(self):
        c=ProbeCoordinator();c.acquire('usb','web')
        with self.assertRaises(ValueError):c.acquire('capture','trace')
        c.release('usb','web','STOP not confirmed')
        with self.assertRaises(ValueError):c.acquire('usb','web')
        with self.assertRaises(ValueError):c.acquire('capture','trace')
        c.release('usb','other')
        self.assertIn('usb',c.snapshot()['resources'])
        c.release('usb','web');c.acquire('capture','trace')
        with self.assertRaises(ValueError):c.acquire('hid','scope')

    def test_queued_cancel_does_not_execute_or_cancel_another_owner(self):
        c=ProbeCoordinator();entered=threading.Event();release=threading.Event();calls=[]
        def first():
            with c.operation('one','write'):
                entered.set();release.wait(2);calls.append('one')
        def second():
            with c.operation('two','write'):calls.append('two')
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(first);self.assertTrue(entered.wait(1));b=pool.submit(second)
            for _ in range(1000):
                if c.snapshot()['pending']:break
                threading.Event().wait(.001)
            self.assertEqual(c.cancel('two')['requested'],1)
            with self.assertRaises(ProbeCancelled):b.result(timeout=2)
            release.set();a.result(timeout=2)
        self.assertEqual(calls,['one'])
        with c.operation('three','read'):calls.append('three')
        self.assertIsNone(c.snapshot()['current'])

    def test_running_cancel_is_observed_at_boundary_and_queue_survives_failure(self):
        c=ProbeCoordinator()
        with self.assertRaises(ProbeCancelled):
            with c.operation('one','bulk') as check:
                self.assertTrue(c.cancel('one')['activeMustDrain']);check()
        with self.assertRaises(RuntimeError):
            with c.operation('two','failure'):raise RuntimeError('transport')
        with c.operation('three','read'):pass
        self.assertEqual(c.snapshot()['cancelled'],1)
        self.assertEqual(c.snapshot()['failed'],1)
