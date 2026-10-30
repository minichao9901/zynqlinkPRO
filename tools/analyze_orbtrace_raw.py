"""Analyze sampled physical DDR bytes using the reference TPIU demux/OpenCSD.

The raw input stores the rising-edge nibble in bits 3:0 and the falling-edge
nibble in bits 7:4. Both possible nibble alignments are assessed independently.
Incomplete/corrupt prefixes and transport loss are reported, not repaired.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

from elftools.elf.elffile import ELFFile


def load_demux(path):
    spec = importlib.util.spec_from_file_location('reference_tpiu_demux', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.demux


def sha(data):
    return hashlib.sha256(data).hexdigest()


def first_frames(stream):
    """Return complete frames only up to the first structural sync error."""
    pos = stream.find(bytes.fromhex('ffffff7f'))
    frames, frame = [], bytearray()
    if pos < 0:
        return frames
    while pos+2 <= len(stream):
        if not frame and stream[pos:pos+4] == bytes.fromhex('ffffff7f'):
            pos += 4
        elif stream[pos:pos+2] == bytes.fromhex('ff7f'):
            pos += 2
        elif stream[pos:pos+2] == bytes.fromhex('ffff'):
            break
        else:
            frame.extend(stream[pos:pos+2]);pos += 2
            if len(frame) == 16:
                frames.append(bytes(frame));frame.clear()
    return frames


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('capture', type=Path, help='directory containing raw-ddr.bin and acceptance.json')
    ap.add_argument('--reference', type=Path, default=Path('E:/superlinkPRO/etm/tools/tpiu_demux.py'))
    ap.add_argument('--decoder', type=Path, default=Path('E:/superlinkPRO/etm/build-native/etm_decode.exe'))
    ap.add_argument('--target-elf', type=Path, required=True)
    ap.add_argument('--golden-tpiu', type=Path, help='Optional real reference TPIU recording for frame comparison')
    args = ap.parse_args()
    work = args.capture.resolve()
    raw = (work/'raw-ddr.bin').read_bytes()
    acceptance = json.loads((work/'acceptance.json').read_text(encoding='utf-8'))
    reference = load_demux(args.reference)
    # phase1 packs falling(i) then rising(i+1); do not infer that either is
    # valid from sync counts alone.
    phases = [raw, bytes((a >> 4) | ((b & 15) << 4) for a, b in zip(raw, raw[1:]))]
    report = {'raw_bytes': len(raw), 'raw_sha256': sha(raw), 'quality': acceptance.get('quality'),
              'reference': str(args.reference.resolve()), 'reference_sha256': sha(args.reference.read_bytes()),
              'decoder': str(args.decoder.resolve()), 'decoder_sha256': sha(args.decoder.read_bytes()),
              'phases': []}
    config = acceptance['config']
    golden = args.golden_tpiu.read_bytes() if args.golden_tpiu else None
    golden_frames = first_frames(golden) if golden is not None else []
    if golden is not None:
        report['golden_tpiu'] = {'path': str(args.golden_tpiu.resolve()), 'sha256': sha(golden),
                                 'frames': len(golden_frames),
                                 'note': 'Different capture windows; similarity is diagnostic, not an equality test.'}
    image_lines = []
    with args.target_elf.open('rb') as f:
        for i, segment in enumerate(ELFFile(f).iter_segments()):
            if segment['p_type'] == 'PT_LOAD' and segment['p_filesz']:
                p = work/f'raw-image{i}.bin'
                p.write_bytes(segment.data())
                image_lines.append(f"{int(segment['p_vaddr']):#x} {p.as_posix()}")
    for index, stream in enumerate(phases):
        phase = {'phase': index, 'bytes': len(stream), 'sha256': sha(stream),
                 'fsync_matches': stream.count(bytes.fromhex('ffffff7f'))}
        path = work/f'raw-phase{index}.bin'
        path.write_bytes(stream)
        try:
            stats, streams = reference(stream)
            phase['tpiu_strict_pass'] = True
        except ValueError as exc:
            phase.update(tpiu_strict_pass=False, tpiu_error=str(exc))
            match = re.search(r'偏移 (\d+)', str(exc))
            if not match:
                report['phases'].append(phase)
                continue
            # Preserve only the strict prefix before the first structural
            # error; the partial final formatter frame stays explicit.
            prefix = stream[:int(match.group(1))]
            try:
                stats, streams = reference(prefix)
            except ValueError:
                report['phases'].append(phase)
                continue
            phase['strict_prefix_bytes'] = len(prefix)
        phase['tpiu'] = stats
        observed_frames = first_frames(stream)
        if observed_frames and golden_frames:
            observed = observed_frames[0]
            def prefix(a,b):
                return next((j for j,(x,y) in enumerate(zip(a,b)) if x!=y),len(a))
            best = max(golden_frames,key=lambda candidate: prefix(observed,candidate))
            phase['first_frame_reference_comparison'] = {
                'observed': observed.hex(), 'reference': best.hex(),
                'matching_prefix_bytes': prefix(observed,best),
                'bit_differences': sum((x^y).bit_count() for x,y in zip(observed,best))}
        etm = streams.get(config['traceid'], b'')
        phase['etm_bytes'] = len(etm)
        phase['etm_sha256'] = sha(etm)
        if etm:
            etm_file = work/f'raw-phase{index}-etm.bin'
            etm_file.write_bytes(etm)
            manifest = work/f'raw-phase{index}-config.txt'
            manifest.write_text('ETMv3\n' + ''.join(f"{config[k]:#x}\n" for k in ('idr','ctrl','ccer','traceid'))
                                + '\n'.join(image_lines) + '\n')
            p = subprocess.run([str(args.decoder), str(etm_file), str(manifest)], capture_output=True,
                               text=True, errors='replace', timeout=120)
            (work/f'raw-phase{index}-decode.jsonl').write_text(p.stdout, encoding='utf-8')
            (work/f'raw-phase{index}-decode.txt').write_text(p.stderr, encoding='utf-8')
            records = [json.loads(line) for line in p.stdout.splitlines() if line.startswith('{')]
            phase['decoder_exit'] = p.returncode
            phase['decoder_error'] = p.stderr[-600:].strip()
            phase['instruction_ranges'] = sum(r.get('kind') == 'element' and r.get('type') == 5 for r in records)
            phase['decoder_status'] = [r for r in records if r.get('kind') == 'status']
        report['phases'].append(phase)
    (work/'raw-analysis.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
