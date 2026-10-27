"""Content identity used to reject stale synthesis and implementation-only builds."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
print(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((root/'fpga/rtl').glob('*.v'))},sort_keys=True,separators=(',',':')))
