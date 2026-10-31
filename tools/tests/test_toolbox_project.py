import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import project_cli as project

class ProjectCliTests(unittest.TestCase):
    def test_aliases_resolve_to_versioned_project_sources(self):
        entries={e['id']:e for e in project.inventory()}
        for name,path in project.ALIASES.items():
            self.assertIn(path,entries,name)
            self.assertTrue(entries[path]['runnable'],name)

    def test_workflow_script_paths_exist(self):
        for name,(_,steps) in project.WORKFLOWS.items():
            for _,arguments in steps:
                for argument in arguments:
                    if argument.endswith(('.py','.mjs')) and not any(c in argument for c in '*?['):
                        self.assertTrue((project.ROOT/argument).is_file(),(name,argument))

    def test_plan_does_not_execute_and_preserves_literal_arguments(self):
        with patch('subprocess.call') as run:
            result=project.plan('etm.cli',['query','--search','x & $(literal)'])
            self.assertEqual(result['steps'][0]['arguments'][-1],'x & $(literal)')
            run.assert_not_called()

    def test_unknown_or_path_traversal_is_not_an_execution_entry(self):
        with self.assertRaises(ValueError):project.plan('../../outside.py')
        with self.assertRaises(ValueError):project.plan('not-a-project-tool')

    def test_tcl_wrapper_preserves_arguments_as_data(self):
        text=project.tcl_wrapper('E:/project/tool.tcl',['a; exit 99','100% & x','你好'])
        self.assertNotIn('a; exit 99',text)
        self.assertIn('100% & x'.encode().hex(),text)
        self.assertIn('你好'.encode().hex(),text)

    def test_tcl_argument_adapter_roundtrips_without_evaluating_data(self):
        try:import tkinter
        except ImportError:self.skipTest('Tcl runtime is unavailable')
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'capture.tcl';script.write_text('set ::received $argv\n',encoding='utf8')
            arguments=['a; exit 99','100% & x','你好']
            interpreter=tkinter.Tcl();interpreter.eval(project.tcl_wrapper(str(script),arguments))
            self.assertEqual(list(interpreter.splitlist(interpreter.getvar('received'))),arguments)

    def test_dispatcher_uses_argument_arrays_and_keeps_native_exit_code(self):
        value=project.plan('etm.cli',['--help'])
        with patch('subprocess.call',return_value=7) as run:
            self.assertEqual(project.execute(value),7)
            self.assertIsInstance(run.call_args.args[0],list)
            self.assertNotIn('shell',run.call_args.kwargs)

    def test_build_fragment_is_described_but_not_run_standalone(self):
        fragment=project.resolve('fpga/compact_config.tcl')
        self.assertFalse(fragment['runnable'])
        with self.assertRaises(ValueError):project.plan('fpga/compact_config.tcl')

if __name__=='__main__':unittest.main()
