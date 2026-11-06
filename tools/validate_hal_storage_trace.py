"""Serial CLI/Web performance campaign for the HAL storage demo.

Each round arms one explicit write+restore transaction, captures it, and rereads
both actual peripherals against the original private host backup. No retries.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from validate_f103_main_web import Web
from toolbox import pack_file

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['cli','web','web-button'],required=True)
    p.add_argument('--elf',type=Path,required=True);p.add_argument('--backup',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--runtime')
    p.add_argument('--pair',type=Path,default=ROOT/'prebuilt/release-20261106')
    p.add_argument('--seconds',type=float,default=1);p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--sources-from-record',type=Path,help='Attach exact source file contents named by a previous record')
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print(json.dumps(dict(hardwareAccess=False,stage=a.stage)));return
    if a.stage.startswith('web') and not a.runtime:p.error('Web stage requires --runtime')
    a.out.mkdir(parents=True,exist_ok=False);report=dict(stage=a.stage,rows=[],passed=False)
    def save():(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    def run(label,arguments):
        with (a.out/(label+'.log')).open('w',encoding='utf8') as log:
            result=subprocess.run([sys.executable,'-X','utf8',*map(str,arguments)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        assert result.returncode==0,label+' failed; inspect its log; no retry'
    w=None
    try:
        if a.stage=='web-button':
            from tools.stress_etm_web import Stress,arguments
            params=['--runtime',a.runtime,'--artifacts',str(a.out/'web'), '--rounds','1','--capture-rounds','1','--milliseconds',str(round(a.seconds*1000)),'--elf',str(a.elf),'--functions','storage_exercise','--control-clocks-khz','10000','--case-timeout','240']
            if a.sources_from_record:
                snapshot=a.out/'source-snapshot';snapshot.mkdir()
                paths=set(json.loads((a.sources_from_record/'sources.json').read_text(encoding='utf8')))
                sys.path.insert(0,str(ROOT/'etm-service/tools'))
                from native_core import Image
                image=Image(a.elf)
                try:paths.update(image.elf_info()['sourceFiles'])
                finally:image.close()
                for path in sorted(paths):
                    source=Path(path)
                    if not source.is_file() or not source.resolve().is_relative_to(ROOT):
                        report.setdefault('unavailableSources',[]).append(path);continue
                    dest=snapshot/source.resolve().relative_to(ROOT)
                    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes())
                params+=['--sources',str(snapshot)]
            w=Stress(arguments(params));w.initialize();report['lifecycle']=w.lifecycle()
        elif a.stage=='web':
            w=Web(SimpleNamespace(runtime=a.runtime,artifacts=a.out/'web',case_timeout=240))
            w.page('etm','show');w.page('etm','describe')
            w.page('etm','upload',selector='#elf-file',files=[pack_file(a.elf)])
            w.wait('etm','#elf-label',a.elf.name);w.ready('etm','#hse')
            w.set('etm','#hse','8');w.set('etm','#target-profile','stm32f103ze')
            if a.sources_from_record:
                paths=json.loads((a.sources_from_record/'sources.json').read_text(encoding='utf8'))
                files=[pack_file(Path(path),Path(path).resolve().relative_to(ROOT).as_posix()) for path in paths]
                w.page('etm','upload',selector='#sources-files',files=files)
                w.wait('etm','#sources-label','已保存本地快照');w.ready('etm','#hse')
            w.page('etm','describe',target='history')
        for repeat in range(a.rounds):
            common=['tools/hal_storage_fixture.py','--elf',a.elf,'--backup',a.backup,'--execute']
            run(f'arm-{repeat}',[*common,'--stage','arm','--out',a.out/f'arm-{repeat}'])
            armed=json.loads((a.out/f'arm-{repeat}/result.json').read_text())
            start=time.perf_counter()
            if a.stage=='cli':
                record=a.out/f'record-{repeat}'
                run(f'capture-{repeat}',['toolbox.py','trace','capture','--elf',a.elf,'--out',record,'--seconds',a.seconds,'--swd-khz','10000','--entry','storage_exercise','--bit',a.pair/'probe.bit','--zynq-elf',a.pair/'application.elf','--json-out',a.out/f'capture-{repeat}.json'])
                result=json.loads((a.out/f'capture-{repeat}.json').read_text());assert result['ok'],result
                capture=result['result'];quality=capture['quality'];reported=result['elapsedSeconds']
            elif a.stage=='web':
                capture=w.invoke('etm','captureNative',dict(seconds=a.seconds,entry='storage_exercise',resetToEntry=False,gpioSpeed=1,swdKhz=10000,traceId=2,decode=True))
                w.invoke('etm','waitForDisplay',target='history')
                metadata=json.loads((Path(a.runtime)/'toolbox-runtime.json').read_text())
                record=Path(metadata['recordsDirectory'])/capture['record']
                quality=json.loads((record/'session.json').read_text())['quality'];reported=None
            else:
                capture=w.captures()[0]
                w.save(w.out/f'button-capture-{repeat}.json',capture)
                metadata=json.loads((Path(a.runtime)/'toolbox-runtime.json').read_text())
                record=Path(metadata['recordsDirectory'])/capture['record']
                quality=capture['transport'];reported=None
            wall=time.perf_counter()-start
            decoded=json.loads((record/'decoded.json').read_text())
            dq=decoded['quality'];summary=decoded['summary']
            assert quality['synced'] and quality['ended'] and not quality['loss'] and quality['requestedWindowComplete'],quality
            assert dq['packetIssues']==dq['unprocessedBytes']==dq['unaccountedBytes']==0,dq
            assert decoded['status']['lastErrorCode']==0
            required=['HAL_SPI_Transmit','HAL_SPI_TransmitReceive','HAL_I2C_Mem_Read','HAL_I2C_Mem_Write','nor_program','nor_erase_sector','eeprom_write','storage_exercise','storage_restore']
            assert all(summary['functions'].get(name,0)>0 for name in required),summary['functions']
            run(f'verify-{repeat}',[*common,'--stage','verify','--out',a.out/f'verify-{repeat}'])
            restored=json.loads((a.out/f'verify-{repeat}/result.json').read_text())
            assert restored['before']['write_rounds']==armed['before']['write_rounds']+1
            row=dict(repeat=repeat,record=str(record.resolve()),wallSeconds=wall,cliReportedSeconds=reported,capture=capture,quality=quality,decodedQuality=dq,summary=summary,peripheralVerification=restored)
            performance=record/'decode-performance.json'
            if performance.exists():row['decodePerformance']=json.loads(performance.read_text())
            report['rows'].append(row);save()
            print(a.stage,repeat,round(wall,3),'s',summary['instructions'],'paths, full peripheral restore verified',flush=True)
        report['passed']=True
    except BaseException as exc:report['error']=repr(exc);raise
    finally:save()

if __name__=='__main__':main()
