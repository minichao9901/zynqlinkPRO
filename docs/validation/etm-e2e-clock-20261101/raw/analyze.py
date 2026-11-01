from pathlib import Path
import json,statistics

base=Path(__file__).resolve().parent
rows=json.loads((base/'ab-measured/captures.json').read_text(encoding='utf8'))
runtime=json.loads((base/'runtime-measured/toolbox-runtime.json').read_text(encoding='utf8'))
records=Path(runtime['recordsDirectory'])
result=dict(scope='Start-capture click through native decode, index, first display, target restore and readiness; connection/initial breakpoint outside this timer',
            captureWindowSeconds=1,targetHCLKHz=48000000,targetTRACECLKHz=24000000,
            transport='ddr-usb/1',rows=[],summary={})
for r in rows:
    folder=records/r['record']
    performance=json.loads((folder/'decode-performance.json').read_text(encoding='utf8'))
    row=dict(round=r['round'],requestedControlClockKhz=r['requestedControlClockKhz'],
        actualControl=r['actualControlClock'],reportedCaptureTckKhz=r['transport']['tckKhz'],
        e2eSeconds=r['seconds'],openSeconds=r['openSeconds'],closeSeconds=r['closeSeconds'],
        ETMBytes=r['rawBytes'],ETMSha256=r['rawSha256'],record=r['record'],
        hardwareSeconds=r['transport']['hardwareSeconds'],usbSeconds=r['transport'].get('usbSeconds'),
        decodeSeconds=performance['decodeSeconds'],jobSeconds=performance['jobSeconds'],
        nativePhases=performance.get('decodePhasesSeconds'),storePhases=performance.get('storePhasesSeconds'),
        controlExchangeSeconds=r['controlTransport']['actions']['exchange']['milliseconds']/1000,
        controlExchangeCalls=r['controlTransport']['actions']['exchange']['calls'],
        packetIssues=r['summary']['packetIssues'],loss=r['transport']['loss'],
        cdcTransactionsInsideHardwareWindow=r['echoInsideHardwareWindow'],
        clockRegistersRestored=r['rccAfter']==r['before']['rcc'],cleanupError=r.get('cleanupError'))
    result['rows'].append(row)
for clock in [1000,10000]:
    selected=[r for r in result['rows'] if r['requestedControlClockKhz']==clock]
    if not selected:continue
    summary=dict(runs=len(selected))
    for field in ['e2eSeconds','controlExchangeSeconds','decodeSeconds','jobSeconds','ETMBytes']:
        values=[r[field] for r in selected]
        summary[field]=dict(median=statistics.median(values),range=[min(values),max(values)],values=values)
    result['summary'][str(clock)]=summary
if all(str(v) in result['summary'] for v in [1000,10000]):
    a,b=[result['summary'][str(v)]['e2eSeconds']['median'] for v in [1000,10000]]
    ca,cb=[result['summary'][str(v)]['controlExchangeSeconds']['median'] for v in [1000,10000]]
    result.update(e2eSecondsSaved=a-b,e2eReductionPercent=100*(a-b)/a,
                  controlSecondsSaved=ca-cb,controlReductionPercent=100*(ca-cb)/ca)
(base/'analysis.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
for r in result['rows']:
    print(r['round'],r['requestedControlClockKhz'],r['reportedCaptureTckKhz'],round(r['e2eSeconds'],3),
          'control',round(r['controlExchangeSeconds'],3),'decode',round(r['decodeSeconds'],3))
print({k:v for k,v in result.items() if k.endswith('Saved') or k.endswith('Percent')})
