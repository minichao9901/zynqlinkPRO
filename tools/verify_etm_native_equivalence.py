"""Compare complete native-store event dictionaries against a retained read-only oracle.

Use --legacy for an existing JSONL/SQLite result, or --oracle for the compact
Git-tracked frozen sample. This never executes the legacy decode pipeline.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etm-service/tools'))
from trace_store_adapter import TraceStoreAdapter


def legacy_sample(folder):
    old=folder.resolve()
    con=sqlite3.connect((old/'browse-v3.sqlite').as_uri()+'?mode=ro',uri=True)
    try:
        count=con.execute('select max(seq)+1 from event_rows').fetchone()[0]
        selected={0,1,2,count-1,*[i*(count-1)//127 for i in range(128)]}
        markers=[r[0] for r in con.execute("select seq from events where kind='event'")]
        selected.update(q+d for q in markers for d in (-1,0,1) if 0<=q+d<count)
        for state in ('unknown','not-taken'):
            selected.update(r[0] for r in con.execute('select seq from events where state=? limit 64',(state,)))
        events=[]
        with (old/'events.jsonl').open('rb') as stream:
            for seq in sorted(selected):
                data,offset=con.execute('select data,src from events where seq=?',(seq,)).fetchone()
                if data:event=json.loads(data)
                else:stream.seek(offset);event=json.loads(stream.readline())
                events.append(event)
        return {'schema':'etm-event-oracle/1','eventCount':count,'allBoundaryEvents':len(markers),
                'inputSha256':hashlib.sha256((old/'capture.bin').read_bytes()).hexdigest(),'events':events}
    finally:con.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--legacy',type=Path)
    group.add_argument('--oracle',type=Path)
    p.add_argument('--write-oracle',type=Path,help='Freeze this exact sample as gzip JSON for portable offline regression')
    p.add_argument('--native',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.legacy:oracle=legacy_sample(a.legacy)
    else:oracle=json.loads(gzip.decompress(a.oracle.read_bytes()).decode('utf8'))
    if oracle.get('schema')!='etm-event-oracle/1':raise ValueError('unsupported event oracle')
    actual_sha=hashlib.sha256((a.native/'capture.bin').read_bytes()).hexdigest()
    if actual_sha!=oracle['inputSha256']:raise ValueError('native input differs from event oracle')
    if a.write_oracle:
        a.write_oracle.parent.mkdir(parents=True,exist_ok=True)
        a.write_oracle.write_bytes(gzip.compress(json.dumps(oracle,ensure_ascii=False,separators=(',',':')).encode('utf8'),mtime=0))
    adapter=TraceStoreAdapter(a.native);adapter.ensure()
    failures=[];kinds={};states={}
    for reference in oracle['events']:
        seq=reference['seq'];actual=adapter.event(seq)['event']
        kinds[actual['kind']]=kinds.get(actual['kind'],0)+1
        state=actual.get('executionState');states[state or 'event']=states.get(state or 'event',0)+1
        if reference!=actual:
            failures.append({'seq':seq,'fields':{k:{'legacy':reference.get(k),'native':actual.get(k)}
                for k in reference.keys()|actual.keys() if reference.get(k)!=actual.get(k)}})
    report={'passed':not failures,'readOnlyLegacy':bool(a.legacy),'frozenOracle':str(a.oracle) if a.oracle else None,
            'comparison':'entire reconstructed event dictionary including callPath, source, execution state and boundary payload',
            'eventCount':oracle['eventCount'],'sampleCount':len(oracle['events']),'allBoundaryEvents':oracle['allBoundaryEvents'],
            'sampleKinds':kinds,'sampleStates':states,'sampleSequences':[e['seq'] for e in oracle['events']],
            'failures':failures,'inputSha256':actual_sha}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('sampleSequences','failures')},ensure_ascii=False))
    if failures:raise SystemExit(f'{len(failures)} event mismatches; see {a.out}')


if __name__=='__main__':main()
