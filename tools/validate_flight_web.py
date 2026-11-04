"""Real workbench flight start/trigger/cancel/timeout and ownership handoff."""
import argparse,json,sys,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from tools.validate_f103_main_web import Web
from toolbox import pack_file


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',required=True);p.add_argument('--records',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--skip-timeout',action='store_true')
    a=p.parse_args()
    if not a.execute:print('Real Web flight plan; no hardware access');return
    w=Web(SimpleNamespace(runtime=a.runtime,artifacts=a.out,case_timeout=90,elf=ROOT/'prebuilt/golden/f103ze-cdc48.elf'))
    report={'rows':[]};connected=False
    def idle():
        status=w.client.native('session','status',{})['value']
        assert 'capture' not in status['resources'],status
        return status
    try:
        w.page('etm','show');w.page('etm','describe',target='target')
        w.page('etm','upload',selector='#elf-file',files=[pack_file(w.args.elf)])
        w.wait('etm','#elf-label','f103ze-cdc48.elf')
        w.page('etm','click',selector='#connect');w.ready('etm','#disconnect');connected=True
        report['before']=w.invoke('etm','inspect',target='target')
        w.set('etm','#entry-before',True);w.set('etm','#reset-before',False);w.set('etm','#entry-before',False)
        w.set('etm','#flight-capacity',1);w.set('etm','#flight-post',20);w.set('etm','#flight-timeout',10)
        for mode in (['manual','cancel'] if a.skip_timeout else ['manual','cancel','timeout']):
            if mode=='timeout':w.set('etm','#flight-timeout',1)
            before=set(a.records.glob('capture-*'))
            w.page('etm','click',selector='#flight-start');w.ready('etm','#flight-trigger')
            status=w.client.native('session','status',{})['value']
            assert status['resources']['capture']['restoreOwner']
            try:w.client.native('usb','open',{'owner':'f'*32})
            except RuntimeError:pass
            else:raise AssertionError('another client overtook capture')
            if mode=='manual':w.page('etm','click',selector='#flight-trigger')
            elif mode=='cancel':w.page('etm','click',selector='#stop')
            w.ready('etm','#flight-start')
            folders=set(a.records.glob('capture-*'))-before;assert len(folders)==1
            folder=folders.pop();m=json.loads((folder/'session.json').read_text(encoding='utf-8'))
            q=m.get('captureQuality')
            if mode=='manual':assert q['completionReason']=='trigger' and q['captureComplete'] and not q['loss'],q
            if mode=='timeout':assert q and not q['captureComplete'],q
            report['rows'].append(dict(mode=mode,record=folder.name,quality=q,
                jobState=w.page('etm','read',selector='#job-state')['text'],coordinator=idle()))
            w.save(w.out/'result.json',report)
        report['after']=w.invoke('etm','inspect',target='target')
        report['passed']=True
    finally:
        if connected:w.invoke('etm','disconnect',target='target')
        report['finalCoordinator']=idle()
        w.save(w.out/'result.json',report)
    print(json.dumps({'passed':report['passed'],'cases':[r['mode'] for r in report['rows']]},ensure_ascii=False))


if __name__=='__main__':main()
