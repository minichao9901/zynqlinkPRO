"""TPIU sync/frame regressions, including real F103ZE pin replay.

No board access. Requires Icarus Verilog. Test data is a complete-frame slice
of the retained superlinkPRO hardware reference, not a simulated acceptance.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/tpiu-frame-regression'


def run(*command):
    p = subprocess.run([str(c) for c in command], cwd=ROOT, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stdout + p.stderr)
    return p.stdout.strip()


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    unit = ROOT / 'fpga/sim/tb_orbtrace_tpiu_stream.sv'
    rtl = ROOT / 'fpga/rtl/orbtrace_tpiu_stream.v'
    reports = []
    for phase in (0, 1):
        executable = WORK / f'phase{phase}.vvp'
        run('iverilog', '-g2012', '-s', 'tb_orbtrace_tpiu_stream',
            f'-Ptb_orbtrace_tpiu_stream.PHASE={phase}', '-o', executable, rtl, unit)
        output = run('vvp', executable)
        assert 'PASS' in output, output
        reports.append({'phase': phase, 'result': output})
    executable = WORK / 'physical.vvp'
    run('iverilog', '-g2012', '-s', 'tb_orbtrace_replay', '-Ptb_orbtrace_replay.BOARD=1',
        '-Ptb_orbtrace_replay.MODE=2', '-o', executable,
        *sorted((ROOT / 'fpga/rtl').glob('orbtrace_*.v')),
        ROOT / 'fpga/sim/sim_primitives.v', ROOT / 'fpga/sim/tb_orbtrace_replay.sv')
    source = ROOT / 'tools/tests/fixtures/f103ze-continuous.tpiu'
    expected = (ROOT / 'tools/tests/fixtures/f103ze-continuous.etm').read_bytes()
    sink = WORK / 'physical.txt'
    output = run('vvp', executable, '+source=' + source.as_posix(), '+sink=' + sink.as_posix())
    lines = [line.split() for line in sink.read_text().splitlines()]
    assert all(int(channel, 16) == 2 for channel, byte in lines), 'unexpected source IDs'
    actual = bytes(int(byte, 16) for channel, byte in lines)
    assert len(expected) == 874 and actual == expected, 'physical replay differs from reference demux'
    report = {'ok': True, 'unit': reports, 'physical': output, 'inputBytes': source.stat().st_size,
              'etmBytes': len(actual), 'etmSha256': hashlib.sha256(actual).hexdigest(),
              'rtlSha256': hashlib.sha256(rtl.read_bytes()).hexdigest(), 'hardwareValidated': False}
    (WORK / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
