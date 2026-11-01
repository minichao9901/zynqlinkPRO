from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'etm-service/tools'))
from flame_html import build_data, export_html
from flame_svg import make_frames


class View:
    def __init__(self):
        self.closed=False
        self.rows=[dict(kind='instruction',seq=0,function='a',callPath=['a']),
                   dict(kind='instruction',seq=1,function='b',callPath=['a','b']),
                   dict(kind='event',seq=2,text='exception <boundary>'),
                   dict(kind='instruction',seq=3,function='a',callPath=['a']),
                   dict(kind='instruction',seq=4,function='a',callPath=['a'])]
        self.analysis=dict(timing={'timeFlameAvailable':True},flame={'name':'root','value':10,'valueCycles':20,'children':[
            {'name':'a','value':6,'valueCycles':12,'children':[]},
            {'name':'b','value':4,'valueCycles':8,'children':[]}]})

    def overview(self):return dict(eventCount=5,name='test trace',elf={'sha256':'1'*64},analysis=self.analysis)
    def window(self,*args):return {'analysis':self.analysis}
    def iter_events(self,low,high):
        try:yield from (r for r in self.rows if low<=r['seq']<=high)
        finally:self.closed=True


def payload(text):
    return json.loads(re.search(r'<script type="application/json" id="flame-data">(.*?)</script>',text,re.S)[1])


class FlameHtmlTests(unittest.TestCase):
    def test_timeline_matches_exact_svg_frames_and_event_gaps(self):
        view=View();data=build_data(view,0,4);original,_,_=make_frames(view.rows)
        actual=[(data['names'][f[0]],f[1],f[2],f[3]-1,f[4]) for f in data['frames']]
        self.assertEqual(actual,[(f['name'],f['depth'],f['start'],f['end'],f['parent']) for f in original])
        self.assertEqual(data['events'],[[2,'exception <boundary>']]);self.assertTrue(view.closed)
        self.assertEqual([f[2] for f in data['frames'] if f[1]==0],[0,3])

    def test_range_and_aggregate_weight_root_are_preserved(self):
        data=build_data(View(),3,4);self.assertEqual(data['domain'],[3,5])
        self.assertTrue(all(3<=f[2]<f[3]<=5 for f in data['frames']))
        data=build_data(View(),0,4,'aggregate','cycles','0')
        self.assertEqual(data['domain'],[0,12]);self.assertEqual(data['names'],['a'])
        with self.assertRaises(ValueError):build_data(View(),0,4,'aggregate','cycles','0.0')
        view=View();view.analysis['timing']['timeFlameAvailable']=False
        with self.assertRaises(ValueError):build_data(view,0,4,'aggregate','cycles')

    def test_invalid_ranges_and_timeline_cycle_axis_are_rejected(self):
        for low,high in [(0,None),(-1,2),(4,2),(0,5)]:
            with self.assertRaises(ValueError):build_data(View(),low,high)
        with self.assertRaises(ValueError):build_data(View(),0,4,'timeline','cycles')

    def test_full_depth_and_limit_failure_close_the_event_iterator(self):
        view=View();view.rows=[dict(kind='instruction',seq=0,callPath=['f'+str(i) for i in range(1500)])]
        self.assertEqual(build_data(view,0,0)['depth'],1500)
        view=View()
        with patch('flame_svg.MAX_FRAMES',1):
            with self.assertRaisesRegex(ValueError,'200000'):build_data(view)
        self.assertTrue(view.closed)

    def test_html_is_self_contained_and_script_names_are_data(self):
        view=View();name='</script><img src=x onerror="alert(1)"> & \u2028'
        view.rows[0]['callPath']=[name]
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'flame.html';info=export_html(view,out)
            text=out.read_text(encoding='utf-8');data=payload(text)
        self.assertIn(name,data['names']);self.assertNotIn('<img src=x',text)
        self.assertNotIn('<script src=',text);self.assertNotIn('<link ',text)
        self.assertIn("connect-src 'none'",text);self.assertTrue(info['selfContained'])
        self.assertIn('id="zoom-in"',text);self.assertIn('id="reset"',text)

    def test_offline_web_download_equals_cli_generator_and_cleans_temp_file(self):
        sys.path.insert(0,str(ROOT))
        from tools.zynq_bridge import application,locations
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory,patch.dict('os.environ'):
            data=Path(directory);token=data/'token';token.write_text('a'*64)
            _,backend,web,service,helpers=locations();app=application(backend,web,service,helpers,data,token,offline=True)
            module=sys.modules['etm_toolbox_backend'];folder=data/'records/capture-test';folder.mkdir(parents=True)
            with patch.object(module,'browse_store',return_value=View()):
                client=Client(app,Response)
                with client.get('/etm/api/download/capture-test/flame-html?fromSeq=0&toSeq=4',environ_overrides={'REMOTE_ADDR':'127.0.0.1'}) as response:
                    self.assertEqual(response.status_code,200,response.get_data())
                    actual=response.get_data();self.assertIn('attachment',response.headers['Content-Disposition'])
                    self.assertNotIn('离线验收：硬件访问已禁用',actual.decode())
                self.assertFalse(list(folder.glob('export-*.html')))
            expected=data/'expected.html';export_html(View(),expected,0,4)
            self.assertEqual(actual,expected.read_bytes())

    def test_portable_cli_rejects_hardware_before_loading_application(self):
        sys.path.insert(0,str(ROOT))
        from tools.zynq_bridge import main
        with patch('tools.zynq_bridge.application',side_effect=AssertionError('service forbidden')):
            self.assertEqual(main(['--trace-cli','capture']),2)
            self.assertEqual(main(['--trace-cli','target']),2)
            self.assertEqual(main(['--trace-cli','--help']),0)


if __name__=='__main__':unittest.main()
