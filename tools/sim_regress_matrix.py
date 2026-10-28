"""Speed and functional matrix for the SWD and JTAG backends.

Runs the same benches at several link rates against the ARM DesignStart core
model (SWD) and the JTAG-DP model (JTAG), so a merge can be compared with the
commit it replaced without any board in the loop.

The script only uses what the checked-out tree provides:

* ``tb_packet_wire_budget``  -> FCLK cycles per HSS/RTT packet (SWD wire cost)
* ``tb_cortexm0_link``       -> end-to-end HSS/RTT through the real core (needs ``+streams``)
* ``tb_jtag_word_cost``      -> FCLK/TCK cycles per chained AP read
* ``tb_jtag_pipeline``       -> end-to-end HSS/RTT through the JTAG DP model

Usage::

    python tools/sim_regress_matrix.py --label main --out build/sim_matrix/main.json
    python tools/sim_regress_matrix.py --label base --out ... --compare base.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = Path('E:/Share/github/ZYNQ7020_YuanZi/ZYNQ_DAPLINK_RTL_100TO50MHz/'
             'ZYNQ_DAPLINK_RTL_100TO50MHz.srcs/sim_1/imports/cortexm0')
MODEL_FILES = ['swd_cortexm0_target.v', 'CORTEXM0INTEGRATION.v', 'cortexm0ds_logic.v']

# SWCLK rates. half_ns is the FCLK half period, so SWCLK = 1/(4*half_ns).
SWD_SPEEDS = [('1MHz', 250.0), ('5MHz', 50.0), ('10MHz', 25.0),
              ('25MHz', 10.0), ('35MHz', 7.142857), ('50MHz', 5.0), ('60MHz', 4.166667)]
# Integer half periods the packet bench can take.
PACKET_HALVES = [250, 50, 25, 10, 7, 5]
# TCK = FCLK/2. clkns is the FCLK half period in ns.
JTAG_SPEEDS = [('1MHz', 1000.0), ('10MHz', 50.0), ('25MHz', 20.0),
               ('35MHz', 14.285714), ('50MHz', 10.0), ('60MHz', 8.333333)]


def sh(cmd, cwd, timeout=1800):
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True,
                       text=True, errors='replace', timeout=timeout)
    return p.returncode, p.stdout + p.stderr


class Bench:
    def __init__(self, root: Path, work: Path):
        self.root = root
        self.work = work
        self.work.mkdir(parents=True, exist_ok=True)
        self.rtl = sorted((root / 'fpga/rtl').glob('*.v'))
        self.log = []

    def build(self, top, sources, params=()):
        exe = self.work / f'{top}.vvp'
        cmd = ['iverilog', '-g2012', '-s', top, '-o', exe]
        for name, value in params:
            cmd += ['-P', f'{top}.{name}={value}']
        code, out = sh([*cmd, *sources], self.root)
        self.log.append({'step': f'build {top}', 'code': code, 'tail': out[-2000:]})
        if code:
            raise SystemExit(f'build failed for {top}:\n{out[-3000:]}')
        return exe

    def run(self, exe, plusargs=(), timeout=1800):
        cmd = ['vvp', exe, *[f'+{a}' for a in plusargs]]
        code, out = sh(cmd, self.root, timeout=timeout)
        return code, out


def packet_budget(bench: Bench, supports_rx: bool):
    tb = bench.root / 'fpga/sim/tb_packet_wire_budget.sv'
    rows = []
    for half in PACKET_HALVES:
        for rx in ([0, 1] if supports_rx else [0]):
            params = [('CLK_HALF_NS', half), ('IDLE_CYCLES', 1), ('TCO_NS', 16)]
            if supports_rx:
                params.insert(0, ('RX_BOUNDARY', rx))
            exe = bench.build('tb_packet_wire_budget',
                              [bench.root / 'fpga/rtl/swd_core.v',
                               bench.root / 'fpga/rtl/dap_transfer_block_engine.v', tb],
                              params)
            code, out = bench.run(exe)
            for m in re.finditer(r'BUDGET words=(\d+) read=(\d+) idle=(\d+) half_ns=(\d+) '
                                 r'cycles=(\d+) rises=(\d+) launches=(\d+)', out):
                words, read, idle, h, cycles = (int(m.group(i)) for i in range(1, 6))
                rows.append({'speed_MHz': round(1000.0 / (4 * h), 3), 'half_ns': h, 'rx': rx,
                             'words': words, 'read': read, 'idle': idle, 'cycles': cycles,
                             'pass': code == 0 and 'PASS real packet/core serial budget' in out})
            if code != 0:
                rows.append({'half_ns': half, 'rx': rx, 'pass': False,
                             'error': out[-800:]})
    return rows


def swd_core_matrix(bench: Bench):
    """Basic link at every rate, plus HSS/RTT when the bench supports it."""
    tb = bench.root / 'fpga/sim/tb_cortexm0_link.sv'
    supports_streams = 'streams' in tb.read_text(encoding='utf-8')
    sources = [*bench.rtl,
               bench.root / 'fpga/sim/sim_primitives.v',
               bench.root / 'fpga/sim/xpm_memory_tdpram.sv', tb,
               *[MODEL / f for f in MODEL_FILES]]
    exe = bench.build('tb_cortexm0_link', sources)
    rows = []
    for label, half in SWD_SPEEDS:
        for mode in (['link', 'streams'] if supports_streams else ['link']):
            plusargs = [f'half_ns={half}'] + (['streams'] if mode == 'streams' else [])
            code, out = bench.run(exe, plusargs)
            rows.append({
                'speed': label, 'half_ns': half, 'mode': mode,
                'pass': code == 0 and 'PASS CortexM0' in out,
                'hss': 'HSS_PASS' in out, 'rtt': 'RTT_PASS' in out,
                'tail': out.strip().splitlines()[-1] if out.strip() else '',
            })
    return rows


def jtag_words(bench: Bench):
    tb = bench.root / 'fpga/sim/tb_jtag_word_cost.sv'
    if not tb.exists():
        return []
    exe = bench.build('tb_jtag_word_cost',
                      [bench.root / 'fpga/rtl/jtag_core.v', bench.root / 'fpga/rtl/jtag_shift.v',
                       bench.root / 'fpga/sim/jtag_dp_model.sv', tb])
    rows = []
    for label, clkns in JTAG_SPEEDS:
        code, out = bench.run(exe, [f'clkns={clkns}'])
        words = {int(m.group(1)): {'fclk': int(m.group(2)), 'tck': int(m.group(3))}
                 for m in re.finditer(r'word(\d+) fclk=(\d+) tck=(\d+)', out)}
        steady = words.get(6, {}).get('fclk')
        rows.append({'speed': label, 'clkns': clkns, 'pass': code == 0 and steady is not None,
                     'word6_fclk': steady, 'word6_tck': words.get(6, {}).get('tck'),
                     'words': words,
                     'tail': out.strip().splitlines()[-1] if out.strip() else ''})
    return rows


def jtag_pipeline(bench: Bench):
    tb = bench.root / 'fpga/sim/tb_jtag_pipeline.sv'
    if not tb.exists():
        return []
    sources = [*bench.rtl, bench.root / 'fpga/sim/sim_primitives.v',
               bench.root / 'fpga/sim/jtag_dp_model.sv',
               bench.root / 'fpga/sim/xpm_memory_tdpram.sv', tb]
    exe = bench.build('tb_jtag_pipeline', sources)
    rows = []
    for name, args in [('nominal', []), ('late_tdo', ['late']), ('q1_window', ['q1'])]:
        code, out = bench.run(exe, args)
        hss = re.search(r'JTAG HSS bank=(\d+) samples=(\d+) skips=(\d+) scans=(\d+)', out)
        rows.append({'case': name, 'pass': code == 0 and 'PASS JTAG full pipeline' in out,
                     'samples': int(hss.group(2)) if hss else None,
                     'skips': int(hss.group(3)) if hss else None,
                     'tail': out.strip().splitlines()[-1] if out.strip() else ''})
    return rows


def compare(current, base):
    problems = []
    lines = ['', '== SWD packet wire cost (FCLK cycles) ==']
    base_map = {(r['half_ns'], r['words'], r['read'], r['idle']): r['cycles']
                for r in base['swd_packet'] if 'cycles' in r and r.get('rx') == 0}
    for row in current['swd_packet']:
        if 'cycles' not in row:
            continue
        key = (row['half_ns'], row['words'], row['read'], row['idle'])
        ref = base_map.get(key)
        delta = None if ref is None else row['cycles'] - ref
        limit = ref
        if row.get('rx') == 1 and ref is not None:
            limit = ref  # short boundary must not cost more than the legacy path
        ok = delta is not None and delta <= 0
        if not ok:
            problems.append(f'packet half={row["half_ns"]} rx={row.get("rx")} '
                            f'words={row["words"]} read={row["read"]}: {row["cycles"]} vs {ref}')
        lines.append(f'  half={row["half_ns"]:>4} rx={row.get("rx")} words={row["words"]:>4} '
                     f'read={row["read"]} cycles={row["cycles"]:>6} base={ref} delta={delta}'
                     f'{"  OK" if ok else "  REGRESS"}')
    lines.append('== JTAG steady AP read (FCLK cycles per word) ==')
    base_words = {r['speed']: r['word6_fclk'] for r in base['jtag_words']}
    for row in current['jtag_words']:
        ref = base_words.get(row['speed'])
        delta = None if ref is None else row['word6_fclk'] - ref
        ok = delta is not None and delta <= 0
        if not ok:
            problems.append(f'jtag {row["speed"]}: {row["word6_fclk"]} vs {ref}')
        lines.append(f'  {row["speed"]:>8} fclk/word={row["word6_fclk"]} base={ref} '
                     f'delta={delta}{"  OK" if ok else "  REGRESS"}')
    lines.append('== SWD core link (per rate and mode) ==')
    base_core = {(r.get('speed'), r.get('mode', 'link')): r['pass']
                 for r in base.get('swd_core', [])}
    for row in current.get('swd_core', []):
        ref = base_core.get((row['speed'], row.get('mode', 'link')))
        ok = ref is not True or row['pass']
        if not ok:
            problems.append(f'swd {row["speed"]} {row.get("mode")}: failed (baseline passed)')
        lines.append(f'  {row["speed"]:>8} {row.get("mode", "link"):>8} '
                     f'current={"PASS" if row["pass"] else "FAIL"} '
                     f'base={"PASS" if ref else "FAIL" if ref is False else "n/a"}'
                     f'{"  OK" if ok else "  REGRESS"}')
    return lines, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--label', required=True)
    ap.add_argument('--root', type=Path, default=ROOT,
                    help='tree to measure (default: this checkout)')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--compare', type=Path)
    args = ap.parse_args()
    root = args.root.resolve()

    bench = Bench(root, root / 'build/sim_matrix' / args.label)
    tb = (root / 'fpga/sim/tb_packet_wire_budget.sv').read_text(encoding='utf-8')
    result = {
        'label': args.label,
        'commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(root),
                                 capture_output=True, text=True).stdout.strip(),
        'swd_packet': packet_budget(bench, 'RX_BOUNDARY' in tb),
        'swd_core': swd_core_matrix(bench),
        'jtag_words': jtag_words(bench),
        'jtag_pipeline': jtag_pipeline(bench),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')

    for name in ('swd_core', 'jtag_pipeline'):
        for row in result[name]:
            print(f'{name:14s} {row.get("speed", row.get("case")):>10s} '
                  f'{row.get("mode", ""):>8s} '
                  f'{"PASS" if row["pass"] else "FAIL"} {row.get("tail", "")}')
    if args.compare:
        base = json.loads(args.compare.read_text(encoding='utf-8'))
        lines, problems = compare(result, base)
        print('\n'.join(lines))
        print(f'\n{len(problems)} regression(s)')
        if problems:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
