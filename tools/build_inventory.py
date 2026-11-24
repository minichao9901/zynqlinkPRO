"""Inventory local build output sizes and timestamps without reading file contents."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]


def utc_timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds')


def measure(path):
    pending = [path]
    files = byte_count = skipped = 0
    latest = None
    while pending:
        entry = pending.pop()
        try:
            info = entry.lstat()
            attributes = getattr(info, 'st_file_attributes', 0)
            if stat.S_ISLNK(info.st_mode) or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                skipped += 1
                continue
            latest = info.st_mtime if latest is None else max(latest, info.st_mtime)
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(entry) as children:
                    pending.extend(Path(child.path) for child in children)
            elif stat.S_ISREG(info.st_mode):
                files += 1
                byte_count += info.st_size
        except OSError:
            skipped += 1
    return {
        'files': files,
        'bytes': byte_count,
        'latestWriteUtc': utc_timestamp(latest) if latest is not None else None,
        'skipped': skipped,
    }


def inventory(root=ROOT):
    build = root / 'build'
    if build.exists():
        info = build.lstat()
        attrs = getattr(info, 'st_file_attributes', 0)
        if not stat.S_ISDIR(info.st_mode) or attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f'Expected a regular build directory: {build}')
        entries = [
            {'path': child.relative_to(root).as_posix(), **measure(child)}
            for child in build.iterdir()
        ]
    else:
        entries = []
    entries.sort(key=lambda row: (-row['bytes'], row['path']))
    return {
        'worktree': str(root),
        'capturedAtUtc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'summary': {
            'entries': len(entries),
            **{key: sum(row[key] for row in entries) for key in ('files', 'bytes', 'skipped')},
        },
        'entries': entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='write to a new JSON file')
    args = parser.parse_args()
    try:
        data = json.dumps(inventory(), ensure_ascii=False, indent=2) + '\n'
        if args.out:
            with args.out.open('x', encoding='utf-8') as output:
                output.write(data)
        else:
            print(data, end='')
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    main()
