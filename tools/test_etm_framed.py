"""Offline native FRM1 equivalence, including repacked real ETMv3/v4 bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'etm-service/tools'))
from native_framed import run
from tpiu_demux import demux


def pack(raw, source=2):
    """Test stimulus only: formatter with ID at every frame, zero-source padding."""
    result = bytearray()
    for offset in range(0, len(raw), 14):
        payload = list(raw[offset:offset+14])
        frame = bytearray(16)
        frame[0] = source*2+1
        frame[1] = payload.pop(0)
        flags = 0
        for pos in range(2, 14, 2):
            if len(payload) >= 2:
                value = payload.pop(0)
                frame[pos] = value & 254
                flags |= (value & 1) << (pos//2)
                frame[pos+1] = payload.pop(0)
            elif payload:
                # Next byte still belongs to previous ID; following data is padding.
                frame[pos] = 1
                flags |= 1 << (pos//2)
                frame[pos+1] = payload.pop(0)
            else:
                frame[pos] = 1
        if payload:
            value = payload.pop(0)
            frame[14] = value & 254
            flags |= (value & 1) << 7
        else:
            frame[14] = 1
        frame[15] = flags
        result.extend(frame)
    return bytes(result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    rows = []
    def check(name, framed, expected, tail=b''):
        source = out/(name+'.frm1'); source.write_bytes(framed+tail)
        report = run(source, out/name, tail_bytes=len(tail))
        actual = {int(key): (out/name/f'id{key}.bin').read_bytes() for key in report['streams']}
        if actual != expected: raise AssertionError(name+' source data mismatch')
        rows.append(dict(name=name, inputBytes=len(framed)+len(tail),
                         streams={str(k): len(v) for k,v in actual.items()},
                         seconds=report['seconds'], inputSha256=report['inputSha256']))
    # Every final payload size tests zero-source padding and previous-ID flag semantics.
    for count in range(1, 29):
        payload = bytes(range(count))
        check(f'length-{count}', pack(payload), {2: payload})
    rng = random.Random(0xF103743)
    frames = bytearray()
    for index in range(512):
        frame = bytearray(rng.randrange(255) for _ in range(16))
        for pos in range(0, 15, 2):
            if rng.randrange(4) == 0: frame[pos] = rng.randrange(0, 8)*2+1
            else: frame[pos] &= 254
        frames.extend(frame)
    _, reference = demux(bytes.fromhex('ff ff ff 7f')+frames)
    check('multi-source', frames, {k:v for k,v in reference.items() if k != 0})
    for count in range(1,16):
        payload = bytes(range(40))
        check(f'tail-{count}', pack(payload), {2:payload}, bytes(range(count)))
    # Repacking proves byte identity through this new stage, not physical DDR acquisition.
    h743 = ROOT/'tools/tests/fixtures/h743-etmv4/h743.etmrecord'
    with zipfile.ZipFile(h743) as archive: raw = archive.read('capture.bin')
    check('h743-etmv4-repacked', pack(raw), {2:raw})
    f103 = ROOT/'tools/tests/fixtures/etm-offline/capture.bin'
    if not f103.is_file(): raise FileNotFoundError('prepare retained F103 1s fixture first')
    raw = f103.read_bytes()
    check('f103-etmv3-repacked', pack(raw), {2:raw})
    exe = ROOT/'etm-service/build-native/etm_framed.exe'
    invalid = out/'invalid.frm1'; invalid.write_bytes(bytes([255])+bytes(15))
    bad = subprocess.run([str(exe),str(invalid),str(out/'invalid-output'),'--tail-bytes','0'],capture_output=True)
    if bad.returncode == 0 or (out/'invalid-output/result.json').exists():
        raise AssertionError('reserved source ID accepted')
    bad = subprocess.run([str(exe),str(invalid),str(out/'bad-tail'),'--tail-bytes','1'],capture_output=True)
    if bad.returncode == 0: raise AssertionError('mismatched tail accepted')
    report = dict(hardwareAccess=False, passed=True, source='repacked real ETM streams and generated formatter frames',
                  cases=len(rows)+2, rows=rows, binarySha256=hashlib.sha256(exe.read_bytes()).hexdigest())
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=report['cases'],realFixtures=rows[-2:]),indent=2))


if __name__ == '__main__': main()
