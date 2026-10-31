"""Compare native numeric-store events with a retained JSONL/SQLite baseline read-only.

This only reads an existing legacy result; it never runs the old decode pipeline.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etm-service/tools'))
from trace_store_adapter import TraceStoreAdapter


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--legacy',type=Path,required=True)
    p.add_argument('--native',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    old=a.legacy.resolve();new=a.native.resolve()
    con=sqlite3.connect((old/'browse-v3.sqlite').as_uri()+'?mode=ro',uri=True)
    count=con.execute('select max(seq)+1 from event_rows').fetchone()[0]
    selected={0,1,2,count-1,*[i*(count-1)//127 for i in range(128)]}
    # All boundary/exception events plus nearby instructions, including the final boundary.
    markers=[r[0] for r in con.execute("select seq from events where kind='event'")]
    selected.update(q+d for q in markers for d in (-1,0,1) if 0<=q+d<count)
    for state in ('unknown','not-taken'):
        selected.update(r[0] for r in con.execute('select seq from events where state=? limit 64',(state,)))
    adapter=TraceStoreAdapter(new);adapter.ensure()
    failures=[];kinds={};states={}
    with (old/'events.jsonl').open('rb') as stream:
        for seq in sorted(selected):
            data,offset=con.execute('select data,src from events where seq=?',(seq,)).fetchone()
            if data:reference=json.loads(data)
            else:stream.seek(offset);reference=json.loads(stream.readline())
            actual=adapter.event(seq)['event']
            kinds[actual['kind']]=kinds.get(actual['kind'],0)+1
            state=actual.get('executionState');states[state or 'event']=states.get(state or 'event',0)+1
            if reference!=actual:
                failures.append({'seq':seq,'fields':{k:{'legacy':reference.get(k),'native':actual.get(k)}
                    for k in reference.keys()|actual.keys() if reference.get(k)!=actual.get(k)}})
    report={'passed':not failures,'readOnlyLegacy':True,'comparison':'entire reconstructed event dictionary including callPath, source, execution state and boundary payload',
            'eventCount':count,'sampleCount':len(selected),'allBoundaryEvents':len(markers),'sampleKinds':kinds,'sampleStates':states,
            'sampleSequences':sorted(selected),'failures':failures,
            'inputSha256':hashlib.sha256((old/'capture.bin').read_bytes()).hexdigest()}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('sampleSequences','failures')},ensure_ascii=False))
    if failures:raise SystemExit(f'{len(failures)} event mismatches; see {a.out}')


if __name__=='__main__':main()
