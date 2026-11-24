"""Versioned Web and native checks driven by the board acceptance runner."""

import base64
from contextlib import contextmanager
import csv
import io
import json
from pathlib import Path
import random
import re
import secrets
import signal
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

from toolbox import pack_file
from tools.board_acceptance_target import (DHCSR, FLASH, RTT_BASE, RV_CODE, SRAM, Target,
                                           checked, elf_contents, sha, verify_baseline_rates, verify_clock,
                                           verify_h743_viewer_rates, wait_for)
from tools.f103_stream_acceptance import symbol
from tools.run_board_acceptance import Pending, ROOT, Unsafe, digest, write_json
from tools.validate_hpm6800_web import Web, redacted

CHIPS = {'f103ze': 'stm32f103', 'h743': 'stm32h7', 'hpm6800evk': 'hpm6800evk'}
BREAKPOINTS = {'f103ze': 'cdc_poll', 'h743': 'HAL_GetTick', 'hpm6800evk': 'engine_leaf'}
HEARTBEAT = {'f103ze': ('g_trace', 12), 'h743': ('g_trace', 12), 'hpm6800evk': ('g_ticks', 0)}
SCOPE_VALUES = tuple(0x68002000 + n * 0x10203 for n in range(8))
RTT_DOWN = bytes.fromhex('00a5ff31320a8055')
SCOPE_PERIODS = {('f103ze', 'swd'): (48, 192), ('h743', 'swd'): (48, 238),
                 ('hpm6800evk', 'jtag'): (240, 1012)}
# The RAM and QSPI release directories currently ship the same routed PL.
# Its existing read-only capability registers identify the qualified profile.
J7_PL_SHA256 = 'dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6'
J7_PL_REGISTERS = ((0x4001004c, 0x4450007f), (0x40030048, 0x30f),
                   (0x40030050, 0x454c4431), (0x40040000, 0x45444d31))
JTAG_TIMING = 0x40010098


class AcceptanceWeb(Web):
    def __init__(self, args, target):
        super().__init__(args)
        self.target = target

    def call(self, payload):
        if self.target.uncertain:
            raise Unsafe(self.target.uncertain)
        started = time.perf_counter()
        try:
            result = self.client.request(payload)
        except Exception as error:
            if '操作可能仍在执行' in str(error) or '是否已排队未知' in str(error):
                self.target.uncertain = f'Browser operation state is uncertain: {error}'
                raise Unsafe(self.target.uncertain) from error
            raise
        except KeyboardInterrupt:
            self.target.uncertain = 'Interrupted while a browser request was in flight'
            raise
        row = dict(request=redacted(payload), result=redacted(result), seconds=time.perf_counter()-started)
        with (self.out / 'steps.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.client.http('ack/' + result['job'], {})
        if not result.get('ok'):
            raise RuntimeError(result.get('error') or str(result))
        value = result.get('value')
        if isinstance(value, dict) and value.get('returned'):
            checked(not value.get('errors'), f'Browser errors: {value["errors"]}')
            return value.get('value')
        return value


def b64(data):
    return {'$base64': base64.b64encode(data).decode('ascii')}


@contextmanager
def defer_interrupt():
    """Latch Ctrl+C during a bounded writer/rollback critical section."""
    interrupted = [False]

    def latch(_signal, _frame):
        interrupted[0] = True
        if getattr(previous, '_board_acceptance_interrupt', False):
            previous(_signal, _frame)

    latch._board_acceptance_interrupt = True
    previous = signal.signal(signal.SIGINT, latch)
    try:
        yield interrupted
    finally:
        signal.signal(signal.SIGINT, previous)


def read_flash_sectors(text):
    """Parse the native OpenOCD geometry saved before admitting a writer."""
    bank = None
    sectors = []
    for line in text.splitlines():
        header = re.search(r'^#\d+\s*:.*\bat\s+(0x[0-9a-f]+),\s*size\s+(0x[0-9a-f]+)', line, re.I)
        if header:
            bank = int(header[1], 16)
            continue
        row = re.search(r'^\s*#\s*\d+:\s*(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\s', line, re.I)
        if row and bank is not None:
            start, size = map(lambda word: int(word, 16), row.groups())
            # OpenOCD prints offsets relative to the bank.
            sectors.append((bank + start, size))
    return sectors


def sequence(data, first=0):
    import numpy as np
    checked(len(data) >= 8 and len(data) % 4 == 0, f'Invalid RTT sequence length: {len(data)}')
    words = np.frombuffer(data, dtype='<u4')
    checked(first is None or int(words[0]) == first, f'Unexpected first RTT sequence: {int(words[0])}')
    checked(bool(np.all(np.diff(words) == 1)), 'RTT sequence gap, duplicate or misalignment')
    return dict(bytes=len(data), first=int(words[0]), last=int(words[-1]), words=len(words))


def capture_quality(summary):
    metrics = summary.get('probeMetrics') or {}
    produced, skipped = metrics.get('produced', 0), metrics.get('skipped', 0)
    checked(summary.get('sampleSource') == 'probe-hss' and summary['definitionReceived'] and produced > 0,
            'Scope did not prove real hardware acquisition')
    checked(not any(summary.get(key) for key in ('lostGap', 'lostUsb', 'readErrors', 'metricsError')),
            f'Scope integrity counters: {summary}')
    checked(summary.get('tailCountDelta') == 0 and summary.get('receivedSamples') == produced,
            'Scope STOP count differs from received samples')
    return skipped / (produced + skipped)


def jsp_data(buffer, address, channels, clock, timestamps=None):
    import numpy as np
    checked(len(buffer) >= 1024 and len(buffer) % 512 == 0, 'Truncated JSP')
    expected = np.array(SCOPE_VALUES[:channels], dtype='<u4')
    groups, previous_seq, first_tick, previous_tick, period = 0, None, None, None, None
    protocol = None
    previous_frame_tick = None
    wrap_ticks = 0
    for offset in range(0, len(buffer), 512):
        packet = memoryview(buffer)[offset:offset+512]
        magic, version, kind, seq, tick, count, length = struct.unpack_from('<HBBIIHH', packet)
        checked(magic == 0x4a53 and version in (1, 2) and protocol in (None, version), 'Invalid JSP protocol')
        protocol = version
        unit_ticks = 24 if version == 1 else 1
        tick *= unit_ticks
        checked(previous_seq is None or seq == (previous_seq+1) & 0xffffffff, 'JSP frame sequence discontinuity')
        previous_seq = seq
        if kind == 1:
            rate, period = struct.unpack_from('<II', packet, 16)
            period *= unit_ticks
            checked(offset == 0 and abs(rate-clock) <= clock*.001 and packet[26] == channels and period > 0,
                    'Scope DEF did not confirm the requested link and channels')
            for index in range(channels):
                actual, width = struct.unpack_from('<IB', packet, 28+index*8)
                checked(actual == address + index*4 and width == 4, 'Scope DEF variable mismatch')
        elif kind == 2:
            checked(period is not None and count > 0 and length == count*channels*4 and length <= 496,
                    'JSP DATA layout or missing DEF')
            values = np.frombuffer(packet[16:16+length], dtype='<u4').reshape(count, channels)
            checked(bool(np.all(values == expected)), 'JSP fixture value mismatch')
            if previous_frame_tick is not None and tick < previous_frame_tick:
                checked(previous_frame_tick - tick > (1 << 31) * unit_ticks, 'JSP frame timestamp moved backwards')
                wrap_ticks += (1 << 32) * unit_ticks
            previous_frame_tick = tick
            tick += wrap_ticks
            if first_tick is None:
                first_tick = tick
            else:
                checked(tick > previous_tick, 'JSP sample timestamps did not advance')
            previous_tick = tick + (count-1)*period
            if timestamps is not None:
                timestamps.extend(tick + sample*period for sample in range(count))
            groups += count
    checked(groups > 0, 'JSP has no complete groups')
    return groups, first_tick, previous_tick, period


class BoardAcceptance:
    def __init__(self, args, report):
        self.args = args
        self.report = report
        self.target = Target(args)
        self.rv = self.target.rv
        self.chip = CHIPS[args.board]
        self.web = None
        self.case = None
        self.physical = None
        self.cable_serial = None

    def preflight(self):
        from probe_flash import Session
        from zynq_memory import PhysicalMemory
        self.web = AcceptanceWeb(SimpleNamespace(runtime=self.args.runtime, timeout=300,
                                                 out=self.report.folder / 'web'), self.target)
        self.runtime = json.loads((self.args.runtime / 'toolbox-runtime.json').read_text(encoding='utf-8'))
        checked(self.runtime.get('nativeProbe'), 'Use a dedicated toolbox serve --native-probe session')
        pair = self.runtime.get('nativeCapture', {})
        for key, path in [('bitSha256', self.args.bit), ('elfSha256', self.args.zynq_elf)]:
            checked(pair.get(key) == digest(path)['sha256'], f'Runtime probe pair mismatch: {key}')
        if pair['bitSha256'] != J7_PL_SHA256:
            raise Pending('Declared bit has no qualified live PL profile for board.accept')
        checked(self.web.call({'action': 'ping'}).get('ready'), 'Browser worker not ready')
        self.probe_identity()
        inventory = self.cable_inventory()
        if self.args.jtag_cable_serial:
            inventory = [serial for serial in inventory if serial == self.args.jtag_cable_serial]
        if len(inventory) != 1:
            raise Pending('Select one J7 XSCT cable with --jtag-cable-serial')
        self.cable_serial = inventory[0]
        physical_dir = self.report.folder / 'physical'
        physical_dir.mkdir()
        self.physical = PhysicalMemory(Session(physical_dir, self.args.sdk, 'tcp:127.0.0.1:3121',
                                               cable_serial=self.cable_serial), cable_serial=self.cable_serial)
        checked(self.check_idle(), 'Probe not idle')
        identity = self.verify_live_probe()
        write_json(self.report.folder / 'probe-identity.json', identity)
        with (self.report.folder / 'ocm.log').open('wb') as log:
            subprocess.run([sys.executable, str(ROOT / 'tools/verify_probe_ocm_code.py'),
                            '--elf', self.args.zynq_elf.resolve(), '--sdk', self.args.sdk,
                            '--cable-serial', self.cable_serial,
                            '--out-dir', self.report.folder / 'ocm'],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        with self.target.link() as (_, mem, chip, clock):
            state = self.target.state(mem, chip)
        for page in ('flash', 'dbg', 'rtt', 'rttcdc', 'scope'):
            self.web.save(f'{page}-api.json', self.web.page(page, 'describe'))
        version = self.web.page('dbg', 'read', selector='#web-build-info')['text']
        return dict(probe=self.probe_identity(), target=state, clock=clock, ocm='ocm/result.json',
                    usbAp0Identity=identity,
                    workbenchBuild=version)

    def cable_inventory(self):
        path = self.report.folder / 'xsct-inventory.tcl'
        path.write_text('connect -url tcp:127.0.0.1:3121\n'
                        'set cpus [targets -target-properties -filter {name =~ "ARM Cortex-A9 MPCore #0*"}]\n'
                        'foreach cpu $cpus {if {[dict exists $cpu jtag_cable_serial]} {'
                        'puts "ACCEPT_CABLE [dict get $cpu jtag_cable_serial]"}}\n'
                        'disconnect\nexit\n', encoding='ascii')
        result = subprocess.run([sys.executable, ROOT / 'tools/run_xsct.py', path, '--sdk', self.args.sdk],
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
        (self.report.folder / 'xsct-inventory.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        checked(result.returncode == 0, 'XSCT inventory failed')
        return re.findall(r'^ACCEPT_CABLE ([A-Za-z0-9_.:-]+)\s*$', result.stdout, re.M)

    def verify_live_probe(self):
        from tools.dap_pipeline_bench import drain, open_dap, xfer
        import usb.util
        registers = {}
        for address, expected in J7_PL_REGISTERS:
            value = self.physical.read_words(address)[0]
            checked(value == expected, f'Unexpected live PL register {address:#x}: {value:#x}')
            registers[hex(address)] = hex(value)
        dev, tx, rx = open_dap(self.args.serial)
        try:
            drain(rx)
            def timing(value):
                reply = xfer(tx, rx, [0x89, value])
                checked(len(reply) == 15 and reply[:2] == b'\x89\x00', 'USB probe JTAG timing query failed')
                return reply[2]
            original = timing(255)
            checked(original in (0, 1, 16, 17) and self.physical.read_words(JTAG_TIMING)[0] & 17 == original,
                    'USB and AP0 JTAG timing initially differ')
            choices = [value for value in (0, 1, 16, 17) if value != original]
            challenge = secrets.SystemRandom().sample(choices, len(choices))
            # Change only the idle probe's sampling mode. No SWJ connect,
            # target transaction, probe reset or image load is involved.
            with defer_interrupt() as interrupted:
                try:
                    for value in challenge:
                        checked(timing(value) == value and self.physical.read_words(JTAG_TIMING)[0] & 17 == value,
                                'Selected USB probe and XSCT cable did not track the same JTAG timing change')
                finally:
                    try:
                        checked(timing(original) == original and timing(255) == original,
                                'USB probe JTAG timing readback differs')
                    except Exception as error:
                        self.target.uncertain = f'USB probe sampling mode restore unconfirmed: {error!r}'
                        raise Unsafe(self.target.uncertain) from error
                checked(self.physical.read_words(JTAG_TIMING)[0] & 17 == original,
                        'AP0 JTAG timing does not match restored USB sampling mode')
            if interrupted[0]:
                raise KeyboardInterrupt
            return dict(usbSerial=self.args.serial, cableSerial=self.cable_serial, challenge=challenge,
                        originalJtagTiming=original, restored=True, livePlRegisters=registers,
                        declaredBitSha256=J7_PL_SHA256, plVerification='qualified live register profile')
        finally:
            usb.util.dispose_resources(dev)

    def probe_identity(self):
        usb = self.web.client.native('usb', 'list', {})['value']
        hid = self.web.client.native('hid', 'list', {})['value']
        for key, rows in [('USB', usb), ('HID', hid)]:
            checked(len(rows) == 1 and rows[0].get('serialNumber') == self.args.serial,
                    f'{key} does not identify only J7 {self.args.serial}')
        return dict(serial=self.args.serial, usb=usb[0]['productName'], hid=hid[0]['productName'])

    def port(self):
        ports = self.web.client.native('serial', 'list', {})['value']
        eligible = [row['path'] for row in ports if row['serialNumber'] == self.args.serial
                    and (row['usbVendorId'], row['usbProductId']) == (0x0d28, 0x0204)]
        checked(len(eligible) == 1, f'Expected one COM port for J7, found {eligible}')
        return eligible[0]

    def invoke(self, page, method, *args, target='view'):
        return self.web.invoke(page, method, *args, target=target)

    def click(self, page, selector):
        return self.web.page(page, 'click', selector=selector)

    def debug_call(self, method, *args):
        return self.invoke('dbg', method, *args, target='session')

    def check_idle(self):
        self.probe_identity()
        status = self.web.client.native('session', 'status', {})['value']
        checked(not status.get('resources') and not status.get('current') and not status.get('pending')
                and not status.get('transport', {}).get('usbOpen') and not status.get('transport', {}).get('hidOpen'),
                f'Probe session is still occupied: {status}')
        checked(not self.invoke('rttcdc', 'summary')['open'], 'Browser CDC port not closed')
        from probe_stream import Probe
        probe = Probe(self.args.serial, zynq_only=True)
        try:
            streams = {}
            for name, service in [('rtt', 0x31), ('hss', 0x32)]:
                rc, words = probe.action(service, 2)
                checked(not rc and not words[0] & 1, f'{name} still active or unknown: {rc}, {words[0]}')
                streams[name] = words[0]
        finally:
            probe.close()
        # The direct stream checks cover firmware. Check the PL engines too.
        from probe_load import probe_state
        fields = probe_state(self.physical.session, cable_serial=self.cable_serial)
        checked('SWD' in fields and 'CAPTURE' in fields, 'Probe PL not configured')
        return dict(streams=streams, engines=fields)

    def final_state(self):
        health = self.check_idle()
        with self.target.link() as (_, mem, chip, clock):
            final = self.target.state(mem, chip)
        return {'target': final, 'probe': self.probe_identity(), 'clock': clock, **health}

    def read_clock(self):
        from zynq_clock import fclk_hz, PLL_REGISTERS
        from probe_build_info import swd_clock_details
        # Read Zynq physical registers without injecting DAP traffic into a live stream.
        registers = (0xf8000170, 0xf8000108, 0xf8000100, 0xf8000104, 0xf800025c, 0x40010008, 0x40010098,
                     0x40010080)
        reads = ' '.join(f'[physrd -force -value {addr:#x}]' for addr in registers)
        output = self.physical.run(f'puts "ACCEPT_CLOCK {reads}"')
        matched = re.search(r'^ACCEPT_CLOCK ([^\r\n]+)', output, re.M)
        checked(matched, 'No physical clock register readback')
        values = dict(zip(registers, (int(value, 0) for value in matched[1].split()), strict=True))
        control = values[registers[0]]
        cfg = values[0x40010008]
        pll = values[PLL_REGISTERS[(control >> 4) & 3]]
        hz = fclk_hz(control, pll, values[0xf800025c])
        clock = dict(FCLK_Hz=hz, cfg=hex(cfg), jtagSamplingMode=values[0x40010098] & 17,
                     jtagRoute=values[0x40010080],
                     actual_link_Hz=swd_clock_details(hz, cfg)['SWCLK_Hz'],
                     basis='physical MEM-AP0 readback of PLL/divider registers')
        return clock

    def clock(self):
        return verify_clock(self.read_clock(), self.case['requestedHz'])

    def stream_mode(self):
        return 'riscv' if self.rv else 'swd'

    def run(self, case, folder):
        self.probe_identity()
        self.case = case
        if case['feature'] == 'flash' and not self.args.allow_flash:
            raise Pending('Target Flash/reset was not enabled with --allow-flash')
        method = getattr(self, case['feature'].replace('-', '_'))
        if case['feature'] == 'etm':
            return method(folder)
        elf = self.args.target_elf
        expected = self.report.value['files']['targetElf']
        with self.target.link() as (_, mem, _, _):
            target_evidence = self.verify_target_image(mem, elf, expected)
            baseline = {}
            if self.args.board == 'h743' and case['feature'] == 'rtt-viewer':
                baseline = verify_h743_viewer_rates(mem)
            elif not self.rv:
                name, offset = HEARTBEAT[self.args.board]
                heartbeat = symbol(self.args.target_elf, name) + offset
                baseline = verify_baseline_rates(self.args.board, mem, heartbeat=heartbeat)
        result = method(folder)
        return dict(result, **baseline, targetElf=target_evidence)

    def verify_target_image(self, mem, elf, expected):
        checked(digest(elf) == expected, 'Target ELF file changed during acceptance')
        machine, segments = elf_contents(elf)
        checked(machine == ('EM_RISCV' if self.rv else 'EM_ARM'), 'Wrong target ELF architecture')
        origin, size, _ = FLASH[self.args.board]
        checked(any(flags & 1 for _, _, flags in segments) and
                all(origin <= start < start + len(data) <= origin + size for start, data, _ in segments),
                'Target ELF must contain code and only Flash-backed load segments')
        for start, data, _ in segments:
            if mem.read(start, len(data)) != data:
                raise Pending(f'Target Flash load segment differs from the ELF at {start:#x}')
        return dict(expected, verifiedLoadBytes=sum(len(data) for _, data, _ in segments))

    def debug_connect(self, folder):
        self.web.page('dbg', 'show')
        self.web.set('dbg', '#d-cfg-core', '')
        self.web.set('dbg', '#d-backend', 'riscv' if self.rv else 'webusb')
        self.web.set('dbg', '#d-hpm-target' if self.rv else '#d-arm-target', self.chip)
        self.web.set('dbg', '#d-clock', str(self.case['requestedHz'] // 1000))
        self.invoke('dbg', 'loadElfBuffer', dict(pack_file(self.args.target_elf), kind='buffer'),
                    self.args.target_elf.name)
        self.invoke('dbg', 'connect')
        state = self.invoke('dbg', 'summary')
        checked(state['connected'] and state['backend'] != '模拟目标', f'Debug connect failed: {state}')
        self.web.save('debug-session-api.json', self.web.page('dbg', 'describe', target='session'))
        return state

    @contextmanager
    def web_debug(self, folder):
        try:
            state = self.debug_connect(folder)
            yield state
        finally:
            self.close_debug()

    def close_debug(self):
        if self.invoke('dbg', 'summary')['connected']:
            try:
                self.debug_call('bpClear')
            finally:
                self.invoke('dbg', 'disconnect')

    def sram(self, folder):
        addr = SRAM[self.args.board] + 0x3f8
        length = 2048
        payload = random.Random(0x61a3).randbytes(length)
        results = {}
        pipeline = self.case.get('pipeline')
        regions = [(pipeline['address'], pipeline['backupBytes'])] if pipeline else [(addr - 8, length + 16)]
        with self.target.memory_fixture(folder / 'fixture', regions,
                                        capture_registers=True, keep_halted=True):
            with self.target.link(self.case['transport'], self.case['requestedHz']) as (_, mem, chip, clock):
                results['native'] = self.memory_check(addr, payload, mem.read, mem.write)
                results['native']['clock'] = verify_clock(clock, self.case['requestedHz'])
                if pipeline:
                    results['pipeline'] = self.sram_pipeline(folder, mem, chip, pipeline)
            with self.web_debug(folder):
                self.debug_call('halt')
                def read(at, size):
                    return bytes(self.debug_call('memRead', at, size)['$bytes'])
                def write(at, data):
                    self.debug_call('memWrite', at, b64(data))
                clock = self.clock()
                results['web'] = self.memory_check(addr, payload, read, write)
                results['web']['clock'] = clock
                results['web']['targetState'] = 'halted'
        results['comparison'] = {key: results['web'][key] / results['native'][key]
                                 for key in ('readMBps', 'writeMBps')}
        write_json(folder / 'measurements.json', results)
        return results

    def sram_pipeline(self, folder, mem, chip, profile):
        from h743_peak import measure_pipeline
        state = self.target.state(mem, chip)
        checked(state['halted'] and not int(state['ccr'], 0) & (1 << 16),
                'H743 pipelined AXI SRAM comparison requires a halted core with D-cache disabled')
        clock = self.clock()
        historical = {'swd': (4.0494, 3.9894), 'jtag': (3.9771, 2.0076)}
        attempts = []
        for _ in range(2):
            data = measure_pipeline(mem, profile['address'], words=profile['words'], depth=profile['depth'],
                                    loops=profile['loops'], repeats=profile['repeats'], soak_seconds=profile['soakSeconds'])
            comparison = {direction: dict(historicalMBps=reference, deltaPercent=100*(data[direction]['MB_s']/reference-1))
                          for direction, reference in zip(('read','write'),historical[self.case['transport']])}
            attempts.append(dict(data, historicalComparison=comparison))
            write_json(folder/'pipeline-attempts.json', attempts)
            if all(row['deltaPercent'] >= -2 for row in comparison.values()):
                break
        return dict(data, profile=profile, clock=clock, target=state, byteExact=True, attempts=len(attempts),
                    historicalComparison=comparison, historicalVariance=any(row['deltaPercent'] < -2 for row in comparison.values()),
                    historicalSource=('https://github.com/minichao9901/zynqlinkPRO/blob/'
                                      '03b6a1dad8ee62aa7902b6bc37d0f0d9c3c3f451/docs/validation/'
                                      'h743-board-rerun-20261115/README.md'))

    @staticmethod
    def memory_check(addr, payload, read, write):
        from statistics import median
        size = len(payload)
        guard = read(addr - 8, 8), read(addr + size, 8)
        rows = []
        for repeat in range(3):
            data = bytes((byte + repeat) & 255 for byte in payload)
            started = time.perf_counter()
            write(addr, data)
            written = time.perf_counter()
            raw = read(addr, size)
            ended = time.perf_counter()
            checked(raw == data, 'SRAM block readback differs')
            rows.append(dict(writeSeconds=written-started, readSeconds=ended-written))
        for width in (1, 2, 4):
            at = addr + 1
            before = read(at - 1, width + 2)
            value = bytes(range(0xf0, 0xf0 + width))
            write(at, value)
            checked(read(at - 1, width + 2) == before[:1] + value + before[-1:], 'SRAM width/guard mismatch')
        checked(guard == (read(addr - 8, 8), read(addr + size, 8)), 'SRAM guard changed')
        return dict(address=hex(addr), bytes=size, rows=rows, byteExact=True,
                    readMBps=size / median(r['readSeconds'] for r in rows) / 1e6,
                    writeMBps=size / median(r['writeSeconds'] for r in rows) / 1e6)

    def debug(self, folder):
        elf = self.args.target_elf
        entry = symbol(elf, self.args.break_symbol or BREAKPOINTS[self.args.board]) & ~1
        register = 'a0' if self.rv else 'r0'
        _, segments = elf_contents(elf)
        checked(any(flags & 1 and start <= entry < start + len(data) for start, data, flags in segments),
                'Debug breakpoint must belong to verified executable target code')
        with self.target.live_debug(folder / 'fixture', self.check_idle):
            t0 = time.perf_counter()
            with self.web_debug(folder):
                connected = time.perf_counter() - t0
                clock = self.clock()
                t0 = time.perf_counter()
                self.debug_call('halt')
                halted = time.perf_counter() - t0
                # Session is halted already when used with the memory snapshot.
                self.debug_call('run')
                self.debug_call('refresh')
                checked(not self.invoke('dbg', 'summary')['halted'], 'Resume not confirmed')
                self.debug_call('halt')
                pc = self.debug_call('readReg', 'pc')
                t0 = time.perf_counter()
                self.debug_call('step')
                stepped = time.perf_counter() - t0
                self.debug_call('refresh')
                next_pc = self.debug_call('readReg', 'pc')
                checked(self.invoke('dbg', 'summary')['halted'] and pc != next_pc, 'Instruction step not confirmed')
                self.debug_call('bpAdd', entry, 'board acceptance')
                checked(self.invoke('dbg', 'summary')['bps'], 'Hardware breakpoint not registered')
                self.debug_call('cont')
                def refresh():
                    self.debug_call('refresh')
                    return self.invoke('dbg', 'summary')
                state = wait_for(refresh, lambda state: state['halted'], 6, 'Breakpoint not hit')
                checked(state['pc'] & ~1 == entry, 'Wrong hardware breakpoint PC')
                self.debug_call('bpClear')
                checked(not self.invoke('dbg', 'summary')['bps'], 'Breakpoints were not cleared')
                steps = {}
                if self.args.board == 'h743':
                    steps, frames = self.h743_source_steps(elf, refresh)
                elif self.rv:
                    steps, frames = self.hpm_source_steps(elf, refresh)
                else:
                    for method in ('stepInto', 'stepOver', 'stepOut'):
                        before = self.debug_call('readReg', 'pc')
                        outcome = self.debug_call(method)
                        after = self.debug_call('readReg', 'pc')
                        checked(before != after and not any(word in str(outcome) for word in
                                ('没停到', '超时', '还没回到调用者')), f'{method} did not complete: {outcome}')
                        steps[method] = dict(before=before, after=after, outcome=outcome)
                    frames = self.debug_call('backtrace', {'maxFrames': 8})
                checked(frames.get('frames'), 'Debugger returned no backtrace')
                name = 'g_ticks' if self.rv else 'g_trace.loops'
                self.invoke('dbg', 'addWatch', name)
                t0 = time.perf_counter()
                self.invoke('dbg', 'refreshWatch', {'force': True})
                watch_s = time.perf_counter() - t0
                watches = self.invoke('dbg', 'summary')['watch']
                checked(any(row['expr'] == name and not row['error'] and row['value'] is not None
                            for row in watches), 'Watch value not available')
                value = self.debug_call('readReg', register)
        return dict(clock=clock, pc=pc, steppedPc=next_pc, breakpointPc=entry, sourceSteps=steps,
                    backtrace=frames, register=value, connectSeconds=connected, haltSeconds=halted,
                    stepSeconds=stepped, watchSeconds=watch_s)

    @staticmethod
    def source_line_addresses(elf, filename, line):
        from elftools.elf.elffile import ELFFile
        from pathlib import PurePosixPath

        with elf.open('rb') as stream:
            image = ELFFile(stream)
            dwarf = image.get_dwarf_info()
            addresses = set()
            for unit in dwarf.iter_CUs():
                unit_name = unit.get_top_DIE().attributes.get('DW_AT_name')
                if not unit_name or PurePosixPath(unit_name.value.decode().replace('\\', '/')).name != filename:
                    continue
                for row in dwarf.line_program_for_CU(unit).get_entries():
                    if row.state and not row.state.end_sequence and row.state.line == line:
                        addresses.add(row.state.address)
        return addresses

    def h743_source_steps(self, elf, refresh):
        # Use the periodic main-loop call that reaches a returning, non-leaf
        # function. Resolve the instruction from DWARF and verify its target.
        addresses = self.source_line_addresses(elf, 'main.c', 480)
        mark = symbol(elf, 'trace_hook_mark') & ~1
        _, segments = elf_contents(elf)
        calls = set()
        for address in addresses:
            for start, data, flags in segments:
                if not flags & 1 or not start <= address <= start + len(data) - 4:
                    continue
                first, second = struct.unpack_from('<HH', data, address - start)
                if first & 0xf800 != 0xf000 or second & 0xd000 != 0xd000:
                    continue
                sign = (first >> 10) & 1
                i1 = 1 ^ ((second >> 13) & 1) ^ sign
                i2 = 1 ^ ((second >> 11) & 1) ^ sign
                offset = (i1 << 23) | (i2 << 22) | ((first & 0x3ff) << 12) | ((second & 0x7ff) << 1)
                if address + 4 + offset - (sign << 24) == mark:
                    calls.add(address)
        checked(len(calls) == 1, 'H743 Golden must have one verified main.c:480 call to trace_hook_mark')
        call = calls.pop()
        expected_return = call + 4

        self.debug_call('bpAdd', call, 'H743 source call')
        self.debug_call('cont')
        hit = wait_for(refresh, lambda state: state['halted'], 6, 'Source call breakpoint not hit')
        checked(hit['pc'] & ~1 == call, 'Source call stopped at the wrong PC')
        self.debug_call('bpClear')
        stack = self.debug_call('readReg', 'sp')
        into = self.debug_call('stepInto')
        into_pc = self.debug_call('readReg', 'pc') & ~1
        checked(mark <= into_pc < mark + 16 and '单步进入 →' in into and
                self.debug_call('readReg', 'lr') & ~1 == expected_return,
                f'H743 did not step into trace_hook_mark: {into}')
        over = self.debug_call('stepOver')
        over_pc = self.debug_call('readReg', 'pc') & ~1
        checked(into_pc < over_pc < mark + 32 and '单步跳过 →' in over,
                f'H743 did not step over to the next line in trace_hook_mark: {over}')
        frames = self.debug_call('backtrace', {'maxFrames': 8})
        stack_frames = frames.get('frames', [])
        checked(len(stack_frames) >= 2 and stack_frames[0]['name'].startswith('trace_hook_mark')
                and stack_frames[1]['name'].startswith('main') and stack_frames[1]['pc'] & ~1 == expected_return,
                'H743 backtrace does not contain the verified caller')
        out = self.debug_call('stepOut')
        return_pc = self.debug_call('readReg', 'pc') & ~1
        return_sp = self.debug_call('readReg', 'sp')
        checked(return_pc == expected_return and return_sp == stack and '单步跳出 →' in out,
                f'H743 did not return to the caller: {out}')
        return dict(stepInto=dict(before=call, after=into_pc, outcome=into),
                    stepOver=dict(before=into_pc, after=over_pc, outcome=over),
                    stepOut=dict(before=over_pc, after=return_pc, outcome=out, returnSp=return_sp)), frames

    def hpm_source_steps(self, elf, refresh):
        callee = symbol(elf, 'model_checksum')
        _, segments = elf_contents(elf)
        calls = set()
        for address in self.source_line_addresses(elf, 'main.c', 98):
            for start, data, flags in segments:
                if not flags & 1 or not start <= address <= start+len(data)-4:
                    continue
                instruction = struct.unpack_from('<I', data, address-start)[0]
                if instruction & 0xfff != 0x0ef:  # JAL ra, signed PC-relative displacement.
                    continue
                offset = ((instruction >> 21) & 0x3ff) << 1
                offset |= ((instruction >> 20) & 1) << 11 | instruction & 0xff000
                offset -= (instruction >> 31) << 20
                if address+offset == callee:
                    calls.add(address)
        checked(len(calls) == 1, 'HPM baseline must have one verified main.c:98 call to model_checksum')
        call = calls.pop()
        return_address = call+4
        self.debug_call('bpAdd', call, 'HPM source call')
        self.debug_call('cont')
        hit = wait_for(refresh, lambda state: state['halted'], 6, 'HPM source call was not hit')
        checked(hit['pc'] == call, 'HPM source call stopped at the wrong PC')
        self.debug_call('bpClear')
        stack = self.debug_call('readReg', 'sp')
        into = self.debug_call('stepInto')
        into_pc = self.debug_call('readReg', 'pc')
        checked('单步进入 →' in into and into_pc == callee
                and into_pc in self.source_line_addresses(elf, 'model.c', 161)
                and self.debug_call('readReg', 'ra') == return_address,
                f'HPM did not source-step into model_checksum: {into}')
        over = self.debug_call('stepOver')
        over_pc = self.debug_call('readReg', 'pc')
        checked('单步跳过 →' in over and over_pc > into_pc
                and over_pc in self.source_line_addresses(elf, 'model.c', 162),
                f'HPM did not step over to the next model_checksum line: {over}')
        frames = self.debug_call('backtrace', {'maxFrames': 8})
        caller = frames.get('frames', [])
        checked(len(caller) >= 2 and caller[0]['name'].split('+')[0] == 'model_checksum'
                and caller[1]['name'].split('+')[0] == 'main'
                and (caller[1]['pc'], caller[1]['sp']) == (return_address, stack),
                'HPM backtrace did not verify the caller PC and SP')
        out = self.debug_call('stepOut')
        pc = self.debug_call('readReg', 'pc')
        sp = self.debug_call('readReg', 'sp')
        checked('单步跳出 →' in out and (pc, sp) == (return_address, stack),
                f'HPM did not return to the verified caller: {out}')
        return dict(stepInto=dict(before=call, after=into_pc, outcome=into),
                    stepOver=dict(before=into_pc, after=over_pc, outcome=over),
                    stepOut=dict(before=over_pc, after=pc, outcome=out, returnSp=sp)), frames

    def rtt_addresses(self):
        base = RTT_BASE[self.args.board]
        return base, base + 0x200, base + 0x1000, base + (0x5000 if self.rv else 0x4000)

    @contextmanager
    def rtt_fixture(self, folder, *, producer=True, batch=1024):
        base, cb, ring, down = self.rtt_addresses()
        size = 16384 if self.rv else 8192
        elf, code = self.target.compile_producer(folder / 'producer') if producer else (None, None)
        if self.rv and producer:
            regions = [(RV_CODE, 256), (base, 0x8000)]
        else:
            regions = [(base, 0x5200 if self.rv else 0x5000)]

        def setup(mem, chip, saved):
            if producer:
                if self.args.board == 'h743':
                    checked(not int(saved['ccr'], 0) & (1 << 16), 'H743 RTT fixture requires D-cache disabled')
                entry = RV_CODE if self.rv else base
                mem.write(entry, code)
                checked(mem.read(entry, len(code)) == code, 'RTT producer writeback failed')
                if self.rv:
                    mem.write(base, bytes(0x8000))
                    mem.write_word(base + 72, batch)
                    mem.write_word(base + 64, 1)
                elif self.args.board == 'h743':
                    mem.write_word(0xe000ef50, 0)
            control = (struct.pack('<16sII', b'SEGGER RTT', 1, 1) +
                       struct.pack('<6I', 0, ring, size, 0, 0, 0) +
                       struct.pack('<6I', 0, down, 64, 60, 60, 0) + bytes(4))
            mem.write(cb, control)
            mem.write(down, bytes([0x6e]) * 64)
            mem.write(self.scope_address(), struct.pack('<8I', *SCOPE_VALUES))
            if producer and self.rv:
                chip.register(0x7b0, (chip.register(0x7b0) & ~7) | 3)
                chip.register(0x7b1, RV_CODE)
                chip.resume()
                wait_for(lambda: mem.word(base), lambda v: v == 0x48504d50, 2, 'RTT producer did not boot')
            elif producer:
                from benchmark_rtt_forward import core_write
                core_write(mem, 16, 0x01000000)
                core_write(mem, 20, 1)
                core_write(mem, 15, base | 1)
                mem.write_word(DHCSR, 0xa05f0001)
            else:
                self.target.restore_state(mem, chip, saved)

        with self.target.memory_fixture(folder / 'fixture', regions, setup, capture_registers=producer,
                                        before_restore=self.check_idle):
            yield elf

    def viewer_start(self, elf):
        self.web.page('rtt', 'show')
        self.web.set('rtt', '#r-target', 'riscv' if self.rv else 'swd')
        if self.rv:
            self.web.set('flash', '#f-chip', self.chip)
            if not self.web.read('rtt', '#r-use-session-target')['disabled']:
                self.click('rtt', '#r-use-session-target')
        self.web.set('rtt', '#r-usb-clock', str(self.case['requestedHz'] // 1000))
        self.web.set('rtt', '#r-record-auto', False)
        self.web.set('rtt', '#r-poll', '5')
        _, cb, _, _ = self.rtt_addresses()
        checked(self.invoke('rtt', 'loadElfFile', dict(pack_file(elf), kind='file')),
                'Failed to resolve _SEGGER_RTT from probe fixture ELF')
        checked(self.invoke('rtt', 'summary')['elfControlBlock'] == cb, 'Wrong RTT ELF address')
        self.click('rtt', '#r-clear')
        self.invoke('rtt', 'connectProbe')
        return wait_for(lambda: self.invoke('rtt', 'summary'),
                        lambda s: s['connected'] and s['running'] and s['controlBlock'] == cb
                        and s['stats']['bytes'] > 0, 8, 'RTT Viewer has no fresh data')

    def rtt_viewer(self, folder):
        with self.rtt_fixture(folder) as elf:
            try:
                self.viewer_start(elf)
                clock = self.clock()
                first = self.invoke('rtt', 'summary')
                t0 = time.perf_counter()
                time.sleep(3)
                last = self.invoke('rtt', 'summary')
                wall = time.perf_counter() - t0
                checked(last['stats']['bytes'] > first['stats']['bytes'], 'RTT Viewer stopped making progress')
                checked(not last['stats'].get('lost') and not last['stats'].get('corrupt'), 'Viewer loss or corruption')
                wrap_bytes = 16384 if self.rv else 8192
                rate = (last['stats']['bytes'] - first['stats']['bytes']) / wall
                wait_for(lambda: self.invoke('rtt', 'summary'),
                         lambda state: state['bufferedBytes'] > wrap_bytes,
                         8, 'RTT up ring wrap not observed')
                self.invoke('rtt', 'writeDown', 0, b64(RTT_DOWN), target='rtt')
                export = self.invoke('rtt', 'saveRaw')
                raw = self.web.download('rtt', folder / 'viewer.bin')
                continuity = sequence(raw)
                checked(export['bytes'] == len(raw) and not export['truncated'], 'RTT Viewer export incomplete')
                health = self.invoke('rtt', 'summary')['stats']
                checked(not health.get('lost') and not health.get('corrupt'), 'RTT Viewer recorded loss/corruption')
            finally:
                self.invoke('rtt', 'disconnect')
            _, cb, _, down = self.rtt_addresses()
            with self.target.link() as (_, mem, chip, _):
                ring = mem.read(down, 64)
                pointer = mem.word(cb + 60)
                checked(pointer == 4 and ring[60:] + ring[:4] == RTT_DOWN and ring[4:60] == b'n' * 56,
                        'Downlink wrap, WrOff or guard bytes mismatch')
        return dict(clock=clock, throughputBps=rate,
                    seconds=wall, upstream=continuity, downstream=dict(bytes=len(RTT_DOWN), wrOff=pointer),
                    pollingMs=5, displayed=not last['displaySuppressed'], viewerTransport=last.get('transport'))

    def cdc_start(self, ready_bytes=8):
        _, cb, _, _ = self.rtt_addresses()
        self.web.page('rttcdc', 'show')
        self.web.set('rttcdc', '#h-target', self.stream_mode())
        self.web.set('rttcdc', '#h-addr', hex(cb))
        self.web.set('rttcdc', '#h-chan', '0')
        self.web.set('rttcdc', '#c-record-auto', False)
        self.invoke('rttcdc', 'connect', target='hid')
        self.invoke('rttcdc', 'applyTargetType', target='hid')
        self.web.set('rttcdc', '#h-clock', str(self.case['requestedHz']))
        self.invoke('rttcdc', 'refreshPorts')
        port = self.port()
        options = self.web.read('rttcdc', '#c-port')['options']
        chosen = [row['value'] for row in options if re.search(r'(?<!\w)' + re.escape(port) + r'(?!\w)', row['label'], re.I)]
        checked(len(chosen) == 1, 'No unique browser COM matching the J7 serial')
        self.web.set('rttcdc', '#c-port', chosen[0])
        self.invoke('rttcdc', 'connect')
        checked(self.invoke('rttcdc', 'summary')['open'], f'Web COM open failed: {port}')
        self.click('rttcdc', '#c-clear')
        self.click('rttcdc', '#c-statclear')
        started = time.monotonic()
        checked(self.invoke('rttcdc', 'start', target='hid') is not False, 'RTT forward START failed')
        checked(self.invoke('rttcdc', 'summary', target='hid')['connected'], 'RTT control channel did not connect')
        wait_for(lambda: self.invoke('rttcdc', 'summary'),
                 lambda state: state['open'] and state['bytes'] >= ready_bytes, 8, 'RTT forward produced no data')
        self.cdc_start_seconds = time.monotonic() - started
        return port

    def cdc_stop(self):
        state = self.invoke('rttcdc', 'summary', target='hid')
        if not state['connected']:
            return None
        self.invoke('rttcdc', 'stop', target='hid')
        self.invoke('rttcdc', 'refresh', target='hid')
        engine = self.invoke('rttcdc', 'summary', target='hid')
        checked(not engine['running'] and not engine['rdErr'] and not engine['wrErr'], f'RTT STOP failure: {engine}')
        summary = self.invoke('rttcdc', 'summary')
        if summary['open']:
            final = wait_for(lambda: self.invoke('rttcdc', 'summary'),
                             lambda s: s['bytes'] >= engine['moved'], 4, 'Host did not receive the STOP tail')
            checked(final['bytes'] == engine['moved'], f'RTT STOP tail mismatch: {final["bytes"]} vs {engine["moved"]}')
        return engine

    def cdc_close(self):
        try:
            checked(self.invoke('rttcdc', 'disconnect', target='hid') is not False,
                    'RTT HID still disconnecting')
        finally:
            self.invoke('rttcdc', 'close', target='session')

    def rtt_measured_stop(self, seconds):
        # A pending captureWindow owns the normal workbench command slot.
        # The public interrupt path sends the real page STOP while recording
        # is still active, so the export includes the host's post-STOP bytes.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.invoke, 'rttcdc', 'captureWindow',
                                 {'seconds': seconds + 4, 'maxMiB': 32, 'reportProgress': True})
            wait_for(lambda: self.web.page('rttcdc', 'state')['summary'].get('captureWindow'),
                     lambda state: state and state['bytes'] > 0, 2, 'Browser RTT recording never started')
            time.sleep(seconds)
            dispatch = self.web.page('rttcdc', 'interrupt', selector='#h-stop')
            checked(dispatch['dispatched'], 'RTT STOP button did not dispatch')
            window = future.result()
        return window

    def rtt_forward(self, folder):
        rows = []
        # Repeat with the same Web page and a fresh target sequence. The
        # second start exercises reuse of the prior Web/HID/COM session.
        for repeat in range(2):
            run = folder / f'web-{repeat + 1}'
            run.mkdir()
            with self.rtt_fixture(run):
                try:
                    port = self.cdc_start()
                    clock = self.clock()
                    window = self.rtt_measured_stop(3)
                    self.invoke('rttcdc', 'refresh', target='hid')
                    end = self.invoke('rttcdc', 'summary', target='hid')
                    host = self.invoke('rttcdc', 'summary')
                    checked(not end['running'] and not end['rdErr'] and not end['wrErr']
                            and host['bytes'] == end['moved'], 'RTT STOP or host tail unconfirmed')
                    data = self.web.download('rttcdc', run / 'forward.bin')
                    checked(window['complete'] and window['bytes'] == len(data), 'RTT Web recording incomplete')
                    # The window starts after START. Check aligned complete words.
                    alignment = self.sequence_window(data)
                    rows.append(dict(port=port, clock=clock, window=window, sequence=alignment,
                                     startupSeconds=self.cdc_start_seconds,
                                     engine=end, hostTailMatch=True))
                finally:
                    self.cdc_close()
                _, cb, _, _ = self.rtt_addresses()
                with self.target.link() as (_, mem, _, _):
                    wr, rd = struct.unpack('<2I', mem.read(cb + 36, 8))
                    rows[-1]['targetRingPending'] = (wr-rd) % (16384 if self.rv else 8192)
                    rows[-1]['chunk'] = 2048
            write_json(folder / 'web.json', rows)
        boundary = self.cdc_boundaries(folder)
        native = self.native_forward(folder)
        return dict(web=rows, native=native, boundaries=boundary, restartVerified=True,
                    webToNativeThroughputRatio=(sum(row['window']['activeBytesPerSecond'] for row in rows)
                                                / len(rows) / native['throughputBps']))

    @staticmethod
    def sequence_window(data):
        for offset in range(4):
            size = (len(data) - offset) & ~3
            if size <= 8:
                continue
            try:
                return dict(sequence(data[offset:offset + size], None), alignment=offset)
            except RuntimeError:
                continue
        raise RuntimeError('RTT window sequence is discontinuous')

    def cdc_boundaries(self, folder):
        # All bytes of these finite fixtures fit under the browser raw buffer
        # limit. Arm the recording before START and preserve the full session.
        rows = []
        for count in (511, 512, 513):
            run = folder / f'boundary-{count}'
            run.mkdir()
            expected = random.Random(count).randbytes(count)
            with self.rtt_fixture(run, producer=False):
                _, cb, ring, _ = self.rtt_addresses()
                with self.target.link() as (_, mem, chip, _):
                    mem.write(ring, expected)
                    mem.write_word(cb + 36, count)
                    mem.write_word(cb + 40, 0)
                try:
                    self.cdc_start(count)
                    end = self.cdc_stop()
                    self.invoke('rttcdc', 'saveRaw')
                    raw = self.web.download('rttcdc', run / 'forward.bin')
                    checked(end['moved'] == count and raw == expected, f'RTT {count} B boundary/tail mismatch')
                    rows.append(dict(bytes=count, sha256=sha(raw), matched=True))
                finally:
                    self.cdc_close()
            write_json(folder / 'boundaries.json', rows)
        return rows

    def native_forward(self, folder):
        import serial
        from benchmark_rtt_forward import Reader
        from probe_stream import Probe
        target_hz = self.case['requestedHz']
        _, cb, _, _ = self.rtt_addresses()
        fixture = folder / 'native'
        fixture.mkdir()
        port = self.port()
        with self.rtt_fixture(fixture):
            # Install the transport without leaving a DAP owner alongside HID.
            with self.target.link(self.case['transport'], target_hz):
                pass
            probe = Probe(self.args.serial, zynq_only=True)
            try:
                route = 2 if self.case['transport'] == 'jtag' else 1
                checked(probe.action(0x31, 12, bytes([route]))[0] == 0, 'Native RTT transport rejected')
                with serial.Serial(port, 115200, timeout=.025) as com:
                    com.reset_input_buffer()
                    reader = Reader(com)
                    reader.start()
                    try:
                        checked(probe.action(0x31, 7, struct.pack('<IHBB', target_hz, 2048, 0, 0xff))[0] == 0,
                                'Native RTT configuration rejected')
                        checked(probe.action(0x31, 1, struct.pack('<IIB', cb, 0x100, 0))[0] in (0, -100),
                                'Native RTT START rejected')
                        wait_for(lambda: (reader.count, reader.error), lambda x: x[0] > 0 or x[1], 5,
                                 'Native CDC received no bytes')
                        clock = self.clock()
                        t0, start = time.perf_counter(), reader.count
                        time.sleep(3)
                        wall, count = time.perf_counter() - t0, reader.count - start
                    finally:
                        try:
                            def stop():
                                rc, words = probe.action(0x31, 0)
                                checked(rc in (0, -7), f'Native RTT STOP failed: {rc}')
                                return rc, words
                            _, final = wait_for(stop, lambda x: x[0] == 0, 4, 'Native RTT STOP did not finish')
                            wait_for(lambda: (reader.count, reader.error), lambda x: x[0] >= final[3] or x[1],
                                     4, 'Native CDC STOP tail missing')
                        finally:
                            reader.quit.set()
                            reader.join(2)
                    checked(not reader.is_alive() and not reader.error and not reader.pending
                            and reader.count == final[3] and not final[5] and count > 0,
                            f'Native RTT loss/error: {reader.count}, {reader.error}, {final}')
            finally:
                probe.close()
            with self.target.link() as (_, mem, chip, _):
                wr, rd = struct.unpack('<2I', mem.read(cb + 36, 8))
        return dict(port=port, clock=clock, seconds=wall, bytes=count, throughputBps=count/wall,
                    received=reader.count, moved=final[3], sequenceContinuous=True,
                    targetRingPending=(wr-rd) % (16384 if self.rv else 8192), chunk=2048)

    def scope_address(self):
        return RTT_BASE[self.args.board] + (0x5100 if self.rv else 0x4800)

    def scope_start(self, channels, ticks, seconds):
        self.web.page('scope', 'show')
        self.click('scope', '#sc-side-capture-tab')
        self.invoke('scope', 'setMock', False)
        self.web.set('scope', '#sc-target', self.stream_mode())
        self.web.set('scope', '#sc-sampling-path', 'probe')
        self.web.set('scope', '#sc-period', f'{ticks / 24:.6f}')
        self.web.set('scope', '#sc-seconds', str(seconds))
        self.web.set('scope', '#sc-raw', True)
        self.invoke('scope', 'clear')
        self.click('scope', '#sc-varclear')
        for index in range(channels):
            self.invoke('scope', 'toggleVar', dict(name=f'fixture_{index}', addr=self.scope_address() + 4*index,
                                                   scalar='u32', size=4), True)
        self.invoke('scope', 'connectHid', False)
        self.invoke('scope', 'connectUsb', False)
        self.web.set('scope', '#sc-clock', str(self.case['requestedHz'] // 1000))
        self.invoke('scope', 'start')
        return wait_for(lambda: self.invoke('scope', 'summary'),
                        lambda s: s['running'] and s['definitionReceived'] and s['samples'] > 0,
                        5, 'Scope did not receive first DEF and data')

    def scope_stop(self):
        self.invoke('scope', 'stop', 'board acceptance STOP')
        return self.invoke('scope', 'summary')

    def scope_exports(self, folder, channels, summary):
        self.invoke('scope', 'saveRaw')
        data = self.web.download('scope', folder / 'capture.jsp')
        timestamps = []
        samples, first_tick, last_tick, period = jsp_data(data, self.scope_address(), channels,
                                                          self.case['requestedHz'], timestamps)
        checked(samples == summary['receivedSamples'], 'JSP group count differs from device')
        # CSV/export replay is exercised in a short checked point. Long
        # confirmation windows retain every raw frame without a huge CSV.
        self.invoke('scope', 'exportCsv')
        raw_csv = self.web.download('scope', folder / 'capture.csv')
        rows = csv.reader(io.StringIO(raw_csv.decode('utf-8-sig')))
        checked(len(next(rows)) == channels + 1, 'Scope CSV column count mismatch')
        first_stamp = last_stamp = None
        for row, ticks in zip(rows, timestamps, strict=True):
            stamp = float(row[0])
            if first_stamp is None:
                first_stamp = stamp
            expected_time = (ticks - first_tick) / 24
            checked(tuple(map(int, row[1:])) == SCOPE_VALUES[:channels] and
                    (last_stamp is None or stamp > last_stamp) and abs(stamp-first_stamp-expected_time) < 1.1,
                    'Scope CSV data/timestamp mismatch')
            last_stamp = stamp
        checked(last_stamp is not None, 'Scope CSV has no samples')
        self.invoke('scope', 'disconnect')
        self.invoke('scope', 'replayFile', dict(b64(data), kind='file', name='capture.jsp'))
        checked(self.invoke('scope', 'summary')['samples'] == samples, 'Scope JSP replay count mismatch')
        return dict(groups=samples, firstTick=first_tick, lastTick=last_tick, periodTicks=period)

    def jscope(self, folder):
        native = {}
        native_error = None
        if self.case.get('native'):
            try:
                self.native_scope(folder, native)
                native['status'] = 'pass'
            except Unsafe as error:
                native['status'] = 'blocked'
                native_error = str(error)
                error.scope_windows = {'native': native}
                raise
            except Exception as error:
                native['status'] = 'fail'
                native_error = str(error)
                self.check_idle()
            finally:
                write_json(folder / 'native-window.json', dict(native, error=native_error))
            self.report.event('scope-window', id=self.case['id'], path='native', **native, error=native_error)
        try:
            result = self.web_scope(folder)
        except Exception as error:
            error.scope_windows = {'native':native}
            raise
        result['confirmed']['status'] = 'pass'
        self.report.event('scope-window', id=self.case['id'], path='web',
                          **{key:value for key,value in result['confirmed'].items() if key!='summary'})
        if native_error:
            error = RuntimeError(f'Fixed native J-Scope failed: {native_error}')
            error.scope_windows = dict(result, native=native)
            raise error
        return dict(result, native=native)

    def native_scope(self, folder, result):
        from probe_stream import Probe
        from tools.board_acceptance_scope import native_window

        case = self.case
        base = 0xf0404000 if self.rv else 0x20004000
        address = base+256
        seed = 0x68004853 if self.rv else 0x485353
        values = random.Random(seed).randbytes(4096)[256:256+4*case['channels']]
        result.update(case['native'], transport=case['transport'], requestedHz=case['requestedHz'],
                      channels=case['channels'], address=hex(address))
        with self.target.memory_fixture(folder/'native-fixture', [(address, len(values))], keep_halted=True,
                                        before_restore=self.check_idle):
            with self.target.link(case['transport'], case['requestedHz']) as (device, mem, chip, link):
                result['target'] = self.target.state(mem, chip)
                checked(result['target']['halted'], 'Native HSS requires the original fixture halt state')
                mem.write(address, values)
                checked(mem.read(address,len(values)) == values, 'Native HSS fixture readback mismatch')
                def stream_clock():
                    actual = self.clock()
                    if case['transport']=='jtag':
                        checked(actual['jtagRoute'] & 7 == (7 if self.rv else 3),
                                'Native HSS did not retain the planned JTAG route')
                    return actual
                if self.rv:
                    result['minimumDtmIdleCycles'] = link['dmi_idle_min']
                probe = Probe(self.args.serial, zynq_only=True)
                try:
                    native_window(device, probe, case, address, values, stream_clock, result)
                finally:
                    probe.close()

    def web_scope(self, folder):
        channels = self.case['channels']
        seed_ticks = SCOPE_PERIODS[(self.args.board, self.case['transport'])][channels == 8]
        address = self.scope_address()
        values = struct.pack('<8I', *SCOPE_VALUES)
        rows = []
        with self.target.memory_fixture(folder / 'fixture', [(address, len(values))],
                                        lambda mem, chip, state: self.seed_scope(mem, chip, state, address, values),
                                        before_restore=self.check_idle):
            def point(ticks, seconds):
                row = dict(periodTicks=ticks, requestedSeconds=seconds, transport=self.case['transport'],
                           requestedHz=self.case['requestedHz'], channels=channels,
                           nominalGroupsPerSecond=24_000_000/ticks)
                rows.append(row)
                try:
                    self.scope_start(channels, ticks, seconds + 8)
                    clock = self.clock()
                    self.invoke('scope', 'readScopeMetrics', {'fresh': True})
                    before = self.invoke('scope', 'summary')['probeMetrics']
                    t0 = time.monotonic()
                    time.sleep(seconds)
                    self.invoke('scope', 'readScopeMetrics', {'fresh': True})
                    wall = time.monotonic() - t0
                    after = self.invoke('scope', 'summary')['probeMetrics']
                    summary = self.scope_stop()
                    skip = capture_quality(summary)
                    groups = after['produced'] - before['produced']
                    receive_seconds = ((after['tick'] - before['tick']) & 0xffffffff) / after['hz']
                    skipped = (after['skipped'] - before['skipped']) & 0xffffffff
                    checked(groups > 0 and receive_seconds > 0, 'Scope counters did not advance')
                    row.update(clock=clock, summary=summary, groups=groups, groupsPerSecond=groups/receive_seconds,
                               counterSeconds=receive_seconds, wallSeconds=wall,
                               windowSkipped=skipped, skipFraction=max(skip, skipped / (groups + skipped)),
                               droppedUsbSamples=summary['lostUsb'], dataSequenceGaps=summary['lostGap'],
                               readErrors=summary['readErrors'], tailCountDelta=summary['tailCountDelta'])
                    if seconds == 60:
                        checked(receive_seconds >= 59.5, 'Scope sample window shorter than 60 seconds')
                        self.invoke('scope', 'saveRaw')
                        data = self.web.download('scope', folder / f'long-{ticks}.jsp')
                        count, _, _, actual_period = jsp_data(data, address, channels, self.case['requestedHz'])
                        checked(count == summary['receivedSamples'] and actual_period == ticks, 'Long JSP differs from settings')
                    return row
                except Exception as error:
                    row['error'] = str(error)
                    raise
                finally:
                    self.invoke('scope', 'disconnect')
                    write_json(folder / 'points.json', rows)
            # The page stores typed values, LOD min/max and timestamps under
            # a 128 MiB cap. Reserve room for the 68 s session, including the
            # acquisition and control overhead outside the 60 s window.
            usable_bytes = 120 * 1024 * 1024
            min_ticks = (68 * 24_000_000 * channels * 4 + usable_bytes - 1) // usable_bytes
            candidates = sorted({max(48, min_ticks, round(seed_ticks * scale)) for scale in (.85, 1, 1.2, 1.5, 2)})
            best = None
            for ticks in candidates:
                try:
                    row = point(ticks, 1.5)
                except Unsafe:
                    raise
                except Exception:
                    self.check_idle()
                    continue
                if row['skipFraction'] < .001:
                    best = ticks
                    break
            checked(best is not None, 'No stable J-Scope short point')
            long = point(best, 60)
            if long['skipFraction'] >= .001:
                long = point(round(best * 1.25), 60)
            checked(long['skipFraction'] < .001, 'J-Scope failed the 60-second skip threshold')
            short_ticks = max(2400, long['periodTicks'])
            try:
                self.scope_start(channels, short_ticks, 3)
                time.sleep(.5)
                stopped = self.scope_stop()
                checked(capture_quality(stopped) < .001, 'Scope export point unstable')
                exports = self.scope_exports(folder, channels, stopped)
            finally:
                self.invoke('scope', 'disconnect')
        return {'confirmed': long, 'exports': exports}

    def seed_scope(self, mem, chip, state, address, values):
        mem.write(address, values)
        checked(mem.read(address, len(values)) == values, 'Scope fixture write did not verify')
        self.target.restore_state(mem, chip, state)

    def flash(self, folder):
        base, capacity, sector = FLASH[self.args.board]
        elf = self.args.target_elf
        machine, segments = elf_contents(elf)
        checked(machine == ('EM_RISCV' if self.rv else 'EM_ARM') and segments, 'Wrong Flash ELF architecture')
        checked(all(base <= address < address + len(data) <= base + capacity for address, data, _ in segments),
                'ELF contains a load segment outside the expected target Flash')
        start = min((address - base) // sector for address, _, _ in segments) * sector + base
        stop = max((address + len(data) - base + sector - 1) // sector for address, data, _ in segments) * sector + base
        checked(stop-start <= (1 << 20), 'Flash acceptance fixture exceeds 1 MiB')
        if self.rv:
            areas = [(0, 0x20000)]
        elif self.args.board == 'h743':
            areas = [(0x24000000, 0x10000), (0x20000000, 0x10000)]
        else:
            areas = [(0x20000000, 0x10000)]
        executable = (self.args.openocd or ROOT / 'prebuilt/golden/host/openocd/openocd.exe').resolve()
        scripts = (self.args.openocd_scripts or executable.parent / 'scripts').resolve()
        if self.rv and not (self.args.openocd and self.args.openocd_scripts):
            raise Pending('HPM target Flash requires matching HPM SDK --openocd and --openocd-scripts for the native comparison')
        if not executable.is_file() or not scripts.is_dir():
            raise Pending('Native OpenOCD or matching scripts not found')
        config = folder / 'native-flash.cfg'
        config.write_text(self.native_flash_config(executable, scripts), encoding='ascii')
        name, offset = HEARTBEAT[self.args.board]
        heartbeat = symbol(elf, name) + offset

        def confirm_flash(expected):
            with self.target.link() as (_, mem, target, _):
                self.target.halt(mem, target)
                current = mem.read(start, stop - start)
                checked(current == mem.read(start, stop - start), 'Unstable independent Flash readback')
                return current == expected

        # Restrict the routine to reprogramming a known running baseline. This
        # bounds recovery to the same sectors and a known executable image.
        with self.target.link() as (_, mem, chip, _):
            starting = self.target.state(mem, chip)
            checked(not starting['halted'], 'Flash test expects a running target application')
            original = mem.read(start, stop - start)
            checked(original == mem.read(start, stop - start), 'Unstable Flash backup')
            for address, data, _ in segments:
                if original[address-start:address-start+len(data)] != data:
                    raise Pending(f'Provide the running baseline ELF. Flash differs at {address:#x}')
            previous = mem.word(heartbeat)
            wait_for(lambda: mem.word(heartbeat), lambda n: n != previous, 2, 'Baseline heartbeat did not advance')
        backup = folder / 'flash.private.bin'
        backup.write_bytes(original)
        write_json(folder / 'flash-backup.json', dict(address=hex(start), bytes=len(original), sha256=sha(original)))
        self.web.page('flash', 'show')
        firmware = dict(pack_file(elf), kind='file')
        options = dict(chip=self.chip, clockKhz=self.case['requestedHz'] // 1000, reset=False,
                       recoveryBounds=dict(start=start, end=stop, sectorSize=sector))
        writes = []
        if self.rv:
            # The SDK ELF is sparse. Match the exact Web erase plan instead
            # of erasing intervening sectors in the contiguous recovery copy.
            plan = self.invoke('flash', 'programFile', firmware, dict(options, prepareOnly=True))
            checked(plan['prepared'], 'Web rejected the Flash comparison plan')
            for first, last in self.flash_ranges(plan['regions'], start, stop, sector):
                image = folder / f'native-{first:08x}.private.bin'
                image.write_bytes(original[first-start:last-start])
                writes.append((first, image))
        native_bytes = sum(path.stat().st_size for _, path in writes) if writes else len(original)
        with self.target.memory_fixture(folder / 'fixture', areas, capture_registers=True, keep_halted=True):
            with self.flash_recovery(folder, backup, lambda: confirm_flash(original),
                                     lambda: self.native_flash(executable, scripts, config, backup, start,
                                                               folder / 'restore-flash.log', geometry=(start, stop, sector))):
                native = self.native_flash(executable, scripts, config, backup, start, folder / 'native-flash.log',
                                           folder / 'native-clock.json', geometry=(start, stop, sector), writes=writes)
                checked(confirm_flash(original), 'Native Flash changed baseline or sector neighbors')
                begin = time.perf_counter()
                # Let the current browser job finish and release its writer
                # before handling Ctrl+C or issuing any recovery command.
                with defer_interrupt() as interrupted:
                    result = self.invoke('flash', 'programFile', firmware, options)
                if interrupted[0]:
                    raise KeyboardInterrupt
                web = time.perf_counter() - begin
                clock = verify_clock(self.read_clock(), self.case['requestedHz'])
                checked(not writes or result['sectors'] == native_bytes // sector,
                        'Web and native Flash sector counts differ')
                checked(result['verified'] and confirm_flash(original), 'Web Flash readback differs from backup')
        # Flash and RAM have been restored before this independent boot check.
        reset_started = time.perf_counter()
        boot = self.reset_application(folder, heartbeat)
        write_json(folder / 'flash-boot.json', boot)
        return dict(nativeSeconds=native, webSeconds=web, clock=clock, bootSeconds=time.perf_counter()-reset_started,
                    verified=True, flashRestored=True,
                    affectedSectorBytes=native_bytes, recoveryCoverageBytes=len(original),
                    nativeInputBytes=native_bytes, webInputBytes=result['bytes'],
                    resetMethod=boot['method'], heartbeat=boot['heartbeat'],
                    detail='Both timings include erase, program and verify over the same affected Flash range')

    @staticmethod
    def flash_ranges(regions, start, stop, sector):
        ranges = []
        for region in sorted(regions, key=lambda item: item['address']):
            address, size = region['address'], region['bytes']
            checked(start <= address < address+size <= stop, 'Web plan exceeds the Flash backup')
            first = start + (address-start)//sector*sector
            last = start + (address+size-start+sector-1)//sector*sector
            if ranges and first <= ranges[-1][1]:
                ranges[-1] = (ranges[-1][0], max(last, ranges[-1][1]))
            else:
                ranges.append((first, last))
        checked(ranges, 'Web plan has no Flash sectors')
        return ranges

    def native_flash_config(self, executable, scripts):
        options = ['adapter driver cmsis-dap', 'cmsis_dap_backend usb_bulk',
                   'cmsis_dap_vid_pid 0x0d28 0x0204', f'adapter serial {self.tcl(self.args.serial)}']
        if self.rv:
            sdk = scripts.parent.parent
            tcl = executable.parent / 'tcl'
            if not (scripts / 'hpm6800_all_in_one.cfg').is_file() or not (tcl / 'interface/cmsis-dap.cfg').is_file():
                raise Pending('HPM native Flash requires the SDK boards/openocd and OpenOCD tcl directories')
            options.extend([f'add_script_search_dir {self.tcl(tcl)}', f'set HPM_SDK_BASE {self.tcl(sdk)}',
                            'set BOARD hpm6800evk', 'set PROBE cmsis_dap',
                            'source [find hpm6800_all_in_one.cfg]'])
        else:
            family = 'stm32f1x' if self.args.board == 'f103ze' else 'stm32h7x'
            options += [f'transport select {self.case["transport"]}', f'source [find target/{family}.cfg]']
        options += [f'adapter speed {self.case["requestedHz"] // 1000}', 'reset_config none']
        return '\n'.join(options) + '\n'

    @contextmanager
    def flash_recovery(self, folder, backup, matches_backup, restore_backup):
        try:
            yield
        except (Exception, KeyboardInterrupt) as operation_error:
            report = dict(failure=repr(operation_error), backup=str(backup), verified=False, rewriteAttempted=False)
            try:
                if isinstance(operation_error, Unsafe) or self.target.uncertain:
                    raise Unsafe(self.target.uncertain or str(operation_error))
                with defer_interrupt() as interrupted:
                    self.check_idle()
                    if not matches_backup():
                        report['rewriteAttempted'] = True
                        restore_backup()
                        checked(matches_backup(), 'Original Flash readback failed after recovery')
                report['verified'] = True
                report['interruptDuringRecovery'] = interrupted[0]
            except (Exception, KeyboardInterrupt) as recovery_error:
                self.target.uncertain = f'Flash restoration unconfirmed. Preserve {backup}: {recovery_error!r}'
                report['recoveryError'] = self.target.uncertain
                raise Unsafe(self.target.uncertain) from recovery_error
            finally:
                write_json(folder / 'flash-recovery.json', report)
            if interrupted[0]:
                raise KeyboardInterrupt from operation_error
            raise

    def reset_application(self, folder, heartbeat):
        if self.args.board == 'f103ze':
            # CDC48 disables JTAG during startup and SYSRESETREQ has not
            # reliably rebooted this fixture. Confirm J7 NRST over SWD.
            self.check_idle()
            with defer_interrupt() as interrupted:
                evidence = self.target.f103_reset_application(heartbeat)
            if interrupted[0]:
                raise KeyboardInterrupt
            return evidence
        # Restore debug configuration alone, preserving the post-reset context.
        with self.target.live_debug(folder / 'boot-debug', self.check_idle):
            with self.web_debug(folder):
                self.debug_call('resetRun')
        with self.target.link() as (_, mem, chip, _):
            checked(not self.target.state(mem, chip)['halted'], 'Restored application is halted after reset')
            tick = mem.word(heartbeat)
            after = wait_for(lambda: mem.word(heartbeat), lambda v: v != tick, 4, 'Restored application did not boot')
        return dict(method='OpenOCD resetRun', heartbeat=dict(address=hex(heartbeat), before=tick, after=after))

    @staticmethod
    def tcl(value):
        value = value.as_posix() if isinstance(value, Path) else str(value)
        checked(not any(char in value for char in '{}\r\n\\'), 'Unsupported character in Tcl argument')
        return '{' + value + '}'

    def native_flash(self, executable, scripts, config, backup, address, log_path, clock_path=None, *,
                     geometry, writes=()):
        import threading
        import libusb_package
        import usb.core
        import usb.util
        # Reading string descriptors opens WinUSB handles. Dispose those
        # explicitly before a different process claims the selected probe.
        devices = list(usb.core.find(find_all=True, idVendor=0x0d28, idProduct=0x0204,
                                     backend=libusb_package.get_libusb1_backend()))
        try:
            matches = [dev for dev in devices if dev.serial_number == self.args.serial]
            checked(len(matches) == 1 and matches[0].manufacturer == 'CherryUSB'
                    and matches[0].product == 'CMSIS-DAP', 'OpenOCD serial is ambiguous or does not identify J7')
        finally:
            for dev in devices:
                usb.util.dispose_resources(dev)
        # OpenOCD is the only writer to the target until it exits. Observe
        # the physical clock while it owns DAP, independently of its logs.
        gate = log_path.with_suffix('.go')
        wait = (f'set n 0; while {{![file exists {self.tcl(gate)}] && $n < 250}} '
                '{ sleep 100; incr n }; '
                'if {$n >= 250} { error "Timed out waiting for Flash verification" }; ')
        bank_indexes = (0, 1) if self.args.board == 'h743' and geometry[1] > 0x08100000 else (0,)
        report_geometry = ''.join(
            f'flash probe {index}; catch {{flash info {index} sectors}} geometry; echo $geometry; '
            for index in bank_indexes)
        first, last, size = geometry
        program_commands = []
        for begin, path in writes or [(address, backup)]:
            length = path.stat().st_size
            checked(first <= begin < begin+length <= last and not (begin-first)%size and not length%size,
                    'Native Flash operation exceeds the backed-up sectors')
            program_commands.append(f'flash write_image erase {self.tcl(path)} {begin:#x} bin; '
                                    f'verify_image {self.tcl(path)} {begin:#x} bin; ')
        program = ''.join(program_commands)
        args = [executable, '-s', scripts, '-f', config, '-c',
                'gdb_port disabled; telnet_port disabled; tcl_port disabled; init; halt; '
                f'{report_geometry}echo ZL_FLASH_READY; {wait}{program}echo ZL_FLASH_DONE; shutdown']
        with log_path.open('wb') as log:
            self.target.prepare_openocd(self.case['transport'])
            start = time.perf_counter()
            verifying_seconds = 0
            # Ctrl+C belongs to the controller. Reap this child explicitly
            # before touching the target again.
            options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
                       if sys.platform == 'win32' else {'start_new_session': True})
            child = None
            reader = None
            try:
                with defer_interrupt() as interrupted:
                    child = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             **options)
                ready = threading.Event()
                def consume():
                    for line in child.stdout:
                        log.write(line)
                        log.flush()
                        if b'ZL_FLASH_READY' in line:
                            ready.set()
                reader = threading.Thread(target=consume, daemon=True)
                reader.start()
                if interrupted[0]:
                    raise KeyboardInterrupt
                checked(ready.wait(15) and child.poll() is None, 'Native Flash did not report bank geometry')
                begin = time.perf_counter()
                reported = set(read_flash_sectors(log_path.read_text(encoding='utf-8', errors='replace')))
                checked(all((at, size) in reported for at in range(first, last, size)),
                        'Physical Flash sectors differ from the backed-up geometry')
                if clock_path:
                    write_json(clock_path, self.clock())
                gate.touch()
                verifying_seconds = time.perf_counter()-begin
                code = child.wait(240)
            except BaseException:
                if child is not None:
                    self.stop_flash_writer(child)
                raise
            finally:
                if child is not None and child.poll() is not None:
                    if reader is not None and reader.ident is not None:
                        reader.join(5)
                    child.stdout.close()
        output = log_path.read_text(encoding='utf-8', errors='replace').lower()
        # Some Jim Tcl builds return verify_image's text without printing it
        # when another command follows. The marker executes after verify.
        checked(code == 0 and ready.is_set() and 'zl_flash_done' in output,
                f'Native Flash did not verify. See {log_path}')
        if clock_path:
            checked(clock_path.is_file(), 'Native Flash actual clock was not confirmed')
        return time.perf_counter() - start - verifying_seconds

    def stop_flash_writer(self, child):
        try:
            with defer_interrupt():
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=10)
        except (Exception, KeyboardInterrupt) as error:
            self.target.uncertain = f'Native Flash writer exit unconfirmed: {error!r}'
            raise Unsafe(self.target.uncertain) from error

    def etm(self, folder):
        elf = self.args.etm_elf.resolve()
        expected = self.report.value['files']['etmElf']
        import libusb_package
        import usb.core
        import usb.util
        matches = list(usb.core.find(find_all=True, idVendor=0x0d28, idProduct=0x0204,
                                     backend=libusb_package.get_libusb1_backend()))
        try:
            if len(matches) != 1 or matches[0].serial_number != self.args.serial:
                raise Pending('Native ETM capture requires J7 to be the only attached CMSIS-DAP VID/PID')
        finally:
            for device in matches:
                usb.util.dispose_resources(device)
        with self.target.link() as (_, mem, chip, _):
            target_evidence = self.verify_target_image(mem, elf, expected)
            name, offset = HEARTBEAT[self.args.board]
            baseline = verify_baseline_rates(self.args.board, mem, etm=True, heartbeat=symbol(elf, name)+offset)
        self.web.page('etm', 'show')
        self.web.page('etm', 'describe')
        # A prior upload can have the same filename and even the same hash.
        # Require a fresh label and the picker to be ready after that load.
        upload = pack_file(elf)
        upload['name'] = f'{elf.stem}-{secrets.token_hex(4)}{elf.suffix}'
        self.web.page('etm', 'upload', selector='#elf-file', files=[upload])
        self.web.wait('etm', '#elf-label', f"{upload['name']} · {expected['sha256'][:12]}")
        wait_for(lambda: self.web.read('etm', '#choose-elf'), lambda button: not button['disabled'],
                 30, 'ETM ELF picker remained busy after loading the verified file')
        target_cfg = {'seconds': 1, 'entry': None, 'resetToEntry': False, 'swdKhz': 10000, 'decode': True}
        begin = time.perf_counter()
        result = self.invoke('etm', 'captureNative', target_cfg)
        wall = time.perf_counter() - begin
        root = Path(self.runtime['recordsDirectory']).resolve()
        record = (root / result['record']).resolve()
        checked(record.parent == root, 'Invalid ETM record path')
        metadata = json.loads((record / 'session.json').read_text(encoding='utf-8'))
        decoded = json.loads((record / 'decoded.json').read_text(encoding='utf-8'))
        checked(digest(record / 'firmware.elf')['sha256'] == expected['sha256'],
                'ETM record used a different ELF from the verified target')
        quality, extent = metadata['quality'], metadata.get('captureExtent') or {}
        checked(result['targetRestored'] and result['captureProof']['restored'], 'ETM target restoration not confirmed')
        checked(quality['synced'] and quality['ended'] and not quality['loss'] and extent.get('complete')
                and abs(extent.get('actualSeconds', 0)-1) <= .002, 'ETM capture window or quality invalid')
        verification = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'toolbox.py'), 'trace', 'verify',
                                       '--record', str(record), '--require-decoded'], cwd=ROOT, capture_output=True,
                                      text=True, encoding='utf-8', timeout=60)
        (folder / 'trace-verify.json').write_text(verification.stdout, encoding='utf-8')
        checked(verification.returncode == 0 and decoded['summary']['instructions'] > 0,
                f'ETM decode quality invalid. See {folder / "trace-verify.json"}')
        verdict = json.loads(verification.stdout)['result']['quality']
        display = self.invoke('etm', 'measureOpenRecord', result['record'])
        processing = record / 'decode-performance.json'
        native = metadata.get('nativeAcceptance') or {}
        return dict(record=str(record), quality=quality, window=extent, decoded=decoded['summary'],
                    restored=True, webCaptureSeconds=wall, display=display, targetElf=target_evidence, decodeQuality=verdict,
                    captureHostSeconds=native.get('capture_host_seconds'),
                    captureClocks=result['captureProof'].get('rccCapture'),
                    processing=json.loads(processing.read_text(encoding='utf-8')) if processing.exists() else None,
                    **baseline)

    def close_scope(self):
        try:
            if self.invoke('scope', 'summary')['running']:
                self.scope_stop()
        finally:
            self.invoke('scope', 'disconnect')

    @contextmanager
    def stress_business(self, business, folder):
        folder.mkdir()
        if business == 'debug':
            with self.target.live_debug(folder / 'fixture', self.check_idle):
                try:
                    self.debug_connect(folder)
                    self.debug_call('halt')
                    pc = self.debug_call('readReg', 'pc')
                    self.debug_call('step')
                    stepped = self.debug_call('readReg', 'pc')
                    checked(pc != stepped, 'Debug stress single-step did not advance')
                    yield dict(pc=pc, steppedPc=stepped, clock=self.clock())
                finally:
                    self.close_debug()
            return
        live_rtt = business in ('rtt-viewer', 'rtt-forward')
        with self.rtt_fixture(folder, producer=live_rtt) as elf:
            if business == 'rtt-viewer':
                try:
                    self.viewer_start(elf)
                    clock = self.clock()
                    self.invoke('rtt', 'saveRaw')
                    data = self.web.download('rtt', folder / 'up.bin')
                    first = self.invoke('rtt', 'summary')['stats']['bytes']
                    next_state = wait_for(lambda: self.invoke('rtt', 'summary'),
                                          lambda s: s['running'] and s['stats']['bytes'] > first,
                                          4, 'Viewer stopped making progress before disconnect')
                    yield dict(clock=clock, sequence=sequence(data), received=next_state['stats']['bytes'])
                finally:
                    self.invoke('rtt', 'disconnect')
            elif business == 'rtt-forward':
                try:
                    port = self.cdc_start()
                    clock = self.clock()
                    window = self.invoke('rttcdc', 'captureWindow', {'seconds': .25, 'maxMiB': 8})
                    data = self.web.download('rttcdc', folder / 'up.bin')
                    checked(window['complete'] and window['bytes'] == len(data), 'RTT stress recording incomplete')
                    first = self.invoke('rttcdc', 'summary')['bytes']
                    next_state = wait_for(lambda: self.invoke('rttcdc', 'summary'),
                                          lambda s: s['open'] and s['bytes'] > first,
                                          3, 'RTT forwarding stopped before disconnect')
                    yield dict(clock=clock, port=port, sequence=self.sequence_window(data), received=next_state['bytes'])
                finally:
                    try:
                        self.cdc_stop()
                    finally:
                        self.cdc_close()
            else:
                try:
                    summary = self.scope_start(1, 2400, 75)
                    clock = self.clock()
                    observed = wait_for(lambda: self.invoke('scope', 'summary'),
                                        lambda s: s['running'] and s['samples'] > summary['samples'],
                                        5, 'Scope stopped before the handoff')
                    yield dict(clock=clock, groups=observed['samples'], state=observed['state'])
                    if self.invoke('scope', 'summary')['receivedSamples'] > 0:
                        self.invoke('scope', 'saveRaw')
                        data = self.web.download('scope', folder / 'prefix.jsp')
                        jsp_data(data, self.scope_address(), 1, self.case['requestedHz'])
                finally:
                    self.close_scope()

    def stop_stress_business(self, business):
        if business == 'rtt-viewer':
            state = self.invoke('rtt', 'summary')
            checked(not state['stats'].get('lost') and not state['stats'].get('corrupt'), 'Viewer detected loss')
            self.invoke('rtt', 'disconnect')
            return state
        if business == 'rtt-forward':
            state = self.cdc_stop()
            self.cdc_close()
            return state
        if business == 'jscope':
            state = self.scope_stop()
            checked(capture_quality(state) < .001, 'J-Scope stress short window unstable')
            self.invoke('scope', 'disconnect')
            return state
        self.close_debug()
        return self.invoke('dbg', 'summary')

    def disconnect_topbar(self, page):
        checked(not self.web.read(page, '#btn-probe-disconnect')['disabled'], 'No top-bar session to disconnect')
        self.click(page, '#btn-probe-disconnect')
        wait_for(lambda: self.web.read(page, '#btn-probe-connect'),
                 lambda x: not x['disabled'], 8, 'Top-bar connection remains busy')
        checked(self.web.read(page, '#btn-probe-disconnect')['disabled'], 'Top-bar disconnect did not complete')
        if page == 'rttcdc':
            # The top bar preserves a standalone serial client; explicitly
            # release this test's CDC port before reopening it.
            self.invoke('rttcdc', 'close', target='session')

    def usb_present(self):
        import hid
        from probe_hid_control import is_zynqlink_hid
        return any(row.get('serial_number') == self.args.serial and is_zynqlink_hid(row)
                   for row in hid.enumerate(0x0d28, 0x0204))

    def usb_cycle(self, page):
        if not self.args.usb_data_cycle:
            raise Pending('Physical USB data disconnect requires --usb-data-cycle and independent power')
        print(f'请只断开 J7 {self.args.serial} 的 USB 数据连接，保持供电。', file=sys.stderr, flush=True)
        self.report.event('operator', id=self.case['id'], action='disconnect-j7-data', serial=self.args.serial)
        try:
            wait_for(self.usb_present, lambda present: not present, 60, 'J7 removal not observed')
        finally:
            print(f'请接回 J7 {self.args.serial} 的 USB 数据连接。', file=sys.stderr, flush=True)
            self.report.event('operator', id=self.case['id'], action='reconnect-j7-data', serial=self.args.serial)
            wait_for(self.usb_present, bool, 60, 'J7 re-enumeration not observed')
        try:
            if not self.web.read(page, '#btn-probe-disconnect')['disabled']:
                self.disconnect_topbar(page)
            return self.probe_identity()
        finally:
            if page == 'rttcdc':
                self.invoke('rttcdc', 'close', target='session')

    def stress(self, folder):
        rows = []
        failures = []
        pending = []
        pages = {'rtt-viewer': 'rtt', 'rtt-forward': 'rttcdc', 'jscope': 'scope', 'debug': 'dbg'}
        for index, action in enumerate(self.case['actions'], 1):
            business, ending = action['business'], action['ending']
            page = pages[business]
            row = dict(action, status='pass')
            rows.append(row)
            began = time.monotonic()
            try:
                with self.stress_business(business, folder / f'{index:02d}-initial') as initial:
                    row['initial'] = initial
                    if ending in ('switch', 'idle-disconnect'):
                        if ending == 'idle-disconnect':
                            # Establish explicit top-bar ownership first so the
                            # idle-disconnect path actually exercises the button.
                            self.click(page, '#btn-probe-connect')
                            wait_for(lambda: self.web.read(page, '#btn-probe-connect'),
                                     lambda x: not x['disabled'], 8, 'Top-bar connect did not complete')
                        row['stop'] = self.stop_stress_business(business)
                    if ending in ('idle-disconnect', 'active-disconnect'):
                        self.disconnect_topbar(page)
                        if ending == 'active-disconnect' and business == 'jscope':
                            capture_quality(self.invoke('scope', 'summary'))
                    if ending == 'usb-disconnect':
                        row['enumeratedAfter'] = self.usb_cycle(page)
                if ending != 'switch':
                    reconnect = time.monotonic()
                    with self.stress_business(business, folder / f'{index:02d}-reconnected') as state:
                        row['reconnected'] = state
                        row['reconnectSeconds'] = time.monotonic() - reconnect
                        self.stop_stress_business(business)
                elif index < len(self.case['actions']):
                    self.web.page(pages[self.case['actions'][index]['business']], 'show')
            except Pending as error:
                row.update(status='pending', reason=str(error))
                pending.append(str(error))
            except Unsafe as error:
                row.update(status='fail', error=str(error))
                raise
            except Exception as error:
                row.update(status='fail', error=str(error))
                failures.append(str(error))
            finally:
                row['seconds'] = time.monotonic() - began
                write_json(folder / 'stress.json', rows)
                self.report.event('stress-step', id=self.case['id'], step=index, **row)
            try:
                self.check_idle()
            except Exception as error:
                raise Unsafe(f'Stress {business} recovery unconfirmed: {error}') from error
        if failures:
            raise RuntimeError(f'{len(failures)} stress action(s) failed: {failures[0]}')
        if pending:
            raise Pending(f'{len(pending)} stress action(s) pending: {pending[0]}')
        return {'actions': rows}
