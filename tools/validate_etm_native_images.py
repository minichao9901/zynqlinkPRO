"""Compare complete ELF/DWARF tables and the Web ELF DTO without board I/O."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'etm-service'), str(ROOT / 'etm-service/tools')]
from trace_cli import engine_environment
import decode_trace
import native_core
import server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    engine_environment()
    rows = []
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    for path in args.elf:
        with patch.dict(os.environ, {'ETM_NATIVE_STATIC': '0'}):
            reference = decode_trace.Image(path)
            expected = server.elf_info(path)
        with patch.dict(os.environ, {'ETM_NATIVE_STATIC': '1'}):
            actual = server.elf_info(path)
        image = native_core.Image(path)
        try:
            assert image.functions == reference.functions
            assert image.lines == reference.lines
            assert image.segments == reference.segments
            assert actual == expected
            rows.append(dict(elf=str(path.resolve()), sha256=image.sha256,
                functions=len(image.functions), lineIntervals=len(image.lines),
                functionsSha256=digest(image.functions), linesSha256=digest(image.lines),
                webElfInfoSha256=digest(actual), completeWebDtoEqual=True,
                segmentsEqual=True, allFunctionAndLineRowsEqual=True))
        finally:
            image.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dict(ok=True, offline=True, rows=rows), ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print('Native ELF/DWARF/segments/Web DTO: PASS', flush=True)


if __name__ == '__main__':
    main()
