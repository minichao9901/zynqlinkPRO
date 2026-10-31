"""Bounded native FRM1 -> per-source ETM streams; no instruction JSON path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 'etm-framed-native/1'


def binary_path():
    # The bridge binds decode_trace.ROOT to its bundled backend assets.
    import decode_trace
    return decode_trace.ROOT/'build-native'/('etm_framed.exe' if os.name=='nt' else 'etm_framed')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(source, out, *, tail_bytes, trace_id=2, binary=None):
    source, out = Path(source).resolve(), Path(out).resolve()
    exe = Path(binary or binary_path())
    if not 0 <= tail_bytes <= 15 or not 1 <= trace_id <= 126:
        raise ValueError('invalid FRM1 tail length or trace ID')
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    version = subprocess.run([str(exe), '--version'], check=True, capture_output=True, text=True, timeout=10,**flags)
    if json.loads(version.stdout).get('protocol') != PROTOCOL:
        raise ValueError('FRM1 native protocol mismatch')
    before = digest(source)
    subprocess.run([str(exe), str(source), str(out), '--tail-bytes', str(tail_bytes)],
                   check=True, capture_output=True, timeout=120,**flags)
    report = json.loads((out/'result.json').read_text())
    if report.get('protocol') != PROTOCOL or report.get('inputBytes') != source.stat().st_size:
        raise ValueError('FRM1 native result mismatch')
    if digest(source) != before:
        raise ValueError('FRM1 input changed during native conversion')
    streams = report['streams']
    for key, count in streams.items():
        if not key.isdecimal() or not 1 <= int(key) <= 126:
            raise ValueError('invalid native source ID')
        if (out/f'id{key}.bin').stat().st_size != count:
            raise ValueError('native source size mismatch')
    if str(trace_id) not in streams:
        raise ValueError(f'FRM1 has no bytes for expected ETM source {trace_id}')
    report.update(inputSha256=before, binarySha256=digest(exe), traceId=trace_id,
                  selectedStream=str(out/f'id{trace_id}.bin'),
                  streamSha256={key: digest(out/f'id{key}.bin') for key in streams})
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--tail-bytes', type=int, required=True)
    p.add_argument('--trace-id', type=int, default=2)
    a = p.parse_args()
    print(json.dumps(run(a.source, a.out, tail_bytes=a.tail_bytes, trace_id=a.trace_id), indent=2))


if __name__ == '__main__':
    main()
