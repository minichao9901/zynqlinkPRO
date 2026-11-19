"""Run a J200 experiment inside a backed-up F103ZE CDC48 SRAM fixture."""
import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time

import usb.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.board_acceptance_target import elf_contents
from dap_pipeline_bench import open_dap, select_arm_jtag, setup, xfer
from h743_peak import measure_pipeline
from jtag200 import ROOT
from jtag200_pipeline import need
from run_f103_jtag_fixture import DHCSR, APB2ENR, MAPR, SWJ_MASK
import run_f103_clock_fixture as clocks
from target_snapshot import snapshot
from test_probe_board import Memory

PAGE = 0x20008000
SIZE = 4096
TAP = 0x3ba00477
SERIAL = '12345678'


@contextmanager
def low_link():
    end = time.monotonic() + 12
    while True:
        try:
            device, tx, rx = open_dap(SERIAL)
            break
        except RuntimeError:
            if time.monotonic() >= end:
                raise
            time.sleep(.25)
    try:
        setup(tx, rx, 1000)
        mem = Memory(tx, rx)
        need(mem.word(0xe0042000) == 0x10036414 and mem.word(0xe000ed00) == 0x411fc231,
             'Expected STM32F103ZE CDC target')
        yield mem
    finally:
        try:
            xfer(tx, rx, [3])
        finally:
            usb.util.dispose_resources(device)


def clock_state(mem):
    return {name: mem.word(addr) for name, addr in (
        ('CR', clocks.CR), ('CFGR', clocks.CFGR), ('APB1ENR', clocks.APB1ENR), ('FLASH_ACR', clocks.FLASH))}


def guards(mem):
    return [mem.word(PAGE - 4), mem.word(PAGE + SIZE)]


def write_report(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    # Windows readers can briefly deny delete sharing during atomic replacement.
    deadline = time.monotonic() + 5
    while True:
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.05)


def save(folder, data):
    write_report(folder/'state.json', data)


def restore(folder, st):
    with low_link() as mem:
        need(mem.word(DHCSR) & (1 << 17), 'Core unexpectedly running during fixture recovery')
        if 'ram_sha256' in st:
            saved = (folder / 'backup.bin').read_bytes()
            need(len(saved) == SIZE and sha256(saved).hexdigest() == st['ram_sha256'], 'Invalid saved RAM')
            actual = mem.read(PAGE, SIZE)
            st['before_restore_sha256'] = sha256(actual).hexdigest()
            st['guard_before_restore'] = guards(mem)
            if actual != saved:
                mem.write(PAGE, saved)
            need(mem.read(PAGE, SIZE) == saved and guards(mem) == st['guards'], 'SRAM/guard restoration failed')
            st['restored_bytes'] = SIZE
        if 'mapr' in st:
            mem.write_word(MAPR, st['mapr'] | (2 << 24))
            need(mem.word(MAPR) & ~SWJ_MASK == st['mapr'], 'AFIO restore failed')
        if 'apb2' in st:
            mem.write_word(APB2ENR, st['apb2'])
            need(mem.word(APB2ENR) == st['apb2'], 'APB2 restore failed')
        if 'clock_before' in st:
            clocks.restore(mem, st['clock_before'])
            st['clock_after'] = clock_state(mem)
            need(st['clock_after'] == st['clock_before'], 'Clock or Flash wait-state restore failed')
        need(snapshot(mem) == st['target'], 'RCC/target changed')
        if 'previous_sampling' in st:
            need(xfer(mem.out, mem.inp, [0x89, st['previous_sampling']])[2] == st['previous_sampling'],
                 'Probe sampling restore failed')
        desired = st['dhcsr'] & 0x2f
        mem.write_word(DHCSR, 0xa05f0000 | desired)
        final = mem.word(DHCSR)
        need((final ^ st['dhcsr']) & 0x2002f == 0, 'Core state restore failed')
        st.update(final_dhcsr=hex(final), restored=True)
        save(folder, st)


def run(args):
    folder = args.out.resolve()
    if args.restore:
        st = json.loads((folder / 'state.json').read_text())
        need(not st.get('restored'), 'Fixture already restored')
        restore(folder, st)
        return
    folder.mkdir(parents=True, exist_ok=False)
    st = {}
    halted = False
    try:
        with low_link() as mem:
            elf = ROOT / 'prebuilt/golden/f103ze-cdc48.elf'
            _, segments = elf_contents(elf)
            for address, content, _ in segments:
                need(mem.read(address, len(content)) == content, 'CDC48 firmware identity mismatch')
            st.update(target=snapshot(mem), dhcsr=mem.word(DHCSR), elf_sha256=sha256(elf.read_bytes()).hexdigest())
            save(folder, st)
            mem.write_word(DHCSR, 0xa05f0003)
            halted = True
            need(mem.word(DHCSR) & (1 << 17), 'Halt failed')
            original = mem.read(PAGE, SIZE)
            st['guards'] = guards(mem)
            need(mem.read(PAGE, SIZE) == original and guards(mem) == st['guards'], 'Unstable backup')
            (folder / 'backup.bin').write_bytes(original)
            st.update(ram_sha256=sha256(original).hexdigest(), apb2=mem.word(APB2ENR))
            save(folder, st)
            mem.write_word(APB2ENR, st['apb2'] | 1)
            st['mapr'] = mem.word(MAPR) & ~SWJ_MASK
            save(folder, st)
            if args.hclk != 48:
                st['clock_before'] = clock_state(mem)
                need(st['clock_before']['CFGR'] == 0x51040a, 'Expected CDC48 HSE8 x6 at entry')
                save(folder, st)
                clocks.set_hse8_clock(mem, st['clock_before'], args.hclk//8, 5, 4)
                st['clock_active'] = clock_state(mem)
                st['dwt'] = clocks.dwt_check(mem, folder/'clock.json', args.hclk*1_000_000)
            mem.write_word(MAPR, st['mapr'])
            tx, rx = mem.out, mem.inp
            tap = setup(tx, rx, 1000, 'jtag')
            need(int.from_bytes(tap[2:], 'little') == TAP, 'F103 JTAG TAP identity mismatch')
            # TAP reset selects IDCODE on both devices. Capture the chain before
            # any explicit IR selection puts the boundary TAP into BYPASS.
            select_arm_jtag(tx, rx)
            ids = xfer(tx, rx, [0x14, 3, 0x41, 0, 2, 0, 0x80, *([0]*8)])
            need(len(ids)==10 and ids[:2]==bytes((0x14,0)), 'Dual TAP capture failed')
            st['chain_tdo_first'] = [hex(int.from_bytes(ids[n:n+4], 'little')) for n in (2,6)]
            save(folder, st)
            need(st['chain_tdo_first'] == [hex(TAP), '0x6414041'], 'Unexpected F103 TAP chain')
            setup(tx, rx, 1000, 'jtag')
            need(mem.read(PAGE, SIZE) == original, 'JTAG low speed SRAM mismatch')
            st['tap'] = hex(TAP)
            st['hclk_mhz'] = args.hclk
            save(folder, st)
            if args.baseline:
                st['previous_sampling'] = xfer(tx, rx, [0x89, 255])[2]
                need(xfer(tx, rx, [0x89, 16])[2] == 16, 'Late TDO sampling rejected')
                setup(tx, rx, 60000, 'jtag')
                st['sampling'] = xfer(tx, rx, [0x89, 255])[2]
                st['clock_reply'] = xfer(tx, rx, [0x80,255]).hex()
                save(folder, st)
                st['baseline'] = measure_pipeline(mem, PAGE, words=512, depth=32, loops=256,
                                                  repeats=3, soak_seconds=10)
                save(folder, st)
            if args.command:
                # Leave the TAP selected before disconnecting the temporary CMSIS-DAP.
                need(not args.baseline, 'Keep the USB and experimental fixtures independent')
        if args.command:
            subprocess.run(args.command, cwd=ROOT, check=True)
    except BaseException as exc:
        st['error'] = repr(exc)
        raise
    finally:
        try:
            save(folder, st)
        finally:
            if halted:
                restore(folder, st)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hclk', choices=(48,96,128), type=int, default=48)
    p.add_argument('--out', type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--baseline', action='store_true')
    mode.add_argument('--restore', action='store_true')
    mode.add_argument('--command', nargs=argparse.REMAINDER)
    p.add_argument('--execute', action='store_true')
    args = p.parse_args()
    if args.execute:
        run(args)
    else:
        print('Temporary JTAG fixture on CDC48, guarded 4 KiB backup, selected HCLK and verified clock restoration.')
