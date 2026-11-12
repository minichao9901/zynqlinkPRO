"""经 JTAG 临时加载探针 bit 和 PS ELF，并独立核对 OCM。"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

try:
    from .probe_flash import Session, sha
    from .verify_probe_ocm_code import read_ocm_code
    from .zynq_memory import PhysicalMemory
except ImportError:
    from probe_flash import Session, sha
    from verify_probe_ocm_code import read_ocm_code
    from zynq_memory import PhysicalMemory


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
RELEASE = ROOT / 'prebuilt/release-20261106'


def inputs(args):
    if bool(args.bit) != bool(args.elf) or (args.ps_init and not args.elf):
        raise ValueError('自选配对须同时传 --bit 和 --zynq-elf，可用 --ps-init 指定初始化 Tcl')
    bit = (args.bit or RELEASE / 'probe.bit').resolve()
    elf = (args.elf or RELEASE / 'application.elf').resolve()
    init = (args.ps_init or elf.with_name('ps7_init.tcl')).resolve()
    files = {}
    for key, path, suffix in [('bit', bit, '.bit'), ('zynq_elf', elf, '.elf'), ('ps_init', init, '.tcl')]:
        if path.suffix.lower() != suffix or not path.is_file() or not path.stat().st_size:
            raise ValueError(f'缺少有效的 {suffix} 文件：{path}')
        files[key] = {'path': str(path), 'sha256': sha(path)}
    if not args.bit:
        manifest = json.loads((RELEASE / 'manifest.json').read_text(encoding='utf8'))
        for file in files.values():
            name = Path(file['path']).name
            if manifest['files'][name]['sha256'] != file['sha256']:
                raise ValueError('正式配对 SHA-256 不匹配：' + name)
    read_ocm_code(elf)
    return files


def probe_state(session):
    """Skip fabric accesses when PS reports isolation or reset."""
    output = PhysicalMemory(session).run('''
set part [physrd -force -value 0xf8000530]
if {($part & 0x0fffffff) != 0x03727093} {error "Expected XC7Z020"}
puts [format "LOAD_STATE PS_IDCODE %08x" $part]
set isolation [physrd -force -value 0xf8000900]
set reset [physrd -force -value 0xf8000240]
puts [format "LOAD_STATE LEVEL_SHIFTERS %08x" $isolation]
puts [format "LOAD_STATE FPGA_RESET %08x" $reset]
puts [format "LOAD_STATE BOOT_MODE %08x" [expr {[physrd -force -value 0xf800025c] & 15}]]
if {($isolation & 15) == 15 && ($reset & 15) == 0} {
    set features [physrd -force -value 0x40030048]
    foreach {name addr} {CAPTURE 0x40030008 SWD 0x40010004} {
        puts [format "LOAD_STATE %s %08x" $name [physrd -force -value $addr]]
    }
    if {[physrd -force -value 0x4001004c] & 4} {
        puts [format "LOAD_STATE PACKET %08x" [physrd -force -value 0x42020004]]
    }
    if {$features & 0x100} {
        puts [format "LOAD_STATE DDR %08x" [physrd -force -value 0x40040008]]
        puts [format "LOAD_STATE CDMA %08x" [physrd -force -value 0x40020004]]
    }
}
''')
    values = {key: int(value, 16) for key, value in re.findall(r'LOAD_STATE (\w+) ([\da-f]{8})', output, re.I)}
    if not {'LEVEL_SHIFTERS', 'FPGA_RESET'} <= values.keys():
        raise RuntimeError('未读取到探针 PS/PL 状态')
    if values['LEVEL_SHIFTERS'] & 15 == 15 and values['FPGA_RESET'] & 15 == 0:
        if not {'CAPTURE', 'SWD'} <= values.keys():
            raise RuntimeError('未读取到已启用 PL 的引擎状态')
        busy = (values['CAPTURE'] & 1 or values['SWD'] & 1 or values.get('PACKET', 0) & 15
                or values.get('DDR', 0) & 33 or not values.get('CDMA', 2) & 2)
        if busy:
            raise RuntimeError('探针的采集、调试或 DMA 引擎仍在运行')
    return {key: hex(value) for key, value in values.items()}


def check_streams():
    import hid
    from probe_stream import Probe

    if not any(device['usage_page'] == 0xff00 for device in hid.enumerate(0x0d28, 0x0204)):
        return {}
    probe = Probe()
    try:
        status = {}
        for name, service in [('rtt', 0x31), ('hss', 0x32)]:
            rc, words = probe.action(service, 2)
            if rc or words[0] & 1:
                raise RuntimeError(f'{name.upper()} 正在运行或无法确认状态，状态码 {rc}')
            status[name] = words[0]
        return status
    finally:
        probe.close()


def execute(plan, out, sdk):
    sys.path.insert(0, str(ROOT / 'etm-service/tools'))
    from probe_ownership import Ownership

    out.mkdir(parents=True, exist_ok=False)
    result = {**plan, 'stage': 'preflight', 'passed': False}
    lease = None
    try:
        lease = Ownership()
        result['streams'] = check_streams()
        result['before'] = probe_state(Session(out, sdk, 'tcp:127.0.0.1:3121'))
        if plan['operation'] == 'check':
            result.update(stage='complete', passed=True)
            return 0
        for stage, log in [('load', 'load.log'), ('verify', 'verify.log')]:
            result['stage'] = stage
            with (out / log).open('w', encoding='utf8') as stream:
                child = subprocess.run(plan['commands'][stage], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            if child.returncode:
                raise RuntimeError(f'{stage} 失败（退出码 {child.returncode}），见 {out / log}')
        report = json.loads((out / 'ocm' / 'result.json').read_text(encoding='utf8'))
        if not report['passed'] or report['elf_sha256'] != plan['files']['zynq_elf']['sha256']:
            raise RuntimeError('板上 OCM 执行代码身份核对失败')
        result.update(stage='complete', passed=True, verifiedBytes=report['expected_executable_bytes'],
                      FCLK_Hz=report['initial_FCLK_Hz'])
    except Exception as error:
        result['error'] = str(error)
    finally:
        if lease is not None:
            lease.close()
        (out / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
        print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0 if result['passed'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog='toolbox.py probe-load', description=__doc__,
        epilog='默认使用正式 J7 配对。需要断电后自动启动时，请使用 toolbox.py probe-flash --help。')
    parser.add_argument('--bit', type=Path, help='探针 FPGA bitstream')
    parser.add_argument('--zynq-elf', '--elf', dest='elf', type=Path, help='探针 Zynq PS ELF')
    parser.add_argument('--ps-init', type=Path, help='配套初始化 Tcl，自选时默认取 ELF 同目录 ps7_init.tcl')
    parser.add_argument('--out', type=Path, help='新证据目录，默认 build/probe-load-<时间>')
    parser.add_argument('--sdk', type=Path, default=Path('E:/Xilinx/SDK/2018.3'), help='Xilinx SDK 2018.3 目录')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='核对输入并显示计划，离线执行')
    mode.add_argument('--check-only', action='store_true', help='只读检查 JTAG、BOOT_MODE 和探针忙闲')
    args = parser.parse_args(argv)
    try:
        files = inputs(args)
    except (ValueError, IndexError, KeyError, OSError, struct.error) as error:
        parser.error(str(error))
    out = (args.out or ROOT / 'build' / datetime.now().strftime('probe-load-%Y%m%d-%H%M%S-%f')).resolve()
    if out.exists():
        parser.error(f'证据目录已存在：{out}')
    sdk = args.sdk.resolve()
    python = [sys.executable, '-X', 'utf8']
    commands = {
        'load': [*python, str(TOOLS / 'run_xsct.py'), str(TOOLS / 'download_dap_fpga.tcl'),
                 *(files[key]['path'] for key in ('zynq_elf', 'bit', 'ps_init')), '--sdk', str(sdk)],
        'verify': [*python, str(TOOLS / 'verify_probe_ocm_code.py'), '--elf', files['zynq_elf']['path'],
                   '--out-dir', str(out / 'ocm'), '--sdk', str(sdk)],
    }
    plan = {'operation': 'check' if args.check_only else 'JTAG/RAM', 'dryRun': args.dry_run,
            'out': str(out), 'files': files}
    if not args.check_only:
        plan['commands'] = commands
    if args.dry_run:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0
    return execute(plan, out, sdk)


if __name__ == '__main__':
    raise SystemExit(main())
