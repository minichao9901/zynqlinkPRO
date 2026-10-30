"""Run ORBTrace pin tests and real Cortex-M3 ETM capture acceptance.

Requires Icarus Verilog, Vivado 2018.3, licensed DesignStart RTL, and Amaranth
0.5.8. Optionally add --decoder for superlinkPRO's OpenCSD instruction checks.
No probe, board, or USB device is accessed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from check_orbtrace_capture import check


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rtl', type=Path, required=True, help='CM3DbgAXI/rtl directory')
    ap.add_argument('--decoder', type=Path, help='superlinkPRO/etm/build-native/etm_decode.exe')
    ap.add_argument('--work-dir', type=Path, default=ROOT / 'build/orbtrace_sim')
    args = ap.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    (work / 'acceptance.json').unlink(missing_ok=True)

    def run(command, name, cwd=ROOT):
        p = subprocess.run([str(c) for c in command], cwd=cwd, capture_output=True, text=True, errors='replace', timeout=3600)
        (work / f'{name}.log').write_text(p.stdout + p.stderr, encoding='utf-8')
        if p.returncode:
            raise RuntimeError(f'{name} failed:\n{(p.stdout + p.stderr)[-3000:]}')
        return p.stdout

    rtl_files = sorted((ROOT / 'fpga/rtl').glob('orbtrace_*.v'))
    executable = work / 'parallel.vvp'
    run(['iverilog', '-g2012', '-s', 'tb_orbtrace_parallel', '-o', executable,
         *rtl_files, ROOT / 'fpga/sim/sim_primitives.v', ROOT / 'fpga/sim/tb_orbtrace_parallel.sv'], 'iverilog')
    report = {'base': 'dc95b99', 'upstream': 'e416cd5b074fc725a04cf6b877d458e2074467ae', 'pin_tests': [], 'cm3_tests': []}
    for pins in (1, 2, 4):
        for phase in (0, 1):
            output = run(['vvp', executable, f'+pins={pins}', f'+phase={phase}'], f'pins{pins}_phase{phase}')
            if 'PASS' not in output:
                raise RuntimeError('pin test did not report PASS')
            print(next(line for line in output.splitlines() if 'PASS' in line), flush=True)
            report['pin_tests'].append({'pins': pins, 'phase': phase, 'passed': True})
    # The selected CM3 DDR pin mapping is four bits; narrow-pin tests above use
    # explicit physical stimuli, and are not presented as CM3 validation.
    simulator_work = work / 'cm3'
    for name, plusargs in [('cm3_100mhz', []),
                           ('cm3_160mhz_stalls', ['target_clk_ns=6.25', 'etm_stalls'])]:
        output = run([sys.executable, ROOT / 'tools/run_cm3_sim.py', '--top', 'tb_cm3_etm',
                      '--rtl', args.rtl.resolve(), '--work-dir', simulator_work, *plusargs], name)
        print(output.strip(), flush=True)
        capture = work / name
        capture.mkdir(exist_ok=True)
        for file in ('cm3_etm.hex', 'cm3_tpiu.hex', 'cm3_etm_config.json', 'xsim.log'):
            shutil.copy2(simulator_work / file, capture / file)
        validation = check(capture, args.decoder)
        validation.update(name=name, plusargs=plusargs)
        report['cm3_tests'].append(validation)
        print(f"PASS {name}: upstream byte match, {validation['bytes']} bytes"
              + (f", {validation['instruction_ranges']} decoded ranges" if args.decoder else ''), flush=True)
    # Ordinary SWD traffic must still work with the default trace-disabled core.
    print(run([sys.executable, ROOT / 'tools/run_cm3_sim.py', '--top', 'tb_cm3_swd',
               '--rtl', args.rtl.resolve(), '--work-dir', work / 'swd_regression'], 'swd_regression').strip(), flush=True)
    report['swd_regression'] = True
    source_files = [*rtl_files, ROOT/'fpga/sim/cm3_target.sv', ROOT/'fpga/sim/cm3_etm_tasks.svh',
                    ROOT/'fpga/sim/tb_cm3_swd.sv', ROOT/'fpga/sim/tb_cm3_etm.sv',
                    ROOT/'fpga/sim/tb_orbtrace_parallel.sv', ROOT/'fpga/sim/sim_primitives.v',
                    ROOT/'tools/run_cm3_sim.py', ROOT/'tools/run_orbtrace_sim.py', ROOT/'tools/check_orbtrace_capture.py']
    report['source_sha256'] = {str(path.relative_to(ROOT)).replace('\\','/'): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in source_files}
    report['cm3_rtl_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.rtl.glob('*.v'))}
    (work / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS simulation acceptance: {work / "acceptance.json"}')


if __name__ == '__main__':
    main()
