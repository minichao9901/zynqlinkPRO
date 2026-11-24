"""Serial-bound native access and restorable memory fixtures for board acceptance."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import time

from tools.run_board_acceptance import Pending, ROOT, Unsafe, write_json

DHCSR = 0xe000edf0
DEMCR = 0xe000edfc
S_RESET_ST = 1 << 25
FPB = 0xe0002000
ARM_REGISTERS = tuple(range(19)) + (20,)
RV_DCSR = 0x7b0
RV_DCSR_STEP = 1 << 2
RV_REGISTERS = (RV_DCSR, 0x7b1, 0x300, 0x305, 0x340, 0x341, 0x342, 0x343,
                *range(0x1001, 0x1020))
RV_STATE = 0xf0400000
RV_CODE = 0x10000
RV_GCC = Path('E:/sdk_env_v1.11.0/toolchains/rv32imac_zicsr_zifencei_multilib_b_ext-win/bin/riscv32-unknown-elf-gcc.exe')
SRAM = {'f103ze': 0x20008000, 'h743': 0x24040000, 'hpm6800evk': 0xf0406000}
RTT_BASE = {'f103ze': 0x20000000, 'h743': 0x24040000, 'hpm6800evk': RV_STATE}
FLASH = {'f103ze': (0x08000000, 0x80000, 0x800),
         'h743': (0x08000000, 0x200000, 0x20000),
         'hpm6800evk': (0x80000000, 0x2000000, 0x1000)}


def checked(test, message):
    if not test:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def wait_for(get, predicate, timeout, message):
    deadline = time.monotonic() + timeout
    while True:
        value = get()
        if predicate(value):
            return value
        if time.monotonic() >= deadline:
            raise RuntimeError(f'{message}: {value!s:.600}')
        time.sleep(.05)


def elf_contents(path):
    from elftools.elf.elffile import ELFFile
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        checked(elf.elfclass == 32 and elf.little_endian, f'Expected little-endian ELF32: {path}')
        segments = [(int(seg['p_paddr']), seg.data(), int(seg['p_flags']))
                    for seg in elf.iter_segments() if seg['p_type'] == 'PT_LOAD' and seg['p_filesz']]
        return elf['e_machine'], segments


def verify_clock(clock, requested):
    actual = clock['actual_link_Hz']
    checked(abs(actual - requested) <= max(10, requested * 0.001),
            f'Actual link {actual:.3f} Hz differs from expected {requested} Hz')
    return clock


def verify_baseline_rates(board, mem, *, etm=False, heartbeat):
    # The retained CDC fixtures publish the configured core clock; the
    # production ETM capture performs the independent RCC clock readback.
    hz = mem.word(heartbeat - 8)
    expected = 48_000_000 if board == 'f103ze' else 60_000_000 if etm else 480_000_000
    if hz != expected:
        raise Pending(f'Target fixture clock is {hz} Hz, expected {expected} Hz')
    return {'targetSysclkHz': hz}


def verify_h743_viewer_rates(mem):
    """Qualify the H743 Viewer RAM workload from live HSE/PLL1 and RCC."""
    from target_snapshot import snapshot

    registers = snapshot(mem)['registers']
    def register(address):
        return int(registers[hex(address)], 16)

    control = register(0x58024400)
    system = register(0x58024410)
    domain = register(0x58024418)
    source = register(0x58024428)
    pll = register(0x5802442c)
    divider = register(0x58024430)
    m = source >> 4 & 63
    # This board has a 25 MHz HSE. Qualify the integer PLL1P path;
    # neither an unready oscillator nor fractional PLL can use this check.
    ready = (1 << 17) | (1 << 25)
    if (control & ready != ready or (system >> 3) & 7 != 3 or source & 3 != 2
            or not m or not pll & (1 << 16) or pll & 1):
        raise Pending('H743 Viewer requires the qualified 25 MHz HSE / integer PLL1P clock')
    n, p = (divider & 0x1ff) + 1, ((divider >> 9) & 127) + 1
    bus_dividers = (1,) * 8 + (2, 4, 8, 16, 64, 128, 256, 512)
    cpu_divisor = m * p * bus_dividers[domain >> 8 & 15]
    hclk_divisor = cpu_divisor * bus_dividers[domain & 15]
    source_hz = 25_000_000 * n
    if source_hz != cpu_divisor * 480_000_000 or source_hz != hclk_divisor * 240_000_000:
        raise Pending(f'H743 Viewer clock is CPU {source_hz/cpu_divisor:g} Hz, HCLK '
                      f'{source_hz/hclk_divisor:g} Hz; expected 480/240 MHz')
    return dict(targetSysclkHz=480_000_000, targetHclkHz=240_000_000,
                targetClockBasis='H743 25 MHz HSE and live RCC PLL1P/D1 readback')


class Target:
    def __init__(self, args):
        self.args = args
        self.rv = args.board == 'hpm6800evk'
        self.uncertain = None

    @contextmanager
    def link(self, transport=None, hz=10_000_000):
        if self.uncertain:
            raise Unsafe(self.uncertain)
        import usb.util
        from tools.dap_pipeline_bench import open_dap, setup, xfer, drain
        from test_probe_board import Memory
        from probe_build_info import swd_clock_details
        dev, tx, rx = open_dap(self.args.serial)
        try:
            transport = transport or ('jtag' if self.rv else 'swd')
            if self.rv:
                from benchmark_hpm5301 import setup as setup_rv, clock
                from riscv_target import RiscvTarget
                from validate_hpm6800_performance import SramMemory
                drain(rx)
                setup_rv(tx, rx, hz, connect=True)
                target = RiscvTarget(tx, rx)
                target.active()
                setup_rv(tx, rx, hz)
                mem = SramMemory(tx, rx)
                info = clock(tx, rx)
                info['actual_link_Hz'] = info['actual_TCK_Hz']
                info['tap'] = '0x1000563d'
            else:
                identity = setup(tx, rx, hz // 1000, transport=transport, speed_hz=hz)
                mem = Memory(tx, rx)
                diag = xfer(tx, rx, [0x80, 255])
                fclk, cfg = struct.unpack_from('<II', diag, 4)
                info = dict(FCLK_Hz=fclk, cfg=hex(cfg),
                            actual_link_Hz=swd_clock_details(fclk, cfg)['SWCLK_Hz'],
                            frequencyBasis='probe PLL/divider register report')
                info['tap' if transport == 'jtag' else 'dpidr'] = hex(
                    int.from_bytes(identity[2 if transport == 'jtag' else 3:][:4], 'little'))
                target = None
            yield dev, mem, target, info
        finally:
            try:
                checked(xfer(tx, rx, [3]) == b'\x03\x00', 'Native DAP disconnect failed')
            finally:
                usb.util.dispose_resources(dev)

    def state(self, mem, target):
        if self.rv:
            from validate_hpm6800_performance import target_clocks
            status = target.dmi(0x11)
            checked(bool(status & (1 << 9)) != bool(status & (1 << 10)), 'Uncertain hart state')
            return dict(halted=bool(status & (1 << 9)), clock=target_clocks(target), dmstatus=hex(status))
        from target_snapshot import snapshot
        clock = snapshot(mem)
        expected_part = 0xc27 if self.args.board == 'h743' else 0xc23
        expected_device = 0x450 if self.args.board == 'h743' else 0x414
        checked(int(clock['cpuid'], 0) >> 4 & 0xfff == expected_part and
                int(clock['device'], 0) & 0xfff == expected_device, f'Wrong target: {clock}')
        status = mem.word(DHCSR)
        return dict(halted=bool(status & (1 << 17)), clock=clock, dhcsr=status,
                    ccr=hex(mem.word(0xe000ed14)))

    def prepare_openocd(self, transport):
        if self.rv or transport != 'jtag':
            return
        if self.uncertain:
            raise Unsafe(self.uncertain)
        from tools.dap_pipeline_bench import prepare_arm_jtag
        prepare_arm_jtag(self.args.serial)

    def f103_reset_application(self, heartbeat):
        from target_snapshot import same_clock_configuration
        with self.link('swd', hz=1_000_000) as (_, mem, target, _):
            before = self.state(mem, target)
            demcr = mem.word(DEMCR)
            fpb = self.fpb_snapshot(mem)
            checked(not before['halted'] and not demcr & 1, 'Expected a running F103 without reset vector catch')
            checked(not (fpb[0] & 1 and any(fpb[i] & 1 for i in range(8, len(fpb), 4))),
                    'An active FPB comparator could halt the application at startup')
            old_tick = mem.word(heartbeat)

            def pins(value, mask):
                reply = mem.transfer([0x10, value, mask, 0, 0, 0, 0])
                checked(len(reply) == 2 and reply[0] == 0x10, 'Invalid DAP_SWJ_Pins response')
                return reply[1]

            nrst = 0x80
            checked(pins(0, 0) & nrst, 'J7 NRST is low before the pulse')
            # Reading DHCSR clears the old sticky reset indication.
            checked(not mem.word(DHCSR) & S_RESET_ST, 'Could not clear the previous reset indication')
            try:
                asserted = pins(0, nrst)
                checked(not asserted & nrst, 'J7 did not assert NRST')
                time.sleep(.045)
            finally:
                try:
                    released = pins(nrst, nrst)
                    checked(released & nrst, 'J7 did not release NRST')
                except (Exception, KeyboardInterrupt) as error:
                    self.uncertain = f'J7 NRST release unconfirmed: {error!r}'
                    raise Unsafe(self.uncertain) from error
            reset_status = mem.word(DHCSR)
            checked(reset_status & S_RESET_ST, 'J7 NRST caused no fresh core reset indication')
            first_tick = mem.word(heartbeat)
            ticks = [first_tick]

            def advances(value):
                # Ignore the stale pre-startup RAM value when startup clears BSS.
                elapsed_ticks = (value - ticks[-1]) & 0xffffffff
                if 0 < elapsed_ticks < 0x80000000:
                    ticks.append(value)
                elif value != ticks[-1]:
                    ticks[:] = [value]
                return len(ticks) == 3

            wait_for(lambda: mem.word(heartbeat), advances, 4,
                     'Restored F103 application heartbeat did not advance after NRST')
            after = self.state(mem, target)
            checked(not after['halted'] and same_clock_configuration(before['clock'], after['clock'])
                    and before['ccr'] == after['ccr'], 'Unexpected F103 run, clock or cache state after reboot')
            checked(mem.word(DEMCR) == demcr and self.fpb_snapshot(mem) == fpb,
                    'F103 debug configuration changed across NRST')
        return dict(method='J7 NRST', assertedPins=hex(asserted), releasedPins=hex(released),
                    resetDhcsr=hex(reset_status),
                    heartbeat=dict(address=hex(heartbeat), beforeReset=old_tick, firstAfterReset=first_tick,
                                   advancing=ticks, before=ticks[0], after=ticks[-1]))

    def halt(self, mem, target):
        if self.rv:
            target.halt()
        else:
            mem.write_word(DHCSR, 0xa05f0003)
            wait_for(lambda: mem.word(DHCSR), lambda status: status & (1 << 17), 2, 'Halt not confirmed')

    def restore_state(self, mem, target, saved):
        from target_snapshot import same_clock_configuration
        current = self.state(mem, target)
        checked((current['clock'] == saved['clock'] if self.rv else
                 same_clock_configuration(saved['clock'], current['clock'])), 'Target clocks changed')
        if not self.rv:
            checked(current['ccr'] == saved['ccr'], 'Target cache control changed')
        if self.rv:
            if saved['halted']:
                target.halt()
            else:
                target.resume()
        else:
            mem.write_word(DHCSR, 0xa05f0000 | (saved['dhcsr'] & 0x2f))
        current = self.state(mem, target)
        checked(current['halted'] == saved['halted'], 'Original run/halt state was not restored')
        return current

    def registers(self, mem, target):
        if self.rv:
            return {reg: target.register(reg) for reg in RV_REGISTERS}
        from benchmark_rtt_forward import core_read
        return {reg: core_read(mem, reg) for reg in ARM_REGISTERS}

    def restore_registers(self, mem, target, registers):
        from benchmark_rtt_forward import core_write
        read_now = self.registers(mem, target)
        for reg, value in registers.items():
            mask = ~0x1c0 if self.rv and reg == 0x7b0 else 0xffffffff
            if read_now[reg] & mask != value & mask:
                if self.rv:
                    target.register(reg, value)
                else:
                    core_write(mem, reg, value)
        after = self.registers(mem, target)
        for reg, value in registers.items():
            mask = ~0x1c0 if self.rv and reg == 0x7b0 else 0xffffffff
            checked(after[reg] & mask == value & mask, f'Register restore failed at {reg:#x}')

    def fpb_snapshot(self, mem):
        ctrl = mem.word(FPB)
        comparators = ((ctrl >> 4) & 15) | ((ctrl >> 8) & 0x70)
        comparators += (ctrl >> 8) & 15
        checked(comparators <= 128, 'Unexpected FPB comparator count')
        return mem.read(FPB, 8 + 4 * comparators)

    def fpb_restore(self, mem, before):
        if mem.read(FPB, len(before)) != before:
            mem.write_word(FPB, 2)
            mem.write(FPB + 4, before[4:])
            mem.write_word(FPB, 2 | (before[0] & 1))
        checked(mem.read(FPB, len(before)) == before, 'FPB comparator/control restore failed')

    def trigger_snapshot(self, target):
        selected = target.register(0x7a0)
        slots = []
        try:
            for index in range(16):
                target.register(0x7a0, index)
                if target.register(0x7a0) != index:
                    break
                slots.append((target.register(0x7a1), target.register(0x7a2)))
            else:
                raise Pending('RISC-V trigger inventory exceeds the qualified range')
        finally:
            try:
                self.select_trigger(target, selected)
            except (Exception, KeyboardInterrupt) as error:
                self.uncertain = f'RISC-V tselect restoration unconfirmed: {error!r}'
                raise Unsafe(self.uncertain) from error
        return selected, slots

    @staticmethod
    def select_trigger(target, selected):
        target.register(0x7a0, selected)
        checked(target.register(0x7a0) == selected, 'RISC-V tselect restore was not confirmed')

    def restore_triggers(self, target, before):
        selected, slots = before
        _, current = self.trigger_snapshot(target)
        try:
            for index, ((control, address), now) in enumerate(zip(slots, current, strict=True)):
                if (control, address) == now:
                    continue
                # Only an inactive address-match trigger is in this fixture's
                # write set. Keep it disabled while restoring its address.
                checked(control >> 28 in (2, 6) and not control & 7, 'Unexpected RISC-V trigger change')
                self.select_trigger(target, index)
                target.register(0x7a1, control)
                checked(target.register(0x7a1) == control, 'RISC-V trigger disable unconfirmed')
                target.register(0x7a2, address)
        finally:
            self.select_trigger(target, selected)
        checked(self.trigger_snapshot(target) == before, 'RISC-V trigger restore failed')

    @contextmanager
    def live_debug(self, folder, before_restore):
        """Keep the application's advanced PC, stack and RAM coherent."""
        folder.mkdir()
        saved = breakpoint_state = None
        step_before = None
        halt_attempted = False
        try:
            with self.link() as (_, mem, target, _):
                saved = self.state(mem, target)
                if saved['halted']:
                    raise Pending('Live debug requires an initially running application')
                halt_attempted = True
                self.halt(mem, target)
                if self.rv:
                    step_before = target.register(RV_DCSR) & RV_DCSR_STEP
                    snapshot = self.trigger_snapshot(target)
                    if any(control >> 28 not in (0, 2, 6, 15) or
                           control >> 28 in (2, 6) and control & 7 for control, _ in snapshot[1]):
                        raise Pending('An existing or unsupported RISC-V trigger is configured')
                    breakpoint_state = snapshot
                else:
                    snapshot = self.fpb_snapshot(mem)
                    if any(item[0] & 1 for item in struct.iter_unpack('<I', snapshot[8:])):
                        raise Pending('An existing FPB breakpoint is configured')
                    breakpoint_state = snapshot
            write_json(folder / 'before.json', dict(state=saved,
                breakpoints=breakpoint_state if self.rv else breakpoint_state.hex(),
                dcsrStep=bool(step_before) if self.rv else None))
            yield
        finally:
            if halt_attempted:
                try:
                    before_restore()
                    with self.link() as (_, mem, target, _):
                        self.halt(mem, target)
                        if breakpoint_state is not None:
                            if self.rv:
                                self.restore_triggers(target, breakpoint_state)
                            else:
                                self.fpb_restore(mem, breakpoint_state)
                        if self.rv and step_before is not None:
                            # OpenOCD may leave step set after an instruction
                            # step. A raw DM resume would then halt after one
                            # more instruction instead of restoring execution.
                            dcsr = target.register(RV_DCSR)
                            if dcsr & RV_DCSR_STEP != step_before:
                                target.register(RV_DCSR, (dcsr & ~RV_DCSR_STEP) | step_before)
                            checked(target.register(RV_DCSR) & RV_DCSR_STEP == step_before,
                                    'RISC-V DCSR.step restoration not confirmed')
                        after = self.restore_state(mem, target, saved)
                    write_json(folder / 'restored.json', dict(state=after, runStateRestored=True,
                        breakpointsRestored=breakpoint_state is not None, ramRestored=None,
                        registersRestored=None, applicationProgressPreserved=True,
                        dcsrStepRestored=step_before is not None))
                except (Exception, KeyboardInterrupt) as error:
                    self.uncertain = f'Live debug restoration unconfirmed at {folder}: {error!r}'
                    raise Unsafe(self.uncertain) from error

    @contextmanager
    def memory_fixture(self, folder, regions, setup=None, capture_registers=False, keep_halted=False,
                       before_restore=None):
        folder.mkdir()
        saved = registers = fpb = None
        records = []
        try:
            with self.link() as (_, mem, target, _):
                saved = self.state(mem, target)
                self.halt(mem, target)
                if capture_registers:
                    registers = self.registers(mem, target)
                    if not self.rv:
                        fpb = self.fpb_snapshot(mem)
                        (folder / 'fpb.private.bin').write_bytes(fpb)
                for address, length in regions:
                    first = mem.read(address, length)
                    checked(first == mem.read(address, length), f'Unstable RAM backup at {address:#x}')
                    name = f'ram-{address:08x}.private.bin'
                    (folder / name).write_bytes(first)
                    records.append((address, first))
                write_json(folder / 'backup.json', dict(state=saved, registers=registers,
                    regions=[dict(address=address, bytes=len(data), sha256=sha(data)) for address, data in records]))
                if setup:
                    setup(mem, target, saved)
                elif not keep_halted:
                    self.restore_state(mem, target, saved)
            yield saved
        finally:
            if saved is not None:
                try:
                    if before_restore:
                        before_restore()
                    with self.link() as (_, mem, target, _):
                        self.halt(mem, target)
                        for address, data in records:
                            if mem.read(address, len(data)) != data:
                                mem.write(address, data)
                            checked(mem.read(address, len(data)) == data, f'RAM restore failed at {address:#x}')
                        if registers:
                            self.restore_registers(mem, target, registers)
                        if fpb is not None:
                            self.fpb_restore(mem, fpb)
                        after = self.restore_state(mem, target, saved)
                    write_json(folder / 'restored.json', dict(state=after, ramRestored=True if records else None,
                        registersRestored=bool(registers), fpbRestored=fpb is not None))
                except (Exception, KeyboardInterrupt) as error:
                    self.uncertain = f'Target RAM/register restoration unconfirmed at {folder}: {error!r}'
                    raise Unsafe(self.uncertain) from error

    def compile_producer(self, folder):
        folder.mkdir()
        base = RTT_BASE[self.args.board]
        if self.rv:
            compiler = self.args.rv_gcc or RV_GCC
            source = ROOT / 'firmware/target/hpm6800evk/performance/rtt-ram/producer.S'
            flags = ['-march=rv32imac_zicsr_zifencei', '-mabi=ilp32', '-Wl,-Ttext=0x10000']
            maximum = 256
        else:
            compiler = self.args.arm_gcc or shutil.which('arm-none-eabi-gcc')
            source = ROOT / 'tools/fixtures/target/probe_rtt_ram.S'
            flags = ['-mcpu=cortex-m3', '-mthumb', f'-Wl,-Ttext={base:#x}',
                     f'-Wl,--defsym,_SEGGER_RTT={base + 0x200:#x}',
                     f'-Wa,--defsym,FIXTURE_BASE={base:#x}']
            maximum = 512
        if not compiler or not Path(compiler).is_file():
            raise Pending('RAM RTT producer compiler missing; see --arm-gcc / --rv-gcc')
        compiler = Path(compiler).resolve()
        objcopy = compiler.with_name(compiler.name.replace('gcc', 'objcopy'))
        elf, binary = folder / 'producer.elf', folder / 'producer.bin'
        with (folder / 'build.log').open('wb') as log:
            for command in ([compiler, *flags, '-nostdlib', '-Wl,-e,producer', source, '-o', elf],
                            [objcopy, '-O', 'binary', elf, binary]):
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=45)
        code = binary.read_bytes()
        checked(0 < len(code) < maximum, 'RTT RAM producer exceeds its private code window')
        return elf, code
