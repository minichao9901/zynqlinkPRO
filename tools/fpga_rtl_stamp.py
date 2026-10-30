"""Content identity used to reject stale synthesis and implementation-only builds."""
import hashlib
import json
import argparse
from pathlib import Path

root=Path(__file__).resolve().parents[1]
current={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'fpga/rtl').glob('*.v'))}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--changed-groups',type=Path)
args=parser.parse_args()
if args.changed_groups:
    try:old=json.loads(args.changed_groups.read_text())
    except (FileNotFoundError,ValueError):old={}
    changed={name for name in current.keys()|old.keys() if current.get(name)!=old.get(name)}
    groups={('trace' if name.startswith('orbtrace_') else 'swd') for name in changed}
    print(' '.join(sorted(groups)))
else:
    print(json.dumps(current,sort_keys=True,separators=(',',':')))
