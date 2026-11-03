"""A local ignored input must not silently qualify as a deliverable dependency."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from tools import verify_dependencies


class DependencyTrackingTests(unittest.TestCase):
    def test_present_but_untracked_configure_template_is_rejected(self):
        root = Path(__file__).resolve().parents[2]
        path = 'etm-service/vendor/libdwarf-2.3.3/cmake/config.h.in'
        self.assertTrue((root / path).is_file())
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode('utf8').split('\0')
        self.assertIn(path, tracked)
        omitted = '\0'.join(name for name in tracked if name != path).encode('utf8')
        with patch.object(verify_dependencies.subprocess, 'check_output', return_value=omitted):
            result = verify_dependencies.verify(root, check_tracked=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failures'], ['untracked input: ' + path])


if __name__ == '__main__':
    unittest.main()
