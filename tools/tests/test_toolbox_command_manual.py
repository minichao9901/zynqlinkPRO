from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from tools import command_manual


ROOT = Path(__file__).resolve().parents[2]


class CommandManualTests(unittest.TestCase):
    def test_manual_uses_authenticated_fixed_actions_and_blocks_hardware_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'cli-token'
            token.write_text('a' * 64)
            app = Flask(__name__)
            command_manual.install(app, token, ROOT, sys.executable, offline=True)
            client = app.test_client()
            headers = {'X-Trace-CLI': 'a' * 64, 'Origin': 'http://localhost'}
            self.assertEqual(client.get('/command-manual').status_code, 403)
            rows = client.get('/command-manual', headers=headers).json['rows']
            commands = [row for row in rows if 'id' in row]
            self.assertEqual({row['id'] for row in commands}, set(command_manual.BY_NAME))
            self.assertEqual(len(commands), 27)
            self.assertTrue(next(row for row in commands if row['id'] == 'program')['disabled'])
            self.assertTrue(next(row for row in commands if row['id'] == 'qspi-write-no-backup')['disabled'])
            self.assertTrue(next(row for row in commands if row['id'] == 'qspi-rebuilt-write')['disabled'])
            self.assertFalse(next(row for row in commands if row['id'] == 'qspi-package')['disabled'])
            self.assertEqual(client.post('/command-manual/run', headers={**headers, 'Origin': 'http://other'},
                                         json={'id': 'python'}).status_code, 403)
            self.assertEqual(client.post('/command-manual/run', headers=headers,
                                         json={'id': 'python -c anything'}).status_code, 404)
            self.assertEqual(client.post('/command-manual/run', headers=headers,
                                         json={'id': 'program', 'confirmed': True}).status_code, 403)
            result = client.post('/command-manual/run', headers=headers,
                                 json={'id': 'workspace', 'value': 'ignored'}).json
            finished = client.get('/command-manual/job/' + result['job'], headers=headers).json
            self.assertEqual(finished['exitCode'], 0)
            self.assertIn(str(ROOT), finished['output'])

    def test_firmware_path_is_one_argument_and_runtime_is_the_current_workbench(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            image = folder / 'fw & with spaces.elf'
            image.touch()
            command = command_manual.BY_NAME['program']
            with (folder / 'log').open('wb') as log, patch.object(command_manual.subprocess, 'Popen') as launch:
                command_manual.start_command(command, str(image), ROOT, folder, folder, sys.executable, log)
            argv, = launch.call_args.args
            self.assertEqual(argv[argv.index('--file') + 1], str(image.resolve()))
            self.assertEqual(argv[argv.index('--runtime') + 1], str(folder))
            self.assertFalse(launch.call_args.kwargs.get('shell', False))

    def test_cold_boot_checks_use_a_fresh_evidence_directory_per_click(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            command = command_manual.BY_NAME['qspi-cold']
            with (runtime / 'log').open('wb') as log, patch.object(command_manual.subprocess, 'Popen') as launch:
                for job in ('first', 'second'):
                    command_manual.start_command(command, '', ROOT, runtime, runtime / job, sys.executable, log)
            for call, job in zip(launch.call_args_list, ('first', 'second')):
                argv, = call.args
                self.assertEqual(argv[argv.index('--out-dir') + 1], str(runtime / job / 'artifacts'))
