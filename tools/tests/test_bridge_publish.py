from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import json
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.build_bridge import publish,archive_application


class PublishTests(unittest.TestCase):
    def test_optional_zip_contains_only_program_files_and_never_user_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);_,out=self.setup_packages(root)
            (out/'package-manifest.json').write_text(json.dumps({'files':[{'path':'zynq-etm-bridge.exe'}]}))
            archive_application(out,root/'share.zip')
            with zipfile.ZipFile(root/'share.zip') as package:
                self.assertEqual(set(package.namelist()),{'zynq-etm-bridge/zynq-etm-bridge.exe','zynq-etm-bridge/package-manifest.json'})

    def setup_packages(self,root):
        candidate=root/'build/candidate';candidate.mkdir(parents=True)
        old=root/'dist/zynq-etm-bridge';old.mkdir(parents=True)
        for folder,text in [(candidate,b'new'),(old,b'old')]:
            (folder/'zynq-etm-bridge.exe').write_bytes(text)
            (folder/'package-manifest.json').write_text('{}')
        (old/'data/records').mkdir(parents=True)
        (old/'data/records/keep.json').write_text('user capture')
        return candidate,old

    def test_update_preserves_data_and_archives_old_program_and_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);candidate,old=self.setup_packages(root)
            Path(str(old)+'.zip').write_bytes(b'old zip')
            result=publish(candidate,old,root)
            self.assertEqual((old/'zynq-etm-bridge.exe').read_bytes(),b'new')
            self.assertEqual((old/'data/records/keep.json').read_text(),'user capture')
            self.assertEqual((Path(result['previousDirectory'])/'zynq-etm-bridge.exe').read_bytes(),b'old')
            self.assertEqual((Path(result['archiveDirectory'])/'previous.zip').read_bytes(),b'old zip')
            self.assertFalse(Path(str(old)+'.zip').exists());self.assertTrue(result['dataPreserved'])

    def test_copy_failure_rolls_back_old_program_and_data_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);candidate,old=self.setup_packages(root)
            def fail(source,destination):
                destination.mkdir();(destination/'partial').write_text('partial');raise OSError('disk full')
            with patch('tools.build_bridge.shutil.copytree',side_effect=fail):
                with self.assertRaisesRegex(OSError,'disk full'):publish(candidate,old,root)
            self.assertEqual((old/'zynq-etm-bridge.exe').read_bytes(),b'old')
            self.assertEqual((old/'data/records/keep.json').read_text(),'user capture')
            self.assertEqual(len(list((root/'build/bridge-archive').glob('*/failed-candidate/partial'))),1)

    def test_unknown_directory_and_outside_workspace_are_not_moved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);candidate,old=self.setup_packages(root)
            unknown=root/'dist/other';unknown.mkdir();(unknown/'keep').write_text('keep')
            with self.assertRaisesRegex(ValueError,'不是可识别'):publish(candidate,unknown,root)
            self.assertEqual((unknown/'keep').read_text(),'keep')
            with self.assertRaisesRegex(ValueError,'工作区'):publish(candidate,root.parent/'outside-bridge',root)


if __name__=='__main__':unittest.main()
