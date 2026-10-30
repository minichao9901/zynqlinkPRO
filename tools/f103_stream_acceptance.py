"""Real Web RTT forwarding and J-Scope rate/integrity campaigns; no browser eval."""
import base64
import csv
import io
import json
from pathlib import Path
import re
import time

from elftools.elf.elffile import ELFFile
from tools.f103_web_acceptance import Acceptance

ROOT=Path(__file__).resolve().parents[1]


def symbol(elf,name):
    with Path(elf).open('rb') as handle:
        section=ELFFile(handle).get_section_by_name('.symtab')
        found=section.get_symbol_by_name(name)
        if not found:raise ValueError('ELF symbol missing: '+name)
        return int(found[0]['st_value'])


class Streams(Acceptance):
    def invoke(self,page,method,*args,target='view'):
        return self.page(page,'invoke',method=method,args=list(args),target=target)

    def set(self,page,selector,value):
        return self.page(page,'set',selector=selector,value=value)

    def flash(self):
        from toolbox import pack_file
        elf=Path(self.args.elf).resolve()
        item=pack_file(elf);item['name']=elf.parent.name+'.elf'
        self.set('flash','#f-backend','openocd');self.set('flash','#f-chip','stm32f103')
        self.page('flash','upload',selector='@file:view._fileInput',files=[item])
        self.wait('flash','#f-file-info',item['name'])
        self.invoke('flash','flash')
        result=self.page('flash','read',selector='#f-result')['text']
        if '已校验' not in result or '已复位运行' not in result:raise RuntimeError(result)
        return result

    def download_latest(self,page,path):
        files=self.page(page,'downloads')
        if not files:raise RuntimeError('Web没有生成导出文件')
        item=files[-1];data=bytearray()
        while len(data)<item['bytes']:
            part=self.page(page,'download',id=item['id'],offset=len(data),length=min(1<<20,item['bytes']-len(data)))
            data.extend(base64.b64decode(part['base64']))
        path.write_bytes(data);self.page(page,'discard',id=item['id'])
        return bytes(data)

    def scope(self):
        from toolbox import pack_file
        self.call({'action':'disconnect'})
        programmed=self.flash()
        self.invoke('scope','setMock',False)
        self.invoke('scope','connectHid',False);self.invoke('scope','connectUsb',False)
        self.set('scope','#sc-target','swd')
        self.page('scope','upload',selector='@file:view.elfInput',files=[pack_file(self.args.elf)])
        self.wait('scope','#sc-elfinfo',Path(self.args.elf).name)
        self.set('scope','#sc-clock','50000')
        self.set('scope','#sc-cdcoff',True);self.set('scope','#sc-batch',True)
        self.set('scope','#sc-seconds','5')
        base=symbol(self.args.elf,'g_pack')
        selected=dict(name='g_pack.u_hi',addr=base+20,scalar='u32',size=4,scale=1,offset=0)
        self.page('scope','click',selector='#sc-varclear')
        self.invoke('scope','toggleVar',selected,True)
        self.invoke('scope','bench')
        rows=[]
        try:
            for period in [float(v) for v in self.args.periods.split(',')]:
                self.set('scope','#sc-period',str(period))
                self.invoke('scope','start')
                before=self.invoke('scope','summary')
                if not before['running']:raise RuntimeError('J-Scope启动失败: '+str(before))
                time.sleep(self.args.stream_seconds)
                live=self.invoke('scope','summary')
                self.invoke('scope','stop','CLI finite acceptance window')
                summary=self.invoke('scope','summary')
                self.invoke('scope','exportCsv')
                data=self.download_latest('scope',self.out/f'period-{period:g}us.csv')
                samples=list(csv.DictReader(io.StringIO(data.decode('utf8'))))
                values=[int(float(r['g_pack.u_hi'])) for r in samples]
                bad=sum((v&0xffff0000)!=0x10000000 for v in values)
                backwards=sum(((b-a)&0xffff)>32768 for a,b in zip(values,values[1:]))
                valid=bool(values and not bad and not backwards and not summary['lostGap'] and
                           not summary['lostUsb'] and not summary['readErrors'] and not summary['metricsError'])
                row=dict(requestedPeriodUs=period,valid=valid,samplesChecked=len(values),bad=bad,
                         counterBackwards=backwards,live=live,summary=summary)
                rows.append(row);self.save(self.out/'results.json',{'suite':'scope','rows':rows})
                print('scope',period,'us, samples',len(values),'rateHz',live['rateHz'],'valid',valid,flush=True)
                if not valid:raise RuntimeError('J-Scope数据完整性失败；未自动重试')
        finally:
            self.invoke('scope','stop','CLI cleanup');self.invoke('scope','disconnect')
        return dict(ok=True,suite='scope',flash=programmed,rows=rows)

    def rttcdc(self):
        self.call({'action':'disconnect'})
        programmed=self.flash()
        cb=symbol(self.args.elf,'_SEGGER_RTT')
        self.invoke('rttcdc','connect',target='hid')
        self.set('rttcdc','#h-target','swd');self.set('rttcdc','#h-addr',hex(cb))
        self.set('rttcdc','#h-size','256');self.set('rttcdc','#h-chan','0')
        self.invoke('rttcdc','refreshPorts')
        desc=self.page('rttcdc','describe')
        ports=next(x for x in desc['controls'] if x['selector']=='#c-port')['options']
        match=[x for x in ports if 'COM33' in x['label']]
        if len(match)!=1:raise RuntimeError('COM33 probe CDC missing/ambiguous')
        self.set('rttcdc','#c-port',match[0]['value']);self.set('rttcdc','#c-ts',False)
        self.set('rttcdc','#c-record-auto',False);self.invoke('rttcdc','connect')
        rows=[]
        try:
            for hz in [int(v) for v in self.args.clocks.split(',')]:
                self.set('rttcdc','#h-clock',str(hz))
                self.invoke('rttcdc','applyClock',target='hid')
                self.page('rttcdc','click',selector='#c-clear');self.page('rttcdc','click',selector='#c-statclear')
                started=time.perf_counter();self.invoke('rttcdc','start',target='hid')
                engine=self.invoke('rttcdc','summary',target='hid')
                if not engine['running']:raise RuntimeError('RTT forwarding did not start: '+str(engine))
                before=self.invoke('rttcdc','summary');t0=time.perf_counter()
                time.sleep(self.args.stream_seconds)
                after=self.invoke('rttcdc','summary');t1=time.perf_counter()
                self.invoke('rttcdc','stop',target='hid')
                time.sleep(.1)
                self.invoke('rttcdc','refresh',target='hid')
                engine=self.invoke('rttcdc','summary',target='hid')
                summary=self.invoke('rttcdc','summary')
                self.invoke('rttcdc','save')
                data=self.download_latest('rttcdc',self.out/f'clock-{hz}.txt')
                matches=list(re.finditer(rb'seq (\d{7})\r\n',data))
                adjacent=all(a.end()==b.start() for a,b in zip(matches,matches[1:]))
                gaps=sum((int(b[1])-int(a[1]))%10000000!=1 for a,b in zip(matches,matches[1:]))
                prefix=matches[0].start() if matches else len(data)
                tail=len(data)-matches[-1].end() if matches else len(data)
                valid=bool(matches and adjacent and not gaps and prefix<=12 and tail<=12 and
                           len(data)==summary['bytes'] and summary['buffered']==summary['bytes'] and
                           not engine['rdErr'])
                row=dict(requestedClockHz=hz,valid=valid,bytes=len(data),recordsChecked=len(matches),
                         sequenceGaps=gaps,unparsedPrefix=prefix,unparsedTail=tail,
                         webBytesPerSecond=(after['bytes']-before['bytes'])/(t1-t0),
                         hostWindowSeconds=t1-t0,totalCaseSeconds=time.perf_counter()-started,
                         engine=engine,summary=summary)
                rows.append(row);self.save(self.out/'results.json',{'suite':'rttcdc','rows':rows})
                print('rttcdc',hz,'Hz',round(row['webBytesPerSecond']),'B/s, valid',valid,flush=True)
                if not valid:raise RuntimeError('RTT sequence/byte accounting failed; no automatic retry')
        finally:
            self.invoke('rttcdc','stop',target='hid');self.invoke('rttcdc','disconnect',target='hid')
            self.invoke('rttcdc','close',target='session')
        return dict(ok=True,suite='rttcdc',flash=programmed,rows=rows)


def run(args):
    if not .1<=args.stream_seconds<=3:raise ValueError('stream-seconds must be 0.1..3')
    campaign=Streams(args)
    try:result=getattr(campaign,args.suite)()
    except Exception as error:
        campaign.save(campaign.out/'failure.json',{'ok':False,'error':str(error)})
        raise
    campaign.save(campaign.out/'summary.json',result)
    return result
