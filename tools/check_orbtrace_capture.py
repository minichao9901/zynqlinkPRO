"""Check simulated TPIU frames against unmodified ORBTrace and OpenCSD.

python tools/check_orbtrace_capture.py build/cm3_sim/etm_full \
    --decoder E:/superlinkPRO/etm/build-native/etm_decode.exe

Amaranth 0.5.8 is needed for the independent upstream reference simulation.
The optional OpenCSD executable uses superlinkPRO's two-argument CLI.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def upstream_demux(frames):
    from amaranth import Module
    from amaranth.lib import wiring
    from amaranth.sim import Simulator
    from third_party.orbtrace.trace import tpiu
    from third_party.orbtrace.stream import Serializer

    # These are the unmodified upstream blocks, not a second copy of our RTL.
    m = Module()
    m.submodules.unmangle = unmangle = tpiu.Unmangle()
    m.submodules.serializer = serializer = Serializer(tpiu.TPIUUnmangledFrame)
    m.submodules.track = track = tpiu.TrackStream()
    m.submodules.strip = strip = tpiu.StripChannelZero()
    wiring.connect(m, unmangle.output, serializer.input)
    wiring.connect(m, serializer.output, track.input)
    wiring.connect(m, track.output, strip.input)
    sim = Simulator(m)
    sim.add_clock(1e-6)
    result = []

    async def producer(ctx):
        for frame in frames:
            ctx.set(unmangle.input.payload, list(frame))
            ctx.set(unmangle.input.valid, 1)
            await ctx.tick().until(unmangle.input.ready)
        ctx.set(unmangle.input.valid, 0)

    async def consumer(ctx):
        ctx.set(strip.output.ready, 1)
        for _ in range(len(frames) * 20 + 100):
            _, _, valid, payload = await ctx.tick().sample(strip.output.valid, strip.output.payload)
            if valid:
                result.append((payload.channel, payload.data))

    sim.add_testbench(producer)
    sim.add_testbench(consumer)
    sim.run()
    return result


def check(work, decoder=None):
    (work / 'capture-check.json').unlink(missing_ok=True)
    frames = [bytes.fromhex(line) for line in (work / 'cm3_tpiu.hex').read_text().splitlines()]
    actual = bytes.fromhex((work / 'cm3_etm.hex').read_text())
    if len(frames) < 10 or len(actual) < 100:
        raise ValueError('capture is too short')
    golden = upstream_demux(frames)
    if any(channel != 2 for channel, _ in golden):
        raise ValueError('upstream found an unexpected source ID')
    expected = bytes(value for _, value in golden)
    if actual != expected:
        index = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        raise ValueError(f'upstream mismatch at byte {index}: RTL={len(actual)}, reference={len(expected)}')
    report = {'frames': len(frames), 'bytes': len(actual), 'traceid': 2,
              'etm_sha256': hashlib.sha256(actual).hexdigest(), 'upstream_byte_match': True}
    (work / 'cm3_etm.bin').write_bytes(actual)
    if decoder:
        config = json.loads((work / 'cm3_etm_config.json').read_text())
        # Same five-instruction Thumb loop preloaded by tb_cm3_swd.
        image = work / 'cm3_code.bin'
        image.write_bytes(bytes.fromhex('00 20 01 30 07 28 fc d1 fa e7 00 bf'))
        manifest = work / 'opencsd-config.txt'
        manifest.write_text('ETMv3\n' + ''.join(f'{config[key]:#x}\n' for key in ('idr', 'ctrl', 'ccer', 'traceid'))
                            + f'0x100 {image.resolve()}\n')
        p = subprocess.run([str(decoder.resolve()), str((work / 'cm3_etm.bin').resolve()), str(manifest.resolve())],
                           capture_output=True, text=True, timeout=120)
        (work / 'opencsd.jsonl').write_text(p.stdout)
        (work / 'opencsd.log').write_text(p.stderr)
        if p.returncode:
            raise ValueError(f'OpenCSD failed: {p.stderr[-2000:]}')
        records = [json.loads(line) for line in p.stdout.splitlines() if line.startswith('{')]
        # OCSD_GEN_TRC_ELEM_INSTR_RANGE = 5 (OpenCSD 1.8.3).
        ranges = [r for r in records if r.get('kind') == 'element' and r.get('type') == 5]
        report['opencsd_status'] = [r for r in records if r.get('kind') == 'status']
        if len(ranges) < 100:
            raise ValueError(f'OpenCSD recovered only {len(ranges)} instruction ranges')
        if any(not 0x100 <= r['start'] < r['end'] <= 0x10a for r in ranges):
            raise ValueError('decoded instruction range outside the actual Thumb workload')
        for before, after in zip(ranges, ranges[1:]):
            pc = before['start']
            next_pc = (0x102 if before['lastExecuted'] else 0x108) if pc == 0x106 else (0x100 if pc == 0x108 else pc + 2)
            if before['end'] != pc + 2 or after['start'] != next_pc:
                raise ValueError(f'decoded instruction flow disagrees with workload at {pc:#x}')
        if {r['start'] for r in ranges} != {0x100, 0x102, 0x104, 0x106, 0x108}:
            raise ValueError('decoded trace did not cover the complete loop')
        if len(report['opencsd_status']) != 1 or report['opencsd_status'][0]['lastErrorCode'] != 0:
            raise ValueError('OpenCSD reported an error')
        report['instruction_ranges'] = len(ranges)
        report['instruction_flow_match'] = True
        report['decoder_sha256'] = hashlib.sha256(decoder.read_bytes()).hexdigest()
    (work / 'capture-check.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    parser.add_argument('--decoder', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.work.resolve(), args.decoder), indent=2))
