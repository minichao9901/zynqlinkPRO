"""Offline real-Web flame export acceptance on an already decoded trace record."""
import hashlib
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from tools.f103_stream_acceptance import Streams


class Exports(Streams):
    def button(self,label):
        controls=self.page('etm','describe')['controls']
        matches=[c for c in controls if (c.get('text') or c['label'])==label]
        if len(matches)!=1:raise RuntimeError('Export control missing/ambiguous: '+label)
        return matches[0]['selector']

    def download(self,label,filename,start=None,end=None):
        before={f['id'] for f in self.page('etm','downloads')}
        started=time.perf_counter()
        mode='aggregate' if label.startswith('aggregate') else 'timeline'
        self.invoke('etm','exportFlame',{'mode':mode,'weight':'records','rootPath':''},{'captureOnly':True},target='history')
        deadline=time.monotonic()+180
        while True:
            files=[f for f in self.page('etm','downloads') if f['id'] not in before]
            if files:break
            if time.monotonic()>deadline:raise TimeoutError('Flame export did not create a download')
            time.sleep(.1)
        data=self.download_latest('etm',self.out/filename)
        root=ET.fromstring(data);ns={'s':'http://www.w3.org/2000/svg'}
        if root.tag!='{http://www.w3.org/2000/svg}svg':raise RuntimeError('Not an SVG document')
        frames=root.findall('.//s:g[@data-frame]',ns)
        names=[e.text or '' for e in root.findall('.//s:text',ns)]
        if not frames or not any('cdc_poll' in n for n in names):raise RuntimeError('SVG has no expected trace frames')
        if start is not None:
            spans=[(int(f.attrib['data-start']),int(f.attrib['data-end'])) for f in frames]
            if any(a<start or b>end for a,b in spans):raise RuntimeError('SVG export escaped the selected sequence range')
        return {'label':label,'file':filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'secondsIncludingCliDownload':time.perf_counter()-started,'frames':len(frames),
                'width':root.get('width'),'height':root.get('height'),'title':root.findtext('s:title',namespaces=ns),
                'fromSeq':start,'toSeq':end,'explicitCliCapture':True,'actualUiButton':False}

    def test(self):
        self.page('etm','show')
        opening=self.invoke('etm','measureOpenRecord',self.args.record)
        if not opening['painted']:raise RuntimeError('ETM view is not painted')
        self.page('etm','click',selector='[data-view="flame"]');self.invoke('etm','render',target='history')
        rows=[]
        self.invoke('etm','setRange',{'start':2,'end':2000},target='history')
        rows.append(self.download('timeline selected range','timeline-range.svg',2,2000))
        zoom=self.invoke('etm','measureZoom',True,target='history')
        selected=zoom['range']
        rows.append(self.download('timeline after zoom','timeline-zoom.svg',selected['start'],selected['end']))
        self.page('etm','click',selector=self.button('按调用权重'));self.invoke('etm','render',target='history')
        rows.append(self.download('aggregate selected range','aggregate-range.svg'))
        self.invoke('etm','setRange',None,target='history')
        rows.append(self.download('aggregate full record','aggregate-full.svg'))
        report={'record':self.args.record,'hardwareOperations':False,'opening':opening,'zoom':zoom,'exports':rows}
        self.save(self.out/'results.json',report)
        # The exact execution-order exporter is deliberately bounded; test the full-record boundary too.
        self.page('etm','click',selector=self.button('按执行顺序'));self.invoke('etm','render',target='history')
        started=time.perf_counter()
        try:
            self.invoke('etm','exportFlame',{'mode':'timeline','weight':'records','rootPath':''},{'captureOnly':True},target='history')
            data=self.download_latest('etm',self.out/'timeline-full.svg');root=ET.fromstring(data)
            report['fullTimeline']={'status':'PASS','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'width':root.get('width')}
        except RuntimeError as error:
            if '200000' not in str(error):raise
            report['fullTimeline']={'status':'LIMITED','error':str(error),'frameLimit':200000}
        report['fullTimeline']['secondsIncludingCli']=time.perf_counter()-started
        self.save(self.out/'results.json',report)
        self.invoke('etm','setRange',{'start':2,'end':2000},target='history')
        return report


def run(args):
    if not args.record:raise ValueError('flame-export requires --record ID')
    check=Exports(args)
    try:result=check.test()
    except Exception as error:
        check.save(check.out/'failure.json',{'error':str(error),'steps':len(check.steps)})
        raise
    check.save(check.out/'summary.json',result)
    return {'ok':True,**result}
