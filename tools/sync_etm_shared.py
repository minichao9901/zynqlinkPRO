"""Check/sync ETM standalone shared drivers against canonical web/app sources."""
import argparse
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group()
    group.add_argument('--write',action='store_true',help='Copy canonical drivers to the ETM standalone mirror')
    group.add_argument('--check',action='store_true',help='Read-only verification (default)')
    a=p.parse_args()
    mirror=ROOT/'etm-service/web/app/shared';rows=[]
    for dest in sorted(mirror.rglob('*.js')):
        name=dest.relative_to(mirror);source=ROOT/'web/app'/name
        if not source.is_file():raise ValueError('Missing canonical shared driver: '+str(name))
        same=source.read_bytes()==dest.read_bytes()
        if not same and a.write:shutil.copyfile(source,dest)
        rows.append(dict(path=name.as_posix(),equal=same or a.write,updated=not same and a.write))
    if not rows:raise ValueError('ETM shared driver mirror is empty')
    print(json.dumps(dict(passed=all(r['equal'] for r in rows),write=a.write,drivers=rows),indent=2))
    return 0 if all(r['equal'] for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
