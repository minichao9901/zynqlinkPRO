"""Offline comparison of the *same* RAW_DIAGNOSTIC=3 five-line samples.

Filters run on physical samples, never on ETM bytes. Phase and filtering are
separate factors. A bounded logic-analyser burst is not a long-run ETM test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'etm-service/tools'))
from tpiu_demux import demux
from native_binary import classify_packet_text, PACKET_INVALID, PACKET_UNSYNC


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def native_summary(data, elf, config, output):
    """Full OpenCSD packet/range decode without expensive source expansion."""
    output.mkdir(parents=True, exist_ok=False)
    (output / 'etm.bin').write_bytes(data)
    manifest = 'ETMv3\n' + ''.join(hex(config[k]) + '\n' for k in ('idr', 'ctrl', 'ccer', 'traceid'))
    with Path(elf).open('rb') as handle:
        image = ELFFile(handle)
        for i, segment in enumerate(image.iter_segments()):
            if segment['p_type'] == 'PT_LOAD' and segment['p_filesz']:
                target = output / f'image-{i}.bin'
                target.write_bytes(segment.data())
                manifest += f"{hex(segment['p_vaddr'])} {target.resolve()}\n"
    cfg = output / 'native-config.txt'
    cfg.write_text(manifest, encoding='utf-8')
    with (output / 'native.jsonl').open('wb') as dest:
        run = subprocess.run([str(ROOT / 'etm-service/build-native/etm_decode.exe'),
                              str(output / 'etm.bin'), str(cfg)], stdout=dest,
                             stderr=subprocess.PIPE, timeout=60)
    (output / 'native.log').write_bytes(run.stderr)
    result = dict(returnCode=run.returncode, packets=0, packetIssues=0, boundaryIncomplete=0,
                  unsyncBytes=0, ranges=0, addressInaccessible=0, status=None)
    for line in (output / 'native.jsonl').read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row['kind'] == 'packet':
            result['packets'] += 1
            flags = classify_packet_text(row['text'])
            if flags & PACKET_INVALID:
                result['packetIssues'] += 1
                if 'INCOMPLETE_EOT' in row['text']:
                    result['boundaryIncomplete'] += 1
            if flags & PACKET_UNSYNC:
                result['unsyncBytes'] += row['size']
        elif row['kind'] == 'element':
            if row['type'] == 5:
                result['ranges'] += 1
            elif row['type'] == 7:
                result['addressInaccessible'] += 1
        elif row['kind'] == 'status':
            result['status'] = row
    status = result['status'] or {}
    result['interiorPass'] = bool(not run.returncode and status.get('processed') == len(data)
                                  and not status.get('lastErrorCode', 1)
                                  and result['packetIssues'] == result['boundaryIncomplete']
                                  and result['ranges'] > 0 and not result['addressInaccessible'])
    result['completePacketPass'] = result['interiorPass'] and not result['packetIssues']
    save(output / 'summary.json', result)
    return result


def unpack(data):
    if len(data) % 2:
        raise ValueError('truncated 16-bit sample record')
    words = np.frombuffer(data, dtype='<u2')
    if np.any(words & 0x8000):
        raise ValueError('sample record bit15 must be zero')
    return ((words[:, None] >> np.array([10, 5, 0])) & 31).astype(np.uint8).reshape(-1)


def filter_samples(samples, method):
    if method == 'none':
        return samples.copy()
    result = samples.copy()
    if method == 'majority3':
        a, b, c = samples[:-2], samples[1:-1], samples[2:]
        result[2:] = (a & b) | (a & c) | (b & c)
    elif method == 'stable2':
        # Per-line causal hold until two consecutive samples agree. This is
        # equivalent to a 3-input majority whose third input is prior output.
        for i in range(1, len(samples)):
            a, b, old = int(samples[i]), int(samples[i-1]), int(result[i-1])
            result[i] = (a & b) | ((a | b) & old)
    else:
        raise ValueError('unknown filter')
    return result


def physical(samples, rate):
    clock = (samples >> 4) & 1
    edges = np.flatnonzero(clock[1:] != clock[:-1]) + 1
    rises = np.flatnonzero((clock[1:] == 1) & (clock[:-1] == 0)) + 1
    lengths = np.diff(edges)
    periods = np.diff(rises)
    return dict(samples=len(samples), sampleRateHz=rate, edgeCount=len(edges),
                measuredTraceclkHz=(float(rate * (len(rises)-1) / (rises[-1]-rises[0])) if len(rises)>1 else None),
                oneTickHalfCells=int(np.sum(lengths == 1)),
                halfCellHistogram={str(int(n)): int(count) for n, count in zip(*np.unique(lengths, return_counts=True))},
                meanPeriodSamples=float(periods.mean()) if len(periods) else None), edges


def analyze(args):
    folder = Path(args.capture).resolve()
    acceptance = json.loads((folder / 'acceptance.json').read_text())
    if not acceptance.get('capture_passed') or not acceptance.get('restored'):
        raise ValueError('raw capture/restore failed; no success comparison permitted')
    data = (folder / 'raw-samples16.bin').read_bytes()
    samples = unpack(data)
    rate = acceptance['sample_rate_hz']
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=False)
    original, _ = physical(samples, rate)
    report = dict(input=str(folder), inputSha256=hashlib.sha256(data).hexdigest(),
                  sampleDurationSeconds=len(samples)/rate, physical=original, rows=[],
                  basis='same physical samples; causal five-line filters; phase separately swept; no ETM byte repair')
    for method in ('none', 'majority3', 'stable2'):
        filtered = filter_samples(samples, method)
        phys, edges = physical(filtered, rate)
        for fraction in (0, .25, .5, .75):
            # Sample within each half-cell after its edge, never across the
            # following clock edge. Low nibble is transmitted first.
            at = edges[:-1] + np.floor(np.diff(edges) * fraction).astype(np.int64)
            nibbles = filtered[at] & 15
            for phase in (0, 1):
                name = f'{method}-offset{fraction:g}-nibble{phase}'
                row = dict(filter=method, phaseFraction=fraction, nibblePhase=phase, physical=phys)
                n = nibbles[phase:]
                n = n[:len(n)//2*2]
                raw = bytes((n[::2] | (n[1::2] << 4)).tolist())
                (output / (name + '.tpiu')).write_bytes(raw)
                try:
                    framing, streams = demux(raw)
                    row['framing'] = framing
                    stream = streams.get(acceptance['config']['traceid'], b'')
                    row['unexpectedSources'] = sorted(set(streams) - {0, acceptance['config']['traceid']})
                    if not stream or row['unexpectedSources']:
                        raise ValueError('missing ETM stream or unexpected source ID')
                    row['decoder'] = native_summary(stream, args.elf, acceptance['config'], output / name)
                    row['etmBytes'] = len(stream)
                    row['interiorPass'] = row['decoder']['interiorPass']
                except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                    row.update(error=str(error), interiorPass=False)
                report['rows'].append(row)
                save(output / 'comparison.json', report)
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}, ensure_ascii=False))
    for row in report['rows']:
        print(row['filter'], row['phaseFraction'], row['nibblePhase'], row['interiorPass'],
              row.get('etmBytes',0), row.get('error', row.get('decoder')))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--out', required=True)
    analyze(parser.parse_args())


if __name__ == '__main__':
    main()
