"""Memory access to a prepared, exact target image on the selected J7."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import json
import secrets
import struct
import sys

from elftools.elf.elffile import ELFFile

import usb.util

from benchmark_hpm5301 import setup as setup_riscv
from dap_pipeline_bench import cmd, drain, open_dap, prepare_arm_jtag, setup
from riscv_target import RiscvTarget
from test_probe_board import Memory

CPUID = {'f103ze': 0xc23, 'h743': 0xc27}
MCU_ID = {'f103ze': (0xe0042000, 0x414), 'h743': (0x5c001000, 0x450)}


def confirm_spi_route(route):
    if not sys.stdin.isatty():
        raise RuntimeError('SPI wiring confirmation requires an interactive terminal')
    expected = route.upper()
    print(f'Isolate the other route, select {expected}, then type {expected}.', file=sys.stderr, flush=True)
    if input().strip().upper() != expected:
        raise RuntimeError(f'{expected} wiring was not confirmed')


class TargetImage:
    def __init__(self, path, board):
        self.path = Path(path).resolve()
        self.board = board
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.path.open('rb') as source:
            elf = ELFFile(source)
            expected = 'EM_RISCV' if board == 'hpm6800evk' else 'EM_ARM'
            if elf['e_machine'] != expected or not elf.little_endian or elf.elfclass != 32:
                raise ValueError(f'ELF does not match {board}: {path}')
            table = elf.get_section_by_name('.symtab')
            self.symbols = {s.name: s['st_value'] for s in table.iter_symbols()
                            if s.name and s['st_shndx'] != 'SHN_UNDEF'}
            self.segments = [(s['p_paddr'], s.data()) for s in elf.iter_segments()
                             if s['p_type'] == 'PT_LOAD' and s['p_filesz']]
            if not self.segments:
                raise ValueError('ELF has no file-backed load segment.')

    def address(self, name):
        if name not in self.symbols:
            raise ValueError(f'{self.path.name} is missing {name}')
        return self.symbols[name]

    def word(self, io, name):
        return struct.unpack('<I', read_bytes(io, self.address(name), 4))[0]

    def set_word(self, io, name, value):
        address=self.address(name)
        if address % 4:
            raise ValueError(f'Word mailbox not aligned: {name}')
        io.write(address,struct.pack('<I',value))
        if self.word(io,name)!=value:
            raise RuntimeError(f'Write readback failed: {name}')

    def verify(self, io):
        if self.board in CPUID:
            register, expected_id = MCU_ID[self.board]
            cpu = struct.unpack('<I', read_bytes(io, 0xe000ed00, 4))[0]
            chip = struct.unpack('<I', read_bytes(io, register, 4))[0]
            if (cpu >> 4) & 0xfff != CPUID[self.board] or chip & 0xfff != expected_id:
                raise RuntimeError(f'CPU or DBGMCU identity differs for {self.board}: {cpu:#x}/{chip:#x}')
        result=[]
        for address, expected in self.segments:
            real=read_bytes(io,address,len(expected))
            if real!=expected:
                raise RuntimeError(f'Live bytes differ from target ELF at {address:#010x}')
            result.append({'address':address,'bytes':len(expected),
                           'sha256':hashlib.sha256(real).hexdigest()})
        return result

    def clocks(self, io, cpu, hclk=None):
        values={key:self.word(io,key) for key in ('g_cpu_hz','g_hclk_hz','g_clock_error')}
        if values['g_clock_error'] or values['g_cpu_hz'] != cpu*1000000:
            raise RuntimeError(f'Target clock failed verification: {values}')
        if hclk is not None and values['g_hclk_hz'] != hclk*1000000:
            raise RuntimeError(f'Target HCLK failed verification: {values}')
        if self.board in MCU_ID:
            from target_snapshot import snapshot
            values['registers'] = snapshot(io)
        else:
            values['g_mchtmr_hz'] = self.word(io, 'g_mchtmr_hz')
        return values


def read_bytes(io, address, length):
    start=address & ~3
    offset=address-start
    data=io.read(start,(offset+length+3)&~3)
    if len(data)<offset+length:
        raise RuntimeError(f'Short target read at {address:#x}')
    return data[offset:offset+length]


@contextmanager
def target_io(board, serial, transport=None, rate=1_000_000):
    if board=='hpm6800evk':
        if transport not in (None,'riscv-jtag'):
            raise ValueError('HPM uses RISC-V JTAG.')
    elif transport=='arm-jtag':
        prepare_arm_jtag(serial)
    dev,tx,rx=open_dap(serial)
    try:
        if board=='hpm6800evk':
            drain(rx)
            setup_riscv(tx,rx,rate,connect=True)
            target=RiscvTarget(tx,rx)
            dmstatus=target.active()
            if (dmstatus & 0xf) not in (2, 3) or not dmstatus & (1 << 7):
                raise RuntimeError(f'Unexpected RISC-V debug module: {dmstatus:#x}')
        else:
            setup(tx,rx,rate//1000,'jtag' if transport=='arm-jtag' else 'swd',speed_hz=rate)
            target=Memory(tx,rx)
        yield target
    finally:
        try:
            if cmd(tx, rx, [3]) != b'\x03\x00':
                raise RuntimeError('DAP disconnect could not be confirmed')
        finally:
            usb.util.release_interface(dev,0)
            usb.util.dispose_resources(dev)


def bind_probe_identity(serial, cable, out):
    from probe_flash import Session
    from probe_load import check_streams, probe_state
    from zynq_memory import PhysicalMemory

    dir_path = out / 'usb-ap0'
    dir_path.mkdir()
    session = Session(dir_path, Path('E:/Xilinx/SDK/2018.3'), 'tcp:127.0.0.1:3121', cable_serial=cable)
    streams = check_streams(serial)
    idle = probe_state(session, cable_serial=cable)
    physical = PhysicalMemory(session, cable_serial=cable)
    dev, tx, rx = open_dap(serial)
    try:
        drain(rx)

        def timing(setting):
            response = cmd(tx, rx, [0x89, setting])
            if len(response) != 15 or response[1] != 0:
                raise RuntimeError('JTAG timing vendor command failed')
            return response[2]

        def ap0():
            return physical.read_words(0x40010098)[0] & 17

        original = timing(255)
        if original not in (0, 1, 16, 17) or ap0() != original:
            raise RuntimeError('USB and physical MEM-AP0 timing differ')
        challenge = secrets.SystemRandom().sample([value for value in (0, 1, 16, 17) if value != original], 3)
        try:
            for value in challenge:
                if timing(value) != value or ap0() != value:
                    raise RuntimeError('The selected USB and HS3 do not address the same probe')
        finally:
            if timing(original) != original or timing(255) != original or ap0() != original:
                raise RuntimeError('JTAG timing restore failed')
        (dir_path / 'identity.json').write_text(json.dumps({
            'usb': serial, 'cable': cable, 'streams': streams, 'physical_idle': idle,
            'challenge': challenge, 'original': original, 'restored': True,
        }, indent=2), encoding='utf8')
    finally:
        usb.util.dispose_resources(dev)
