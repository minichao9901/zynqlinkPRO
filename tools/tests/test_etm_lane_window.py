from pathlib import Path
import contextlib
import hashlib
import io
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from calibrate_etm_lanes import choose_window,excitation
import calibrate_etm_lanes as calibration


class LaneWindowTests(unittest.TestCase):
    def test_only_fully_measured_nonwrapping_windows_are_candidates(self):
        self.assertIsNone(choose_window({i:True for i in range(31)}))
        points={i:8<=i<=18 for i in range(32)}
        self.assertEqual(choose_window(points)['tap'],13)
        self.assertEqual(choose_window(points)['width'],11)
        self.assertIsNone(choose_window({i:i<3 or i>28 for i in range(32)}))
        self.assertEqual(choose_window({i:True for i in range(32)})['tap'],15)

    def test_unexcited_lanes_cannot_claim_a_window_from_clean_parser_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'frames';path.write_bytes(bytes(4096))
            self.assertFalse(excitation(path)['excited'])
            path.write_bytes(bytes(range(256))*32)
            self.assertTrue(excitation(path)['excited'])

    def scan(self,folder,unexpected=False,echo_error=None):
        pair=folder/'pair';pair.mkdir();files={}
        for name in ('probe.bit','application.elf','ps7_init.tcl'):
            (pair/name).write_bytes(b'offline-only identity fixture');files[name]={'sha256':hashlib.sha256((pair/name).read_bytes()).hexdigest()}
        (pair/'manifest.json').write_text(json.dumps(dict(files=files)))
        elf=folder/'target.elf';elf.write_bytes(b'ELF parsing is delegated to the mocked capture process')
        output=folder/'scan';calls=[];configurations=[]
        class Control:
            def snapshot(self):return dict(enabled=False,taps=[0]*5)
            def configure(self,enabled,taps):configurations.append((enabled,list(taps)));return dict(ack=True)
        class Echo:
            rows=[]
            def __init__(self,port):pass
            def start(self):pass
            def close(self):return dict(rows=[],error=echo_error)
        def capture(command,**kwargs):
            point=Path(command[command.index('--output')+1]);point.mkdir();(point/'ddr').mkdir()
            calls.append(command);first=len(calls)==1
            raw=bytes(range(256))*32;(point/'ddr/capture.frm1').write_bytes(raw)
            q=dict(synced=True,loss=first,ended=True,stopReason=0,hardwareStartBracketUnix=[10,10.001],hardwareSeconds=.01,
                diagnostics=dict(frameDrops=0,writerError=0,idelayReadyLosses=0,parserErrors=17 if first else 0))
            acceptance=dict(restored=True,fpb_restored=True,rcc_before=[1,2],rcc_after=[1,2])
            if first:acceptance['error']='USB identity failure' if unexpected else 'DDR hardware quality/window failed'
            (point/'acceptance.json').write_text(json.dumps(acceptance))
            (point/'ddr/result.json').write_text(json.dumps(dict(quality=q,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())))
            return SimpleNamespace(returncode=int(first),stdout=b'',stderr=b'')
        argv=['calibrate','--pair',str(pair),'--target-elf',str(elf),'--out',str(output),'--coarse','0','--coarse-only']
        caught=None;code=None
        def session(folder,*args):
            self.assertTrue(folder.is_dir(),'Session requires an existing output directory')
            return object()
        with patch.object(sys,'argv',argv),patch.object(calibration,'LaneDelay',return_value=Control()),patch.object(calibration,'Session',side_effect=session),patch.object(calibration,'PhysicalMemory'),patch.object(calibration,'Echo',Echo),patch.object(calibration.subprocess,'run',side_effect=capture),contextlib.redirect_stdout(io.StringIO()):
            try:code=calibration.main()
            except RuntimeError as e:caught=str(e)
        report=json.loads((output/'result.json').read_text())
        return code,caught,report,calls,configurations

    def test_bad_calibration_point_is_retained_without_replay_and_coarse_is_not_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            code,error,report,calls,configurations=self.scan(Path(folder))
        self.assertEqual(code,0);self.assertIsNone(error);self.assertEqual(len(calls),2)
        self.assertFalse(report['rows'][0]['protocolPass']);self.assertTrue(report['rows'][1]['protocolPass'])
        self.assertFalse(report['passed']);self.assertTrue(report['coarseComplete']);self.assertFalse(report['candidateRetained'])
        self.assertEqual(configurations,[(False,[0]*5),(True,[0]*5),(False,[0]*5)])

    def test_unexpected_transport_error_stops_scan_and_restores_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            _,error,report,calls,configurations=self.scan(Path(folder),unexpected=True)
        self.assertIn('Unexpected capture',error);self.assertEqual(len(calls),1);self.assertFalse(report['passed'])
        self.assertEqual(configurations[-1],(False,[0]*5));self.assertIn('restoration',report)

    def test_coarse_completion_cannot_hide_an_echo_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            code,error,report,_,configurations=self.scan(Path(folder),echo_error='CDC mismatch')
        self.assertIsNone(code);self.assertIn('Calibration/echo',error);self.assertEqual(report['echoError'],'CDC mismatch')
        self.assertFalse(report['passed']);self.assertEqual(configurations[-1],(False,[0]*5))


if __name__=='__main__':unittest.main()
