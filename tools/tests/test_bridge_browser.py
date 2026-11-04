import io
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

from tools import zynq_bridge as bridge


class BrowserTests(unittest.TestCase):
    def test_windows_uses_argument_list_and_new_window(self):
        child = Mock(); child.wait.return_value = 0
        with patch.object(bridge.sys, 'platform', 'win32'), patch.object(bridge, 'FROZEN', False), \
             patch.object(bridge, 'windows_browsers', return_value=iter([Path('C:/Chrome/chrome.exe')])), \
             patch.object(bridge.subprocess, 'Popen', return_value=child) as launch, \
             patch.object(bridge.webbrowser, 'open') as shell:
            url = 'http://127.0.0.1:8882/?trace-cli=abc#etm'
            self.assertTrue(bridge.open_workbench(url))
            self.assertEqual(launch.call_args.args[0], ['C:\\Chrome\\chrome.exe', '--new-window', url])
            shell.assert_not_called()

    def test_failed_browser_tries_next_and_shell_failure_is_reported(self):
        child = Mock(); child.wait.return_value = 1
        with patch.object(bridge.sys, 'platform', 'win32'), patch.object(bridge, 'FROZEN', False), \
             patch.object(bridge, 'windows_browsers', return_value=iter([Path('chrome.exe'), Path('msedge.exe')])), \
             patch.object(bridge.subprocess, 'Popen', side_effect=[OSError('unavailable'), child]) as launch, \
             patch.object(bridge.webbrowser, 'open', return_value=False), patch('sys.stderr', new_callable=io.StringIO) as errors:
            self.assertFalse(bridge.open_workbench('http://127.0.0.1:8882/'))
            self.assertEqual(launch.call_count, 2)
            self.assertIn('请手动打开', errors.getvalue())

    def test_readiness_requires_matching_boot(self):
        wrong = Mock(); wrong.__enter__ = Mock(return_value=io.StringIO('{"bootId":"old"}')); wrong.__exit__ = Mock()
        ready = Mock(); ready.__enter__ = Mock(return_value=io.StringIO('{"bootId":"new"}')); ready.__exit__ = Mock()
        with patch.object(bridge, 'urlopen', side_effect=[wrong, ready]), \
             patch.object(bridge.time, 'sleep'), patch.object(bridge, 'open_workbench') as launch:
            bridge.open_when_ready('http://127.0.0.1:8882', 'browser-url', 'new')
            launch.assert_called_once_with('browser-url')

    def test_frozen_dll_directory_restored_on_error(self):
        import ctypes
        kernel = ctypes.WinDLL('kernel32')
        kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
        before = ctypes.create_unicode_buffer(32768)
        kernel.GetDllDirectoryW(len(before), before)
        try:
            kernel.SetDllDirectoryW(str(Path.cwd()))
            with patch.object(bridge, 'FROZEN', True):
                with self.assertRaisesRegex(RuntimeError, 'test'):
                    with bridge.system_dll_search():
                        cleared = ctypes.create_unicode_buffer(32768)
                        kernel.GetDllDirectoryW(len(cleared), cleared)
                        self.assertEqual(cleared.value, '')
                        raise RuntimeError('test')
            restored = ctypes.create_unicode_buffer(32768)
            kernel.GetDllDirectoryW(len(restored), restored)
            self.assertEqual(restored.value, str(Path.cwd()))
        finally:
            kernel.SetDllDirectoryW(before.value or None)


if __name__ == '__main__':
    unittest.main()
