from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'tools'))
from dap_pipeline_bench import open_dap,setup
from test_probe_board import Memory
from probe_build_info import live_clock_snapshot
from validate_fclk_performance import physical_snapshot
import usb.util
out=Path(__file__).resolve().parent
d,o,i=open_dap()
try:
    setup(o,i,10000)
    m=Memory(o,i)
    target={n:hex(m.word(a)) for n,a in {'CPUID':0xe000ed00,'DHCSR':0xe000edf0,
        'ETMCR':0xe0041000,'ETMLSR':0xe0041fb4,'RCC_CR':0x40021000,'RCC_CFGR':0x40021004}.items()}
    assert target['CPUID']=='0x411fc231' and not int(target['DHCSR'],16)&(1<<17)
    assert target['RCC_CFGR']=='0x51040a'
finally:usb.util.dispose_resources(d)
report=dict(recordedAtUtc=datetime.now(timezone.utc).isoformat(),pair='prebuilt/fclk133-release-20261101',
    target=target,clock=live_clock_snapshot(),physical=physical_snapshot(),targetFlashWrites=False,QSPIWrites=False)
assert abs(report['clock']['actual_link_Hz']-10000000)<10 and report['physical']['allObservedEnginesIdle']
(out/'final-board.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
package=root/'dist/zynq-etm-bridge'
manifest=json.loads((package/'package-manifest.json').read_text(encoding='utf8'))
delivery=dict(path=str(package),exe=str(package/'zynq-etm-bridge.exe'),
    exeSha256=hashlib.sha256((package/'zynq-etm-bridge.exe').read_bytes()).hexdigest(),
    manifestSha256=hashlib.sha256((package/'package-manifest.json').read_bytes()).hexdigest(),
    sourceRevision=manifest['sourceRevision'],sourceDirty=manifest['sourceDirty'],
    etmControlClockDefaultHz=manifest['etmControlClockDefaultHz'],packageFiles=len(manifest['files']))
(out/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(finalClockHz=report['clock']['actual_link_Hz'],targetRunning=True,enginesIdle=True,delivery=delivery)))
