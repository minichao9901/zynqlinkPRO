"""Read uncached benchmark counters and USB registers through the APU debug port."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['bench_rx_bytes', 'bench_tx_bytes', 'bench_rx_completions', 'bench_tx_completions', 'bench_submit_errors']


def read_status(elf):
    nm = Path(r'E:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-none-eabi\bin\arm-none-eabi-nm.exe')
    symbols = subprocess.check_output([str(nm), '-n', str(elf)], text=True)
    addresses = {m[2]: int(m[1], 16) for m in re.finditer(r'^([0-9a-fA-F]+) \w (\w+)$', symbols, re.M) if m[2] in NAMES + ['bench_sctlr', 'bench_rx_verify_errors', 'bench_rx_expected_seq']}
    if not set(NAMES).issubset(addresses):
        raise RuntimeError('ELF does not contain all benchmark counter symbols')
    addresses.update(usb_command=0xE0002140, usb_status=0xE0002144, usb_portsc=0xE0002184)
    script = ROOT / 'build/cdc_status.tcl'
    lines = ['connect -url tcp:127.0.0.1:3121', 'targets -set -filter {name == "APU"}']
    for name, address in addresses.items():
        lines.append(f'puts "{name}=[format %08X [mrd -force -value 0x{address:08X} 1]]"')
    lines.extend(['disconnect', 'exit'])
    script.write_text('\n'.join(lines) + '\n', encoding='ascii')
    proc = subprocess.run(['python', str(ROOT / 'tools/run_xsct.py'), str(script)], capture_output=True, text=True, timeout=15)
    if proc.returncode:
        raise RuntimeError(proc.stdout + proc.stderr)
    values = {m[1]: int(m[2], 16) for m in re.finditer(r'^(\w+)=([0-9a-fA-F]+)\s*$', proc.stdout, re.M)}
    if set(values) != set(addresses):
        raise RuntimeError('Incomplete status: ' + proc.stdout)
    values['itc'] = (values['usb_command'] >> 16) & 255
    values['usb_speed_code'] = (values['usb_portsc'] >> 26) & 3
    if 'bench_sctlr' in values:
        values['dcache_enabled'] = bool(values['bench_sctlr'] & 4)
        values['icache_enabled'] = bool(values['bench_sctlr'] & 4096)
    return values


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    print(json.dumps(read_status(parser.parse_args().elf), indent=2))
