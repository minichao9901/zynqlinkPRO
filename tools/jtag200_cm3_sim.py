"""Simulate the J200 SelectIO path into a Cortex-M3 DAP and guarded SRAM page."""
import argparse
import json
from pathlib import Path

from jtag200 import ROOT, RTL, VIVADO, environment, run_logged
from run_cm3_sim import DEFAULT_RTL


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--rtl', type=Path, default=DEFAULT_RTL)
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--hclk', type=float, default=48)
    cli.add_argument('--point', nargs=4, type=float, action='append', required=True,
                     metavar=('FCLK_HALF_NS', 'TCK_HALF_SLOTS', 'SAMPLE', 'IDLE'))
    args = cli.parse_args()
    model = args.rtl.resolve()
    if not (model / 'cortexm3_integration.v').is_file():
        cli.error('Select the DesignStart CM3DbgAXI RTL directory with --rtl')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    exe = VIVADO / 'bin/unwrapped/win64.o'
    sim = ROOT / 'fpga/sim'
    env = environment()
    run_logged([exe / 'xvlog.exe', '--relax', '-i', model, *sorted(model.glob('*.v')),
                sim / 'axi3_sram.v'], out, out / 'cm3-compile.log', env)
    run_logged([exe / 'xvlog.exe', '--sv', '-d', 'J200_TEST_CM3', *sorted(RTL.glob('*.v')),
                *(ROOT / 'fpga/rtl' / f for f in ('jtag_core.v', 'jtag_shift.v', 'dap_transfer_block_engine.v')),
                *(sim / f for f in ('jtag_dtm_model.sv', 'riscv_sba_model.sv', 'jtag_dp_model.sv',
                                    'cm3_target.sv', 'tb_jtag200.sv')), VIVADO / 'data/verilog/src/glbl.v'],
               out, out / 'compile.log', env)
    run_logged([exe / 'xelab.exe', '-L', 'unisims_ver', '-L', 'secureip', '-s', 'j200_cm3',
                'tb_jtag200', 'glbl'], out, out / 'elab.log', env)
    rows = []
    for ref, half, slot, idle in args.point:
        half, slot, idle = int(half), int(slot), int(idle)
        log = out / f'cm3-{ref}-{half}-{slot}-{idle}.log'
        params = dict(ref=ref, half=half, sample=slot, idle=idle, hclk=args.hclk)
        cmd = [exe / 'xsim.exe', 'j200_cm3', '-runall']
        for key, value in params.items():
            cmd += ['-testplusarg', f'{key}={value}']
        run_logged(cmd, out, log, env)
        lines = [line for line in log.read_text(errors='replace').splitlines()
                 if line.startswith(('J200_', 'Fatal:', 'Error:'))]
        passed = any(line.startswith('J200_CM3_PASS') for line in lines)
        rows.append(dict(**params, tck_MHz=2000/(ref*half), passed=passed, evidence=lines))
        (out / 'result.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(params, *lines, sep='\n', flush=True)
    return 0 if all(row['passed'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
