"""Run cache/sector comparisons on the dedicated Zynq RAM-disk firmware."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import time
from msc_disk_bench import benchmark, find_ram_disk

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['read_commands', 'write_commands', 'read_bytes', 'write_bytes', 'max_read_length', 'max_write_length', 'sctlr', 'reserved']


def status(elf):
    nm = Path(r'E:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-none-eabi\bin\arm-none-eabi-nm.exe')
    symbols = subprocess.check_output([str(nm), '-n', str(elf)], text=True)
    address = int(re.search(r'^([0-9a-fA-F]+) \w msc_stats$', symbols, re.M)[1], 16)
    addresses = {name: address + 4 * i for i, name in enumerate(NAMES)}
    addresses.update(usb_command=0xE0002140, usb_portsc=0xE0002184)
    script = ROOT / 'build/msc_status.tcl'
    lines = ['connect -url tcp:127.0.0.1:3121', 'targets -set -filter {name == "APU"}']
    for name, addr in addresses.items():
        lines.append(f'puts "{name}=[format %08X [mrd -force -value 0x{addr:08X} 1]]"')
    lines += ['disconnect', 'exit']
    script.write_text('\n'.join(lines) + '\n', encoding='ascii')
    proc = subprocess.run(['python', str(ROOT / 'tools/run_xsct.py'), str(script)], capture_output=True, text=True, timeout=15)
    if proc.returncode:
        raise RuntimeError(proc.stdout + proc.stderr)
    values = {m[1]: int(m[2], 16) for m in re.finditer(r'^(\w+)=([0-9a-fA-F]+)\s*$', proc.stdout, re.M)}
    if set(values) != set(addresses):
        raise RuntimeError('Missing status fields ' + proc.stdout)
    values.update(itc=(values['usb_command'] >> 16) & 255, speed=(values['usb_portsc'] >> 26) & 3,
                  dcache_enabled=bool(values['sctlr'] & 4), icache_enabled=bool(values['sctlr'] & 4096))
    return values


def main():
    folder = ROOT / 'results/msc'
    folder.mkdir(parents=True, exist_ok=True)
    for sector, cache in [(4096, 'on'), (4096, 'off'), (512, 'on')]:
        tag = f'sector{sector}_dcache{cache}_O0_itc0'
        elf = ROOT / 'build/msc_bench' / tag / 'msc_bench.elf'
        result = {'tag': tag, 'elf_sha256': hashlib.sha256(elf.read_bytes()).hexdigest()}
        print('START', tag, flush=True)
        try:
            proc = subprocess.run(['python', str(ROOT / 'tools/run_xsct.py'), str(ROOT / 'tools/download_cdc.tcl'), str(elf)], capture_output=True, text=True, timeout=35)
            (folder / (tag + '_download.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
            if proc.returncode:
                raise RuntimeError('Download failed')
            time.sleep(2)
            find_ram_disk()
            result['before'] = status(elf)
            if result['before']['dcache_enabled'] != (cache == 'on') or result['before']['speed'] != 2 or result['before']['itc'] != 0:
                raise RuntimeError('Unexpected cache/USB register state')
            result.update(benchmark())
            result['after'] = status(elf)
            result['status'] = 'passed'
            print('PASS', tag, result['median_MB_per_second'], flush=True)
        except Exception as exc:
            result['status'] = 'failed'
            result['error'] = str(exc)
            print('FAIL', tag, str(exc), flush=True)
        (folder / (tag + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
