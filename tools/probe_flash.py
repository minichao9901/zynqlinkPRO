"""Back up, program and verify a Zynq-7020 probe's single QSPI flash."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Session:
    def __init__(self, out, sdk, url):
        self.out, self.sdk, self.url = out, sdk, url
        self.index = 0

    def run(self, body):
        self.index += 1
        script = self.out/f'{self.index:03d}.tcl'
        script.write_text('connect -url {'+self.url+'}\nset selected 0\n'
            'for {set n 0} {$n < 50} {incr n} {\n'
            ' if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}\n'
            ' after 100\n}\nif {!$selected} {error $why}\n'+body+'\ndisconnect\nexit\n')
        result = subprocess.run([sys.executable, str(ROOT/'tools/run_xsct.py'), str(script), '--sdk', str(self.sdk)],
            capture_output=True, text=True, errors='replace', timeout=1200)
        (self.out/f'{self.index:03d}.log').write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(result.stdout+result.stderr)
        return result.stdout

    def read_words(self, address, count=1):
        s = self.run(f'puts "VALUES [mrd -force -value {address:#x} {count}]"')
        values = re.search(r'VALUES ([^\r\n]+)', s)
        if not values:
            raise RuntimeError('XSCT did not return memory values: '+s)
        return [int(v, 0) for v in values[1].split()]

    def reader(self, image):
        # A live probe may be in Thumb state. `dow` changes PC but does not
        # reliably reset CPSR/MMU/cache state; reset CPU0 before the ARM helper.
        self.run('rst -processor')
        self.run('source {'+(image/'ps7_init.tcl').as_posix()+'}\nps7_init\n'
                 'dow {'+(image/'qspi_read.elf').as_posix()+'}')
        self.run('con')
        for _ in range(30):
            words = self.read_words(0x03ff0000, 3)
            if words[0] == 0x51535049:
                return words
            if words[0] & 0xffff0000 == 0xdead0000:
                raise RuntimeError(f'QSPI helper failed: {words}')
            time.sleep(.2)
        raise TimeoutError('QSPI helper did not become ready')

    def read_flash(self, length, destination):
        if destination.exists():
            raise FileExistsError(destination)
        self.run('catch {stop}')
        self.run(f'mwr -force 0x03ff0010 0\nmwr -force 0x03ff0014 {length}\nmwr -force 0x03ff000c 1')
        self.run('con')
        deadline = time.monotonic()+900
        while True:
            status = self.read_words(0x03ff000c)[0]
            if status == 2:
                break
            if status != 1:
                raise RuntimeError(f'QSPI read failed: {status:#x}')
            if time.monotonic() >= deadline:
                raise TimeoutError('QSPI read timed out; flash was not modified')
            time.sleep(3)
        self.run('catch {stop}')
        self.run('mrd -force -bin -file {'+destination.as_posix()+f'}} 0x04000000 {(length+3)//4}\nputs READ_COMPLETE')
        if destination.stat().st_size != (length+3)//4*4:
            raise RuntimeError('Incomplete flash readback')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image-dir', type=Path, default=ROOT/'prebuilt/recovery')
    p.add_argument('--sdk', type=Path, default=Path('E:/Xilinx/SDK/2018.3'))
    p.add_argument('--url', default='tcp:127.0.0.1:3121')
    p.add_argument('--out', type=Path)
    p.add_argument('--dry-run', action='store_true', help='validate files and display plan without touching hardware')
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--backup-only', action='store_true')
    modes.add_argument('--verify-only', action='store_true', help='read back the existing image and test reset boot without erasing/programming')
    a = p.parse_args(argv)
    image = a.image_dir.resolve()
    manifest = json.loads((image/'flash_manifest.json').read_text())
    required = {'BOOT.bin','fsbl_programmer.elf','qspi_read.elf','ps7_init.tcl','probe.bit','application.elf'}
    if not required <= manifest['files'].keys():
        raise ValueError('Boot package manifest is missing required files')
    for name, expected in manifest['files'].items():
        if Path(name).name != name or sha(image/name) != expected:
            raise ValueError('Image file SHA-256 mismatch: '+name)
    boot = image/'BOOT.bin'
    if not 0 < boot.stat().st_size < 16<<20:
        raise ValueError('Boot image must fit in first 16MiB')
    out = (a.out or ROOT/'build'/('probe-flash-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
    plan = dict(image_dir=str(image), out=str(out), boot_sha256=sha(boot),
                operation=('backup only' if a.backup_only else 'verify existing image -> system reset' if a.verify_only
                    else 'full backup -> program/verify -> full readback SHA-256 -> system reset'))
    print(json.dumps(plan, indent=2), flush=True)
    if a.dry_run:
        return 0
    out.mkdir(parents=True, exist_ok=False)
    session = Session(out, a.sdk, a.url)
    report = dict(plan, status='started', source=manifest)
    try:
        mode = session.read_words(0xf800025c)[0]&15
        part = session.read_words(0xf8000530)[0]
        if (part & 0x0fffffff) != 0x03727093:
            raise RuntimeError(f'Expected XC7Z020; got {part:#x}')
        if not a.backup_only and mode != 1:
            raise RuntimeError('Set QSPI boot straps and power-cycle first (BOOT_MODE must equal 1)')
        info = session.reader(image)
        if info[1] != 0xef4019:
            raise RuntimeError(f'Unvalidated flash geometry: JEDEC {info[1]:06x}')
        if info[2] & 0x7d:
            raise RuntimeError(f'Flash busy/protected: status {info[2]:02x}')
        report.update(boot_mode=mode, ps_idcode=f'{part:08x}', jedec_id=f'{info[1]:06x}', flash_bytes=32<<20)
        backup = out/'original_flash_32MiB.bin'
        if not a.verify_only:
            print('Backing up full 32MiB flash...', flush=True)
            session.read_flash(32<<20, backup)
            report['backup'] = dict(path=str(backup), bytes=backup.stat().st_size, sha256=sha(backup))
            (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        if a.backup_only:
            report['status']='backup_complete'
            return 0
        command = [str(a.sdk/'bin/program_flash.bat'), '-f', str(boot), '-offset', '0',
                   '-flash_type', 'qspi-x4-single', '-fsbl', str(image/'fsbl_programmer.elf'),
                   '-blank_check', '-verify', '-url', a.url]
        if not a.verify_only:
            print('Backup complete. Programming and verifying BOOT.bin...', flush=True)
            report['program_command']=command
            result = subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=1200)
            (out/'program_flash.log').write_text(result.stdout+result.stderr)
            if result.returncode or 'Flash Operation Successful' not in result.stdout:
                raise RuntimeError('program_flash failed; inspect program_flash.log and keep original backup')
            session.reader(image)
        readback = out/'programmed_readback.bin'
        session.read_flash(boot.stat().st_size if a.verify_only else 32<<20,readback)
        if readback.read_bytes()[:boot.stat().st_size] != boot.read_bytes():
            raise RuntimeError('Flash readback differs from BOOT.bin')
        report['readback_sha256']=hashlib.sha256(readback.read_bytes()[:boot.stat().st_size]).hexdigest()
        if not a.verify_only:
            erase_end=(boot.stat().st_size+4095)&~4095
            report['outside_erased_range_unchanged']=readback.read_bytes()[erase_end:]==backup.read_bytes()[erase_end:]
            if not report['outside_erased_range_unchanged']:
                raise RuntimeError('Flash outside intended erase range changed')
        session.run('mwr -force 0x03ff0000 0 8\nmwr -force 0xf8000008 0xdf0d\n'
                    'set m [mrd -force -value 0xf800702c]\nmwr -force 0xf800702c [expr {$m & ~0x1fff}]')
        # SDK 2018.3's public `rst -system` explicitly requests suspend=1,
        # stopping at the reset vector. Use the same reset service with
        # suspend=0 to test autonomous boot without a debugger `con`.
        session.run('::tcf::send_command [::xsdb::getcurchan] XilinxReset reset '
                    'sso{[dict create suspend b]} e '
                    '[list [::xsdb::getcurtarget] system [dict create suspend 0]]\nputs RESET_NO_HALT')
        time.sleep(5)
        trace=session.read_words(0x03ff0000,8)
        report['boot_trace']=trace
        if trace[0]!=0x53544730 or trace[3]!=1 or trace[5]!=0x600 or trace[6]!=0 or trace[7]!=1:
            raise RuntimeError('QSPI reset boot did not reach OCM application handoff: '+str(trace))
        report['status']='programmed_verified_reset_boot'
        print('Flash verified; QSPI reset boot reached OCM application.',flush=True)
        return 0
    except Exception as error:
        report.update(status='failed',error=str(error))
        raise
    finally:
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    raise SystemExit(main())
