from pathlib import Path
import hashlib,json,statistics

base=Path(__file__).resolve().parent
runtime=json.loads((base/'runtime-measured/toolbox-runtime.json').read_text(encoding='utf8'))
records=Path(runtime['recordsDirectory'])
rows=[]
for series in ['ab-measured','ab-repeat']:
    f=base/series/'captures.json'
    if not f.exists():continue
    for r in json.loads(f.read_text(encoding='utf8')):
        folder=records/r['record']
        perf=json.loads((folder/'decode-performance.json').read_text(encoding='utf8'))
        rows.append(dict(series=series,round=r['round'],clockKhz=r['requestedControlClockKhz'],
            actualControlClock=r['actualControlClock'],reportedCaptureTckKhz=r['transport']['tckKhz'],
            e2eSeconds=r['seconds'],controlExchangeSeconds=r['controlTransport']['actions']['exchange']['milliseconds']/1000,
            exchangeCalls=r['controlTransport']['actions']['exchange']['calls'],decodeSeconds=perf['decodeSeconds'],
            openSeconds=r['openSeconds'],closeSeconds=r['closeSeconds'],ETMBytes=r['rawBytes'],sha256=r['rawSha256'],
            record=r['record'],nativePhases=perf.get('decodePhasesSeconds'),storePhases=perf.get('storePhasesSeconds'),
            hardwareSeconds=r['transport']['hardwareSeconds'],packetIssues=r['summary']['packetIssues'],
            loss=r['transport']['loss'],CDCInsideWindow=r['echoInsideHardwareWindow'],
            RCCRestored=r['rccAfter']==r['before']['rcc'],cleanupError=r.get('cleanupError')))
summaries={}
for series in ['ab-measured','ab-repeat','all']:
    selected=[r for r in rows if series=='all' or r['series']==series]
    out={}
    for clock in [1000,10000]:
        a=[r for r in selected if r['clockKhz']==clock]
        if not a:continue
        out[str(clock)]={}
        for key in ['e2eSeconds','controlExchangeSeconds','decodeSeconds']:
            vals=[r[key] for r in a]
            out[str(clock)][key]=dict(n=len(vals),values=vals,median=statistics.median(vals),range=[min(vals),max(vals)])
    if all(str(v) in out for v in [1000,10000]):
        a,b=[out[str(v)]['e2eSeconds']['median'] for v in [1000,10000]]
        ca,cb=[out[str(v)]['controlExchangeSeconds']['median'] for v in [1000,10000]]
        out.update(observedE2ESecondsSaved=a-b,observedE2EReductionPercent=100*(a-b)/a,
                   controlSecondsSaved=ca-cb,controlReductionPercent=100*(ca-cb)/ca)
        print(series,'1MHz',round(a,3),'10MHz',round(b,3),'observed savings',round(a-b,3),round(100*(a-b)/a,2),'%',
              'control',round(ca,3),round(cb,3))
    summaries[series]=out
result=dict(scope='Start-capture button to first display, target restore and ready; excludes initial connection and initial breakpoint creation',
    windowSeconds=1,firmwareHCLKHz=48000000,TRACECLKHz=24000000,rows=rows,summary=summaries,
    interpretation='E2E includes CPU/disk-heavy native decode/index; overlap and drift prevent attributing all observed difference to SWD. No outlier removed.',
    exploratoryMixedHandoffSeries='ab/ configured UI at 1/10MHz but capture service reset both to 1MHz; excluded from formal comparison',
    softwareFailure='ab-full-clock/ failed before acquisition because bundled setup lacked speed_hz; preserved and fixed before both formal series')
(base/'comparison.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print('Formal rows',len(rows),'all clean',all(r['packetIssues']==0 and not r['loss'] and r['RCCRestored'] and not r['cleanupError'] for r in rows))
