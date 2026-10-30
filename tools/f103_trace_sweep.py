"""Finite real F103ZE TRACECLK sweep; failures and register restoration retained."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from trace_signal_analysis import native_summary, save

ROOT = Path(__file__).resolve().parents[1]


def clocks(cfgr, hse):
    source = (cfgr >> 2) & 3
    if source == 0:
        system = 8_000_000
    elif source == 1:
        system = hse
    elif source == 2:
        incoming = hse / (2 if cfgr & (1 << 17) else 1) if cfgr & (1 << 16) else 4_000_000
        system = incoming * min(16, ((cfgr >> 18) & 15) + 2)
    else:
        raise ValueError('invalid clock source')
    divider = [1]*8 + [2,4,8,16,64,128,256,512]
    hclk = system / divider[(cfgr >> 4) & 15]
    return dict(hseHz=hse, systemHz=system, hclkHz=hclk, traceclkHz=hclk/2,
                basis='actual RCC readback, board HSE supplied; parallel TRACECLK = HCLK/2')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-elf', required=True)
    parser.add_argument('--bit', required=True)
    parser.add_argument('--zynq-elf', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--cpu-mhz', type=int, choices=(48,72), required=True)
    parser.add_argument('--hse-mhz', type=int, default=8)
    parser.add_argument('--divs', default='4,2,1')
    parser.add_argument('--gpio', default='1,3')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--milliseconds', type=float, default=10)
    parser.add_argument('--raw-samples', action='store_true')
    args = parser.parse_args(argv)
    divs, speeds = [int(x) for x in args.divs.split(',')], [int(x) for x in args.gpio.split(',')]
    if set(divs)-{1,2,4} or set(speeds)-{1,2,3} or not 1<=args.rounds<=20:
        parser.error('invalid sweep parameters')
    output = Path(args.out).resolve(); output.mkdir(parents=True, exist_ok=False)
    report = dict(cpuMHz=args.cpu_mhz, rawSamples=args.raw_samples, rows=[],
                  note='Pair paths do not load firmware. Load this exact pair by JTAG before running; Flash is verified each capture.')
    for divider in divs:
        for speed in speeds:
            for trial in range(args.rounds):
                name = f'cpu{args.cpu_mhz}-div{divider}-gpio{speed}-r{trial+1}'
                folder = output/name
                command = [sys.executable, str(ROOT/'tools/test_orbtrace_board.py'),
                           '--target-elf', str(Path(args.target_elf).resolve()), '--bit', str(Path(args.bit).resolve()),
                           '--elf', str(Path(args.zynq_elf).resolve()), '--output', str(folder),
                           '--milliseconds', str(args.milliseconds), '--speed-khz', '1000',
                           '--hclk-div', str(divider), '--gpio-speed', str(speed), '--entry', 'cdc_poll']
                if args.raw_samples:
                    command += ['--raw','--raw-samples']
                run = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
                (output/(name+'.log')).write_bytes(run.stdout+run.stderr)
                acceptance_file = folder/'acceptance.json'
                acceptance = json.loads(acceptance_file.read_text()) if acceptance_file.exists() else {}
                row = dict(name=name, divider=divider, gpioSpeed=speed, trial=trial+1,
                           returnCode=run.returncode, capture=acceptance, accepted=False)
                if 'rcc_capture' in acceptance:
                    row['clocks']=clocks(acceptance['rcc_capture'][1],args.hse_mhz*1_000_000)
                    if row['clocks']['systemHz'] != args.cpu_mhz*1_000_000:
                        raise ValueError('RCC readback disagrees with requested target firmware clock')
                if not run.returncode:
                    if args.raw_samples:
                        row['accepted']=True # physical acquisition only; no TPIU/ETM claim
                    else:
                        data=(folder/'etm.bin').read_bytes()
                        row['decode']=native_summary(data,args.target_elf,acceptance['config'],folder/'decode')
                        row['accepted']=row['decode']['completePacketPass']
                report['rows'].append(row)
                save(output/'sweep.json',report)
                print(name, row.get('clocks',{}).get('traceclkHz'), 'accepted=',row['accepted'],
                      'bytes=',acceptance.get('etm_bytes',acceptance.get('raw_bytes')),flush=True)
                # Failed acquisition is retained and the next finite test is
                # permitted only after all target ownership was restored.
                if not acceptance.get('restored') or not acceptance.get('fpb_restored') or acceptance.get('target_cleanup_error'):
                    raise RuntimeError('target cleanup not proven; sweep stopped')
    return 0


if __name__=='__main__':
    sys.exit(main())
