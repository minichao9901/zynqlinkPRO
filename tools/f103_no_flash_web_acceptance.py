"""Real-Web F103 CDC/ETM acceptance without programming QSPI or target Flash."""
import base64
import csv
import io
import hashlib
import json
from pathlib import Path
import time
import re

from tools.f103_stream_acceptance import Streams, symbol

ROOT=Path(__file__).resolve().parents[1]


class NoFlash(Streams):
    def __init__(self,args):
        super().__init__(args)
        from serial.tools.list_ports import comports
        ports=[p.device for p in comports() if p.vid==0xf055 and p.pid==0x1031]
        if len(ports)!=1:raise ValueError('Expected one F103 CDC F055:1031 target: '+str(ports))
        self.target_port=ports[0]
        probes=[p.device for p in comports() if p.vid==0x0d28 and p.pid==0x0204]
        if len(probes)!=1:raise ValueError('Expected one Zynq probe CDC port: '+str(probes))
        self.probe_cdc=probes[0]

    def call(self,payload):
        op=payload.get('op');method=payload.get('method')
        safe_flash=(op in ('read','describe','state','show') or op=='invoke' and method=='readIdcode' or
                    op=='set' and payload.get('selector')=='#f-backend' and payload.get('value')=='webusb')
        if payload.get('action') in ('flash','probe-flash') or (
            payload.get('page')=='flash' and not safe_flash) or (
            op=='invoke' and method in ('flash','erase','program')):
            raise ValueError('no-flash acceptance refuses a programming action')
        return super().call(payload)

    def flash(self):
        raise ValueError('no-flash acceptance never programs a target')

    def serial(self,label):
        self.page('serial','show')
        self.set('serial','#s-ts',False)
        self.invoke('serial','refreshPorts')
        controls=self.page('serial','describe')['controls']
        ports=next(x for x in controls if x['selector']=='#s-port')['options']
        matches=[p for p in ports if re.search(r'\b'+re.escape(self.target_port)+r'\b',p['label'])]
        if len(matches)!=1:raise RuntimeError('F103 CDC port is missing or ambiguous: '+self.target_port)
        self.set('serial','#s-port',matches[0]['value']);self.set('serial','#s-dtr',True)
        self.set('serial','#s-eol','none');self.invoke('serial','connect')
        rows=[]
        try:
            for command,expected in [('PING\n','PONG'),('INFO\n','sysclk=48000000')]:
                self.page('serial','click',selector='#s-clear')
                if not self.invoke('serial','send',command):raise RuntimeError('Web serial send failed')
                value=self.wait('serial','#s-rx',expected)
                rows.append({'sent':command,'expected':expected,'receivedText':value['text']})
            self.page('serial','click',selector='#s-clear')
            payload='ABCDEFGHIJKLMNOP0123456789abcdef'*2
            if not self.invoke('serial','send',payload):raise RuntimeError('Web serial 64-byte send failed')
            self.wait('serial','#s-rx',payload);self.invoke('serial','save')
            data=self.download_latest('serial',self.out/(label+'-serial64.txt'))
            if data!=payload.encode():raise RuntimeError('serial export differs from 64-byte payload: '+repr(data))
            rows.append({'payloadBytes':64,'byteExact':True,'sha256':hashlib.sha256(data).hexdigest()})
        finally:self.invoke('serial','close',target='session')
        return rows

    def capture(self,label,options,required=()):
        self.page('etm','show')
        started=time.perf_counter();value=self.invoke('etm','captureNative',options)
        self.invoke('etm','waitForDisplay',target='history')
        sid=value['record'];folder=ROOT/'etm-service/records'/sid
        decoded=json.loads((folder/'decoded.json').read_text(encoding='utf8'))
        session=json.loads((folder/'session.json').read_text(encoding='utf8'))
        manifest=json.loads((folder/'store/manifest.json').read_text(encoding='utf8'))
        quality=decoded['quality'];capture_quality=session['quality']
        if not (capture_quality['synced'] and capture_quality['ended'] and not capture_quality['loss'] and
                value['targetRestored'] and quality['packetIssues']==quality['unprocessedBytes']==quality['unaccountedBytes']==0 and
                decoded['status']['lastErrorCode']==0 and manifest['engine']['name']=='native' and not manifest['engine']['fallback']):
            raise RuntimeError('capture/native quality failed: '+str(sid))
        absent=set(required)-decoded['summary']['functions'].keys()
        if absent:raise RuntimeError('expected execution functions absent: '+str(absent))
        if any((folder/n).exists() for n in ['native.jsonl','events.jsonl','elements.jsonl','packets.jsonl','browse-v3.sqlite']):
            raise RuntimeError('legacy intermediate appeared')
        row={'record':sid,'label':label,'wallSecondsIncludingCliAndDisplay':time.perf_counter()-started,
             'capture':value,'summary':decoded['summary'],'quality':quality,'captureQuality':capture_quality,
             'storeEngine':manifest['engine'],'etmBytes':(folder/'capture.bin').stat().st_size,
             'etmSha256':hashlib.sha256((folder/'capture.bin').read_bytes()).hexdigest()}
        self.save(self.out/(label+'.json'),row)
        return row

    def rtt(self):
        self.page('rtt','show')
        self.set('rtt','#r-backend','webusb');self.set('rtt','#r-target','swd')
        self.set('rtt','#r-usb-clock','1000');self.set('rtt','#r-addr',hex(symbol(self.args.elf,'_SEGGER_RTT')))
        self.invoke('rtt','connectProbe')
        try:
            deadline=time.monotonic()+10
            while True:
                status=self.invoke('rtt','summary')
                if not status['connected'] or not status['running']:raise RuntimeError('RTT connection failed: '+str(status))
                if status['stats']['bytes']>0:break
                if time.monotonic()>deadline:raise TimeoutError('RTT did not receive application boot log')
                time.sleep(.1)
            if not status['connected'] or not status['running'] or status['backend']!='webusb' or status['stats'].get('corrupt',0):
                raise RuntimeError('RTT state failed: '+str(status))
            saved=self.invoke('rtt','saveRaw');data=self.download_latest('rtt',self.out/'application-rtt.bin')
            if len(data)!=saved['bytes'] or b'SYSCLK=48000000' not in data or b'usb initialized' not in data:
                raise RuntimeError('RTT raw log does not identify the running CDC application')
            return {'status':status,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'applicationBootLogVerified':True}
        finally:self.invoke('rtt','disconnect')

    def scope(self):
        self.page('scope','show')
        self.invoke('scope','setMock',False)
        self.invoke('scope','connectHid',False);self.invoke('scope','connectUsb',False)
        endpoint=self.page('scope','read',selector='#sc-usbinfo')['text']
        if 'EP 0x87' not in endpoint:raise RuntimeError('scope is not using the Zynq HSS IN7 endpoint')
        self.set('scope','#sc-target','swd');self.set('scope','#sc-clock','1000')
        self.set('scope','#sc-cdcoff',True);self.set('scope','#sc-batch',True)
        self.set('scope','#sc-period','1000');self.set('scope','#sc-seconds','5');self.set('scope','#sc-raw',True)
        self.page('scope','click',selector='#sc-varclear')
        base=symbol(self.args.elf,'g_trace')
        fields=['magic','sysclk_hz','ready','loops','marks','cyc_last','cyc_delta','usb_rx']
        for index,name in enumerate(fields):
            self.invoke('scope','toggleVar',{'name':'g_trace.'+name,'addr':base+4*index,'scalar':'u32','size':4,'scale':1,'offset':0},True)
        self.invoke('scope','bench')
        try:
            began=time.monotonic()
            self.invoke('scope','start');status=self.invoke('scope','summary')
            if not status['running'] or status['mode']!='real':raise RuntimeError('scope failed to start real acquisition')
            deadline=began+5
            while status['samples']<100 and status['running'] and time.monotonic()<deadline:
                time.sleep(.1);status=self.invoke('scope','summary')
            startupSeconds=time.monotonic()-began
            self.save(self.out/'scope-startup.json',{'seconds':startupSeconds,'status':status})
            if not status['definitionReceived'] or status['samples']<100:
                raise RuntimeError('J-Scope did not receive a valid definition and 100 live samples: '+str(status))
            time.sleep(1)
            self.invoke('scope','stop','finite no-flash acceptance')
            status=self.invoke('scope','summary');clocks=self.clocks();self.invoke('scope','exportCsv')
            data=self.download_latest('scope',self.out/'application-scope.csv')
            rows=list(csv.DictReader(io.StringIO(data.decode('utf8'))))
            values=lambda name:[int(float(row['g_trace.'+name])) for row in rows]
            loops=values('loops')
            if not (len(rows)>=100 and all(v==0x31524354 for v in values('magic')) and
                    all(v==48000000 for v in values('sysclk_hz')) and all(v==1 for v in values('ready')) and
                    any(a!=b for a,b in zip(loops,loops[1:])) and
                    all(((b-a)&0xffffffff)<0x80000000 for a,b in zip(loops,loops[1:])) and
                    not any(status.get(k) for k in ['lostGap','lostProbe','lostUsb','readErrors','metricsError'])):
                raise RuntimeError('scope live-counter/constant/continuity validation failed: '+str(status))
            return {'status':status,'endpoint':endpoint,'liveClocks':clocks,'rows':len(rows),'fieldCount':8,'startupSeconds':startupSeconds,
                    'constantsAndMonotonicLoopVerified':True,'sha256':hashlib.sha256(data).hexdigest()}
        finally:
            self.invoke('scope','stop','CLI cleanup')
            try:
                if self.invoke('scope','summary').get('raw'):
                    self.invoke('scope','saveRaw');self.download_latest('scope',self.out/'application-scope.jsp')
            finally:self.invoke('scope','disconnect')

    def debug_steps(self):
        elf=Path(self.args.elf);entry=symbol(elf,'cdc_poll')&~1
        self.call({'action':'connect','swdHz':1000000})
        self.call({'action':'elf','name':elf.name,'data':base64.b64encode(elf.read_bytes()).decode('ascii')})
        self.page('dbg','show');rows=[]
        try:
            for trial in range(self.args.rounds):
                self.call({'action':'command','commands':['halt','bd all','b cdc_poll','c']})
                self.call({'action':'wait-halt','timeoutMs':3000})
                pcs=[];modes=[]
                for offset in [2,6,8,10,12]:
                    if trial%2:self.call({'action':'command','commands':['si']})
                    else:
                        mode=self.invoke('dbg','step',target='session')
                        if mode!='dhcsr':raise RuntimeError('native step fell back: '+str(mode))
                    status=self.invoke('dbg','summary')
                    if status['pc']!=entry+offset or status['lastStepOk'] is not True:
                        raise RuntimeError('step did not reach exact instruction PC: '+str(status))
                    pcs.append(status['pc']);modes.append(status['lastStepMode'])
                rows.append({'trial':trial+1,'entry':entry,'expectedOffsets':[2,6,8,10,12],
                             'pcs':pcs,'modes':modes,'interface':'command si' if trial%2 else 'page session.step'})
                self.call({'action':'command','commands':['bd all','c']})
        finally:
            self.call({'action':'command','commands':['bd all','c']});self.call({'action':'disconnect'})
        return {'rounds':rows,'exactSteps':5*len(rows)}

    def identity(self):
        self.page('flash','show');self.set('flash','#f-backend','webusb')
        before=self.page('flash','read',selector='#f-log')['text']
        self.invoke('flash','readIdcode')
        after=self.page('flash','read',selector='#f-log')['text']
        if not after.startswith(before):raise RuntimeError('identity log rotated during verification')
        text=after[len(before):]
        if '0x414' not in text or '512' not in text:raise RuntimeError('identity does not match F103ZE: '+text)
        return {'readOnly':True,'text':text}

    def rttcdc(self):
        # Refill the real application's finite boot log after RTT Viewer drained it.
        capture=self.capture('usb-init-for-rttcdc',{'seconds':.1,'entry':'cdc_acm_init','resetToEntry':True,
            'usbReconnect':True,'hclkDiv':4,'gpioSpeed':1,'swdKhz':1000,'traceId':2,'decode':True})
        self.page('rttcdc','show');self.invoke('rttcdc','connect',target='hid')
        try:
            self.set('rttcdc','#h-target','swd');self.set('rttcdc','#h-addr',hex(symbol(self.args.elf,'_SEGGER_RTT')))
            self.set('rttcdc','#h-size','256');self.set('rttcdc','#h-chan','0');self.set('rttcdc','#h-clock','20000000')
            self.invoke('rttcdc','applyClock',target='hid');self.invoke('rttcdc','refreshPorts')
            ports=next(c for c in self.page('rttcdc','describe')['controls'] if c['selector']=='#c-port')['options']
            matches=[p for p in ports if re.search(r'\b'+re.escape(self.probe_cdc)+r'\b',p['label'])]
            if len(matches)!=1:raise RuntimeError('expected probe CDC '+self.probe_cdc)
            self.set('rttcdc','#c-port',matches[0]['value']);self.set('rttcdc','#c-ts',False)
            self.set('rttcdc','#c-record-auto',False)
            self.page('rttcdc','click',selector='[data-group="crxmode"] [data-v="ascii"]')
            self.invoke('rttcdc','connect')
            self.page('rttcdc','click',selector='#c-clear');self.invoke('rttcdc','start',target='hid')
            self.wait('rttcdc','#c-rx','usb initialized')
            self.invoke('rttcdc','stop',target='hid');self.invoke('rttcdc','refresh',target='hid')
            engine=self.invoke('rttcdc','summary',target='hid');status=self.invoke('rttcdc','summary');clocks=self.clocks()
            self.invoke('rttcdc','save');data=self.download_latest('rttcdc',self.out/'application-rtt-cdc.txt')
            if engine['running'] or engine['rdErr'] or b'SYSCLK=48000000' not in data or b'usb initialized' not in data:
                raise RuntimeError('RTT-to-CDC application log or stop verification failed')
            return {'capture':capture['record'],'engine':engine,'status':status,'liveClocks':clocks,'exportBytes':len(data),
                    'sha256':hashlib.sha256(data).hexdigest(),'applicationBootLogVerified':True,'throughputBenchmark':False}
        finally:
            self.invoke('rttcdc','stop',target='hid');self.invoke('rttcdc','disconnect',target='hid')
            self.invoke('rttcdc','close',target='session')

    def flow(self):
        report={'noFlash':True,'serialBefore':self.serial('before')};self.save(self.out/'results.json',report)
        self.page('etm','show');self.load_etm()
        report['usbInitialization']=self.capture('usb-initialization',{
            'seconds':.1,'entry':'cdc_acm_init','resetToEntry':True,'usbReconnect':True,
            'hclkDiv':4,'gpioSpeed':1,'swdKhz':1000,'traceId':2,'decode':True},
            ('cdc_acm_init','usbd_initialize','usb_dc_init'))
        report['serialAfterReset']=self.serial('after-reset');self.save(self.out/'results.json',report)
        report['cdcEcho']=self.capture('cdc-echo',{
            'seconds':.2,'entry':'cdc_poll','resetToEntry':False,'hclkDiv':4,'gpioSpeed':1,'swdKhz':1000,
            'traceId':2,'decode':True,'serialStimulus':{'port':self.target_port,'payload':'ETM_CDC_ECHO_0123456789abcdef\r\n',
            'rounds':4,'intervalSeconds':.02}},('usbd_cdc_acm_bulk_out','usbd_cdc_acm_bulk_in'))
        self.save(self.out/'results.json',report)
        report['rtt']=self.rtt();self.save(self.out/'results.json',report)
        report['scope']=({'status':'DEFERRED','reason':'Known intermittent missing DEF; skipped explicitly'} if getattr(self.args,'skip_scope',False) else self.scope())
        self.save(self.out/'results.json',report)
        report['debug']=self.debug_steps();self.save(self.out/'results.json',report)
        report['identity']=self.identity();self.save(self.out/'results.json',report)
        report['rttcdc']=self.rttcdc()
        if report['rttcdc']['sha256']!=report['rtt']['sha256']:raise RuntimeError('RTT Viewer / CDC boot logs differ')
        report['rttBootLogCrossCheck']='exact bytes match across the two real transports'
        self.save(self.out/'results.json',report)
        report['serialFinal']=self.serial('final');self.save(self.out/'results.json',report)
        return report


def run(args):
    if not 1<=args.rounds<=1000:raise ValueError('rounds must be 1..1000')
    campaign=NoFlash(args)
    try:result=campaign.flow()
    except Exception as error:
        cleanup=[]
        for page,method,target in [('scope','stop','view'),('scope','disconnect','view'),('rtt','disconnect','view'),('rttcdc','stop','hid'),('rttcdc','disconnect','hid'),('rttcdc','close','session'),('serial','close','session')]:
            try:campaign.invoke(page,method,target=target)
            except Exception as failed:cleanup.append(str(failed))
        campaign.save(campaign.out/'failure.json',{'error':str(error),'steps':len(campaign.steps),'cleanupErrors':cleanup})
        raise
    campaign.save(campaign.out/'summary.json',result)
    return result
