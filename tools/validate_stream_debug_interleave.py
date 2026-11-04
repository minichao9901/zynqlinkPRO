"""F103/H743 RTT/J-Scope + real DAP traffic, halt/resume and single step.

RAM-only fixtures with full SRAM/core/RCC/run-state restoration. Run exclusively
after loading the explicitly named probe pair. No target Flash/QSPI writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import statistics
import struct
import subprocess
import sys
import time

import serial
import serial.tools.list_ports
import usb.util
from benchmark_probe_stream import HssReader
from benchmark_rtt_forward import Reader, core_read, core_write, DHCSR
from dap_pipeline_bench import open_dap, setup, xfer, send, read_exact
from probe_build_info import provenance, live_clock_snapshot
from probe_stream import Probe
from test_probe_board import Memory, stop, drain_hss
from test_swd_lowfreq_board import recover
from target_snapshot import snapshot
from validate_fclk_performance import ROOT, PAIRS, EXPECTED, command, save, physical_snapshot

BASE, SIZE, SCRATCH = 0x20000000, 20480, 0x20004800
TARGET_CPUID, TARGET_DPIDR = 0x411fc231, 0x1ba01477
REGISTERS = list(range(19)) + [20]


class ScopeReader(HssReader):
    def __init__(self, dev, expected, period, variables):
        super().__init__(dev, expected, period, allow_duplicate_stat=True)
        self.definitions = 0
        self.variables = variables
        self.last_data = None
        self.timer_rebases = []
        self.timestamp_order_errors = []

    def consume(self, data):
        for off in range(0, len(data), 512):
            magic, version, kind, seq, stamp, n, aux = struct.unpack_from('<HBBIIHH', data, off)
            if kind == 1:
                assert seq == 0 and not self.definitions, 'Unexpected/duplicate HSS DEF'
                assert aux == self.variables
                assert struct.unpack_from('<I', data, off + 20)[0] == self.period
                self.definitions += 1
            elif kind == 2:
                assert self.definitions == 1, 'HSS DATA arrived before DEF seq0'
                if self.last_data is not None:
                    previous_stamp, previous_n = self.last_data
                    elapsed = (stamp - previous_stamp) & 0xffffffff
                    last_to_next = (elapsed - (previous_n - 1) * self.period) & 0xffffffff
                    if last_to_next == 0 or last_to_next >= 0x80000000:
                        self.timestamp_order_errors.append(dict(previous=self.last_data,
                            stamp=stamp, samples=n, gap_ticks=last_to_next))
                    elif elapsed != previous_n * self.period:
                        self.timer_rebases.append(dict(previous=self.last_data, stamp=stamp,
                            samples=n, gap_since_last_sample_ticks=last_to_next,
                            phase_remainder_ticks=elapsed % self.period))
                self.last_data = (stamp, n)
            # probe_after_dap re-arms/rebases the sampler. A global integer
            # period grid is not a valid invariant across debug ownership.
            # Keep strict payload/sequence/count checks and independently
            # report timer rebases or backwards/overlapping sample timestamps.
            self.previous_data = None
            super().consume(data[off:off + 512])


def compile_producer(out, name):
    gcc = Path(shutil.which('arm-none-eabi-gcc'))
    objcopy = gcc.with_name('arm-none-eabi-objcopy.exe' if gcc.suffix == '.exe' else 'arm-none-eabi-objcopy')
    elf, binary = out / (name + '.elf'), out / (name + '.bin')
    source = ROOT / f'firmware/target/probe_{name}_ram.S'
    subprocess.run([str(gcc), '-mcpu=cortex-m3', '-mthumb', '-nostdlib',
                    f'-Wl,-Ttext={BASE:#x}', f'-Wa,--defsym,FIXTURE_BASE={BASE:#x}', '-Wl,-e,producer', str(source), '-o', str(elf)], check=True)
    subprocess.run([str(objcopy), '-O', 'binary', str(elf), str(binary)], check=True)
    return binary.read_bytes()


def wait_halt(mem):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if mem.word(DHCSR) & (1 << 17):
            return
    raise RuntimeError('Target did not report halted after debug command')


def debug_burst(mem, o, i, transport, fixture, stats):
    start = time.perf_counter()
    if transport == 'swd':
        response = xfer(o, i, [5, 0, 1, 2])
        assert response[:3] == bytes([5, 1, 1]) and int.from_bytes(response[3:7], 'little') == TARGET_DPIDR, response.hex()
    else:
        response = xfer(o, i, [0x16, 0])
        assert response[:2] == bytes([0x16, 0]) and int.from_bytes(response[2:6], 'little') & 0x0fff0fff == 0x0ba00477, response.hex()
    assert mem.word(0xe000ed00) == TARGET_CPUID
    mem.word(DHCSR)
    # Read/write independent SRAM; no producer/ring/sample variables overlap.
    value = (stats['bursts'] ^ 0x61da9000) & 0xffffffff
    mem.write_word(SCRATCH + 0x700, value)
    assert mem.word(SCRATCH + 0x700) == value
    # Deliberately preserve a host TAR across autonomous stream ownership.
    mem.address(SCRATCH)
    for at in range(4):
        response = xfer(o, i, [6, 0, 16, 0, 15])
        assert response[:4] == bytes([6, 16, 0, 1])
        assert response[4:] == fixture[at * 64:(at + 1) * 64], 'Host AP TAR/CSW context lost'
    # Queue eight real DAP requests before reading responses. All 256-byte
    # blocks fit the backed-up scratch window and each result is byte checked.
    mem.address(SCRATCH)
    for _ in range(8):
        send(o, [6, 0, 64, 0, 15])
    for at in range(8):
        response = read_exact(i, 260)
        assert response[:4] == bytes([6, 64, 0, 1])
        index = at % 4 if (TARGET_CPUID >> 4) & 0xfff == 0xc27 else at
        expected = bytearray(fixture[index * 256:(index + 1) * 256])
        if index == 7:
            expected[0:4] = struct.pack('<I', value)
        assert response[4:] == expected, 'Pipelined debug SRAM read mismatch'
    elapsed = time.perf_counter() - start
    stats['bursts'] += 1
    stats['verified_memory_operations'] += 16
    stats['dap_requests_in_bursts'] += 23
    stats['burst_latencies_s'].append(elapsed)
    assert elapsed < 2, f'Debug burst exceeded 2s responsiveness bound: {elapsed}'


def debug_control(mem, reader, stats):
    t0 = time.perf_counter()
    mem.write_word(DHCSR, 0xa05f0003)
    wait_halt(mem)
    pc_before = core_read(mem, 15)
    r12 = core_read(mem, 12)
    core_write(mem, 12, r12 ^ 0x5a5a5a5a)
    assert core_read(mem, 12) == r12 ^ 0x5a5a5a5a
    core_write(mem, 12, r12)
    # C_DEBUGEN | C_STEP | C_MASKINTS; the F103 executes one instruction.
    mem.write_word(DHCSR, 0xa05f000d)
    wait_halt(mem)
    pc_after = core_read(mem, 15)
    count_before = reader.count if hasattr(reader, 'count') else reader.samples
    mem.write_word(DHCSR, 0xa05f0001)
    assert not mem.word(DHCSR) & (1 << 17), 'Target remained halted after resume'
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = reader.count if hasattr(reader, 'count') else reader.samples
        if reader.error:
            raise RuntimeError(reader.error)
        if current > count_before:
            break
        time.sleep(.01)
    else:
        raise RuntimeError('Stream did not resume after target halt/step/resume')
    stats['halt_step_resume'].append(dict(pc_before=hex(pc_before), pc_after=hex(pc_after),
                                        elapsed_s=time.perf_counter() - t0,
                                        stream_progress_after_resume=True))


def exercise(mem, o, i, probe, reader, fixture, speed, transport, seconds, command_id, metric_action,
             stats, full_reconnect=False):
    stats.update(bursts=0, verified_memory_operations=0, dap_requests_in_bursts=0, burst_latencies_s=[],
                 halt_step_resume=[], stage_counters=[])

    def checkpoint(stage):
        rc, values = probe.action(command_id, metric_action)
        assert rc == 0, (stage, rc, values)
        stats['stage_counters'].append(dict(stage=stage, metrics=values,
            received=reader.count if hasattr(reader, 'count') else reader.samples))

    time.sleep(.25)
    assert reader.error is None, reader.error
    checkpoint('baseline_begin')
    time.sleep(.5)
    checkpoint('baseline_end')
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        debug_burst(mem, o, i, transport, fixture, stats)
        if reader.error:
            raise RuntimeError(reader.error)
        time.sleep(.002)
    checkpoint('debug_bursts_end')
    for _ in range(3):
        debug_control(mem, reader, stats)
    checkpoint('halt_step_resume_end')
    if full_reconnect:
        stats['full_SWJ_reconnect_attempted'] = True
        setup(o, i, speed // 1000, transport, speed_hz=speed)
        stats['full_SWJ_reconnect_completed'] = True
    before = reader.count if hasattr(reader, 'count') else reader.samples
    time.sleep(.5)
    after = reader.count if hasattr(reader, 'count') else reader.samples
    assert after > before and reader.error is None, 'Stream stalled after debug traffic ceased'
    checkpoint('post_debug_end')
    stats['post_debug_progress'] = after - before
    stats['max_debug_burst_s'] = max(stats['burst_latencies_s'])
    stats['median_debug_burst_s'] = statistics.median(stats['burst_latencies_s'])
    stats['clock_after_debug'] = live_clock_snapshot()
    assert abs(stats['clock_after_debug']['actual_link_Hz'] - speed) < 10
    return stats


def rtt_point(probe, mem, dev, o, i, code, speed, transport, seconds, full_reconnect):
    row = dict(service='rtt', speed_hz=speed, transport=transport, passed=False, debug={})
    reader = None
    fixture = random.Random(0xdab).randbytes(2048)
    mem.write_word(DHCSR, 0xa05f0003)
    mem.write(BASE, code)
    mem.write(BASE+0x200, struct.pack('<16sII6II', b'SEGGER RTT', 1, 0, 0, BASE+0x1000, 8192, 0, 0, 0, 0))
    mem.write(SCRATCH, fixture)
    prepare_code(mem)
    core_write(mem, 16, 0x01000000)
    core_write(mem, 20, 1)
    core_write(mem, 15, BASE | 1)
    setup(o, i, speed // 1000, transport, speed_hz=speed)
    assert probe.action(0x31, 12, bytes([2 if transport == 'jtag' else 1]))[0] == 0
    port = next(p.device for p in serial.tools.list_ports.comports() if p.vid == 0xd28 and p.pid == 0x204)
    with serial.Serial(port, 115200, timeout=.025) as com:
        com.reset_input_buffer()
        assert probe.action(0x31, 7, struct.pack('<IHBB', speed, 1024, 0, 1))[0] == 0
        assert probe.action(0x31, 1, struct.pack('<IIB', BASE+0x200, 0x100, 0))[0] == 0
        reader = Reader(com)
        reader.start()
        try:
            mem.write_word(DHCSR, 0xa05f0001)
            exercise(mem, o, i, probe, reader, fixture, speed, transport, seconds, 0x31, 2,
                     row['debug'], full_reconnect)
            mem.write_word(DHCSR, 0xa05f0003)
            wait_halt(mem)
            published = mem.word(BASE+0x230) * 4
            wr = mem.word(BASE+0x224)
            in_flight = (wr - (published & 8191)) & 8191
            assert in_flight in (0, 4)
            published += in_flight
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and reader.count != published and reader.error is None:
                time.sleep(.02)
            rc, final = probe.action(0x31, 2)
            row['final'] = final
            assert rc == 0 and final[5] == 0, (rc, final)
            assert reader.error is None and reader.count == published and not reader.pending, (reader.error, reader.count, published)
            row.update(passed=True, session_bytes=published, all_published_received=True, sequence_exact=True)
        except Exception as exc:
            row['error'] = repr(exc)
        finally:
            try:
                probe.action(0x31, 0)
            finally:
                reader.quit.set()
                reader.join(2)
                row['reader_stopped'] = not reader.is_alive()
    return row


def hss_point(probe, mem, dev, o, i, code, speed, transport, seconds, variables, period, full_reconnect):
    row = dict(service='hss', speed_hz=speed, transport=transport, variables=variables,
               period_ticks=period, requested_sample_Hz=24000000 / period, passed=False, debug={})
    fixture = random.Random(0xdab).randbytes(2048)
    samples = random.Random(0x485353).randbytes(4 * variables)
    mem.write_word(DHCSR, 0xa05f0003)
    mem.write(BASE, code)
    mem.write_word(BASE+0x4000, 0)
    mem.write(BASE+0x4100, samples)
    mem.write(SCRATCH, fixture)
    prepare_code(mem)
    core_write(mem, 16, 0x01000000)
    core_write(mem, 20, 1)
    core_write(mem, 15, BASE | 1)
    setup(o, i, speed // 1000, transport, speed_hz=speed)
    assert probe.action(0x31, 12, bytes([2 if transport == 'jtag' else 1]))[0] == 0
    assert probe.action(0x32, 3, struct.pack('<I', speed))[0] == 0
    config = struct.pack('<IBB', period, 0, variables) + b''.join(
        struct.pack('<IBB', BASE+0x4100 + 4 * n, 4, 4) for n in range(variables))
    assert probe.action(0x32, 10, config)[0] == 0
    drain_hss(dev)
    reader = ScopeReader(dev, samples, period, variables)
    reader.start()
    try:
        mem.write_word(DHCSR, 0xa05f0001)
        assert probe.action(0x32, 1)[0] == 0
        exercise(mem, o, i, probe, reader, fixture, speed, transport, seconds, 0x32, 11,
                 row['debug'], full_reconnect)
        for _ in range(100):
            rc, _ = probe.action(0x32, 0)
            if rc == 0:
                break
            assert rc == -7
            time.sleep(.01)
        else:
            raise RuntimeError('HSS STOP did not finish')
        time.sleep(.12)
        reader.quit.set()
        reader.join(2)
        assert not reader.is_alive() and reader.error is None, reader.error
        drain_hss(dev, reader.consume)
        rc, final = probe.action(0x32, 11)
        row['final'] = final
        assert rc == 0 and reader.samples == final[3], (reader.samples, final)
        assert final[6] == 0 and final[7] > 0, ('HSS errors / DAP yields', final)
        assert reader.definitions == 1
        row.update(passed=True, session_samples=reader.samples, skipped=final[4],
                   DAP_yields=final[7], sample_count_match=True, all_data_frames_verified=True,
                   first_DEF_verified=True, stat_duplicate_frames=len(reader.control_sequence_errors),
                   control_sequence_errors=reader.control_sequence_errors,
                   timer_rebase_events=len(reader.timer_rebases),
                   timer_rebase_examples=reader.timer_rebases[:16],
                   timestamp_order_errors=reader.timestamp_order_errors,
                   sample_timestamps_monotonic=not reader.timestamp_order_errors,
                   global_uniform_sample_phase_preserved=not reader.timer_rebases)
    except Exception as exc:
        row['error'] = repr(exc)
    finally:
        try:
            probe.action(0x32, 0)
        finally:
            reader.quit.set()
            reader.join(2)
            row['reader_stopped'] = not reader.is_alive()
            drain_hss(dev)
    return row


def prepare_code(mem):
    if (TARGET_CPUID >> 4) & 0xfff == 0xc27:
        assert not mem.word(0xe000ed14)&(1<<16), 'M7 fixture requires D-cache disabled'
        mem.write_word(0xe000ef50, 0)


def main():
    global BASE, SCRATCH, TARGET_CPUID, TARGET_DPIDR
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair', choices=list(PAIRS))
    p.add_argument('--pair-dir',type=Path,help='Explicit candidate tuple; verify its manifest and physical OCM instead of using historical labels')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--transport', choices=['swd', 'jtag'], default='swd')
    p.add_argument('--speeds', default='50000000,60000000')
    p.add_argument('--seconds', type=float, default=2)
    p.add_argument('--fixture-base',type=lambda v:int(v,0),choices=(0x20000000,0x24040000),default=0x20000000)
    p.add_argument('--full-reconnect', action='store_true',
                   help='Also perform full SWJ line reset/reinitialization while streaming; distinct from ordinary debug commands')
    a = p.parse_args()
    BASE=a.fixture_base;SCRATCH=BASE+0x4800
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if not a.pair_dir and not a.pair:p.error('--pair or --pair-dir is required')
    pair = a.pair_dir.resolve() if a.pair_dir else ROOT / 'prebuilt' / PAIRS[a.pair]
    if a.pair_dir:
        manifest=json.loads((pair/'manifest.json').read_text(encoding='utf-8-sig'))
        assert all(hashlib.sha256((pair/name).read_bytes()).hexdigest()==manifest['files'][name]['sha256'] for name in ['probe.bit','application.elf'])
    else:
        assert tuple(hashlib.sha256((pair / name).read_bytes()).hexdigest()
                     for name in ['probe.bit', 'application.elf']) == EXPECTED[a.pair]
    command(out, 'identity', ['tools/verify_probe_ocm_code.py', '--elf', pair / 'application.elf', '--out-dir', out / 'identity'])
    code_rtt, code_hss = compile_producer(out, 'rtt'), compile_producer(out, 'hss')
    report = dict(artifacts=provenance(pair / 'probe.bit', pair / 'application.elf'),
                  driverSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  transport=a.transport, rows=[], targetFlashWrites=False, targetClockWrites=False)
    d, o, i = open_dap()
    probe, mem = Probe(), Memory(o, i)
    backup = regs = initial = None
    result_path = out / 'result.json'
    try:
        stop(probe, d)
        identity=setup(o, i, 1000)
        TARGET_DPIDR=int.from_bytes(identity[3:7],'little')
        TARGET_CPUID=mem.word(0xe000ed00)
        initial = mem.word(DHCSR)
        mem.write_word(DHCSR, 0xa05f0003)
        wait_halt(mem)
        regs = {n: core_read(mem, n) for n in REGISTERS}
        backup = mem.read(BASE, SIZE)
        (out / 'backup.bin').write_bytes(backup)
        report.update(backup_sha256=hashlib.sha256(backup).hexdigest(), registers_before=regs,
                      RCC_before=snapshot(mem),fixture_base=hex(BASE),
                      initial_halted=bool(initial & (1 << 17)))
        if (TARGET_CPUID>>4)&0xfff == 0xc27:
            report['DBG_CR_before']=hex(mem.word(0x5c001004))
            report['ETM_PRGCTLR_before']=hex(mem.word(0xe0041004))
            assert not int(report['ETM_PRGCTLR_before'],16)&1, 'This study excludes active H7 ETM output'
        else:
            report['ETMCR_before']=hex(mem.word(0xe0041000))
            assert int(report['ETMCR_before'],16)&0x400, 'This study excludes active ETM output'
        save(result_path, report)
        for speed in map(int, a.speeds.split(',')):
            for service in ['rtt', 'hss8', 'hss1']:
                setup(o, i, 1000)
                if service == 'rtt':
                    row = rtt_point(probe, mem, d, o, i, code_rtt, speed, a.transport, a.seconds, a.full_reconnect)
                else:
                    row = hss_point(probe, mem, d, o, i, code_hss, speed, a.transport, a.seconds,
                                    8 if service == 'hss8' else 1, 24000 if service == 'hss8' else 24, a.full_reconnect)
                report['rows'].append(row)
                save(result_path, report)
                print('INTERLEAVE', service, speed, 'PASS' if row['passed'] else 'FAIL',
                      'bursts', row.get('debug', {}).get('bursts'), 'error', row.get('error'), flush=True)
                if not row['passed']:
                    raise RuntimeError(f'{service}/{speed} failed: {row.get("error")}; see {result_path}')
                stop(probe, d)
        report['passed'] = True
    except BaseException as exc:
        report['failure'] = repr(exc)
        raise
    finally:
        try:
            try:
                stop(probe, d)
            except Exception:
                recover(d, i)
                stop(probe, d)
            recover(d, i)
            setup(o, i, 1000)
            mem.write_word(DHCSR, 0xa05f0003)
            if backup is not None:
                mem.write(BASE, backup)
                report['restore_match'] = mem.read(BASE, SIZE) == backup
                assert report['restore_match']
            if regs is not None:
                for n, value in regs.items():
                    core_write(mem, n, value)
                report['registers_after'] = {n: core_read(mem, n) for n in regs}
                report['registers_match'] = report['registers_after'] == regs
                assert report['registers_match']
            report['RCC_after'] = snapshot(mem)
            assert report.get('RCC_before', report['RCC_after']) == report['RCC_after']
            if initial is not None and not initial & (1 << 17):
                mem.write_word(DHCSR, 0xa05f0001)
            report['run_halt_restored'] = bool(mem.word(DHCSR) & (1 << 17)) == bool(initial & (1 << 17))
            assert report['run_halt_restored']
        finally:
            save(result_path, report)
            probe.close()
            usb.util.dispose_resources(d)
    save(out / 'safety.json', physical_snapshot())


if __name__ == '__main__':
    main()
