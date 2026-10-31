"""Measure the actual Web history reader through its authenticated CLI queue; no hardware I/O.

Open the URL printed by bench_etm_native_offline.py in a browser first.
Run this once per fresh decode campaign: opening records and querying windows warms caches.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.f103_stream_acceptance import Streams


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--skip-open',action='store_true',help='Only measure zoom; preserve earlier first-open results')
    a=p.parse_args()
    ready=json.loads((a.campaign/'ready.json').read_text(encoding='utf8'))
    s=Streams(SimpleNamespace(runtime=ready['runtime'],case_timeout=90,artifacts=str(a.out)))
    report={'hardwareAccess':False,'boundary':'browser method start -> requested view and default timeline ready -> two animation frames',
            'cachePolicy':'First open per fresh record after native decode/cache preparation, shared server/ELF and OS caches; zoom windows are labelled by order.',
            'firstScreen':[],'zoom':[]}
    def capture(key,value):
        assert value['painted'] and value['visibility']=='visible',value
        report[key].append(value);s.save(s.out/'results.json',report)
        print(json.dumps(value,ensure_ascii=False),flush=True)
    for sid in ready['records']:
        if not a.skip_open:capture('firstScreen',s.invoke('etm','measureOpenRecord',sid))
        else:s.invoke('etm','openRecord',sid)
        for direction in [True,True,True,False,False,False]:
            capture('zoom',s.invoke('etm','measureZoom',direction,target='history'))
    # Full execution-order flame view, not only aggregate/count-only analysis.
    s.page('etm','click',selector='[data-view="flame"]')
    s.invoke('etm','render',target='history')
    for direction in [True,True,True,False,False,False]:
        capture('zoom',s.invoke('etm','measureZoom',direction,target='history'))
    s.save(s.out/'results.json',report)


if __name__=='__main__':main()
