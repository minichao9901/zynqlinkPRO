"""Seed an isolated Vivado cache without overwriting either project's entries."""
import argparse
from pathlib import Path
import shutil

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source', type=Path, required=True, help='Existing project .cache/ip directory')
ap.add_argument('--destination', type=Path, default=Path('build/shared_ip_cache'))
a = ap.parse_args()
src = a.source.resolve()
dst = a.destination.resolve()
if not src.is_dir() or src == dst or src in dst.parents or dst in src.parents:
    ap.error('Source must exist and destination must be a separate cache directory')
copied = skipped = 0
for version in src.iterdir():
    if not version.is_dir():
        continue
    for entry in version.iterdir():
        if not entry.is_dir():
            continue
        target = dst/version.name/entry.name
        if target.exists():
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(entry, target)
        copied += 1
print(f'IP cache {dst}: seeded={copied}, existing={skipped}')
