"""HPM5301 SRAM, RTT/CDC and PL HSS measurements with real byte checks.

Run after explicitly loading the --bit/--elf pair and the 360 MHz SRAM target
fixture. Memory traffic uses the PL DMI/SBA backend, not host DMI loops.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import struct
import time

import serial
import usb.util

from benchmark_probe_stream import HssReader
from benchmark_rtt_forward import Reader
from dap_pipeline_bench import drain, le, open_dap, read_exact, send, xfer
from probe_build_info import live_clock_snapshot, provenance
from probe_stream import Probe
from riscv_target import RiscvTarget
from test_probe_board import Memory, drain_hss, stop
from test_swd_lowfreq_board import recover

BASE = 0x0106C000  # Free DLM system alias, above fixture stack; 64 KiB window.
SIZE = 65536
HSS_BASE = 0xF0404000
STATE = 0xF0400000
RTT = 0xF0400200
RING = 0xF0401000


def setup(out, inp, speed, mode=0, connect=False):
    if connect:
        assert xfer(out, inp, [2, 2]) == b'\x02\x02'
    assert xfer(out, inp, [0x8B, 1]) == b'\x8b\x00\x01'
    assert xfer(out, inp, [0x15, 1, 5]) == b'\x15\x00'
    assert xfer(out, inp, [0x11] + le(speed)) == b'\x11\x00'
    assert xfer(out, inp, [0x89, mode])[:3] == bytes([0x89, 0, mode])
    reply = xfer(out, inp, [0x16, 0])
    assert reply == bytes.fromhex('16003d560010'), ('IDCODE', reply.hex())
    assert xfer(out, inp, [0x89, mode])[:3] == bytes([0x89, 0, mode])
    # Activate the real DM through the PL virtual memory frontend.
    reply = xfer(out, inp, [5, 0, 2, 0] + le(0x1E) + [4] + le(0x50000032))
    assert reply == b'\x05\x02\x01', ('DM activation', reply.hex())


def clock(out, inp):
    reply = xfer(out, inp, [0x80, 255])
    fclk, cfg = struct.unpack_from('<II', reply, 4)
    timing = xfer(out, inp, [0x89, 255])
    half = 1 + ((cfg >> 13) & 15)
    return dict(FCLK_Hz=fclk, actual_TCK_Hz=fclk / (2 * half),
                JTAG_sampling_mode=timing[2], cfg=hex(cfg),
                dmi_idle_min=8, clock_source='PS FCLK divider and PL half_delay registers')


def recover_link(dev, out, inp):
    recover(dev, inp)
    # Clear sticky DTM and SBA errors using low-speed raw scans, independent
    # of the failed high-speed memory phase. Target CPU clock is unchanged.
    xfer(out, inp, [0x11] + le(10000000))
    target = RiscvTarget(out, inp)
    target.select(16)
    target.scan(1 << 16, 32)
    target = RiscvTarget(out, inp)  # HPM requires TLR after DTMCS before DMI.
    target.active()
    target.dmi(0x38, 0x447000)
    # Failed high-speed scans can disturb DM run control. Restore the
    # fixture's running state explicitly before the next measurement.
    target.resume()
    setup(out, inp, 10000000, 0)


def peak(mem, out, inp, pattern, loops=128, repeats=3):
    # Reset TAR per 32-command burst. Unlike the ARM AP, SBA increments
    # linearly; the transfer must stay within the backed-up 64 KiB window.
    words, depth = 512, 32
    rows = {}
    for direction in ('read', 'write'):
        rates = []
        for repeat in range(repeats + 1):
            started = time.perf_counter()
            done = 0
            while done < loops:
                count = min(depth, loops - done)
                mem.address(BASE)
                for index in range(count):
                    packet = bytes([6, 0, 0, 2, 15 if direction == 'read' else 13])
                    if direction == 'write':
                        packet += pattern[index * 2048:(index + 1) * 2048]
                    send(out, packet)
                for index in range(count):
                    reply = read_exact(inp, 2052 if direction == 'read' else 4)
                    assert reply[:4] == bytes([6, 0, 2, 1]), reply[:16].hex()
                    if direction == 'read':
                        assert reply[4:] == pattern[index * 2048:(index + 1) * 2048], 'Peak read byte mismatch'
                done += count
            elapsed = time.perf_counter() - started
            if repeat:
                rates.append(loops * words * 4 / elapsed / 1e6)
        rows[direction + '_MB_s'] = statistics.median(rates)
        rows[direction + '_repeats_MB_s'] = rates
    assert mem.read(BASE, SIZE) == pattern, 'Peak write readback mismatch'
    return dict(words=words, depth=depth, loops=loops, **rows)


def hss_point(probe, mem, dev, speed, period, nvars, seconds, expected):
    variables = [(HSS_BASE + 256 + 4 * i, 4, 4) for i in range(nvars)]
    assert probe.action(0x32, 3, struct.pack('<I', speed))[0] == 0
    config = struct.pack('<IBB', period, 0, nvars) + b''.join(struct.pack('<IBB', *v) for v in variables)
    assert probe.action(0x32, 10, config)[0] == 0
    drain_hss(dev)
    reader = HssReader(dev, expected[:nvars * 4], period, allow_duplicate_stat=True)
    reader.start()
    try:
        rc, info = probe.action(0x32, 1)
        assert rc == 0, ('HSS start', rc, info)
        time.sleep(.25)
        live = live_clock_snapshot()
        rc, first = probe.action(0x32, 11)
        assert rc == 0
        time.sleep(seconds)
        rc, last = probe.action(0x32, 11)
        assert rc == 0
        for _ in range(100):
            rc, _ = probe.action(0x32, 0)
            if rc == 0:
                break
            assert rc == -7, rc
            time.sleep(.01)
        else:
            raise RuntimeError('HSS stop timeout')
        time.sleep(.12)
        reader.quit.set()
        reader.join(2)
        assert reader.error is None and not reader.is_alive(), reader.error
        drain_hss(dev, reader.consume)
        rc, final = probe.action(0x32, 11)
        # Match the F103ZE saturation harness: STOP can expose one trailing
        # sample between the PL and firmware counter snapshots. Preserve the
        # difference explicitly; every delivered data frame is still byte checked.
        tail_delta = reader.samples - final[3]
        assert rc == 0 and abs(tail_delta) <= 1, (reader.samples, final)
        delta = [(b - a) & 0xFFFFFFFF for a, b in zip(first, last)]
        dt = delta[1] / min(24000000, live['FCLK_Hz'])
        assert delta[6] == 0, ('HSS transport errors', delta)
        return dict(service='hss', requested_clock_Hz=speed, variables=nvars, period_ticks=period,
                    effective_Hz=delta[3] / dt, produced=delta[3], skipped=delta[4],
                    skip_percent=100 * delta[4] / (delta[3] + delta[4]),
                    FCLK_Hz=live['FCLK_Hz'], actual_TCK_Hz=live['actual_link_Hz'],
                    JTAG_sampling_mode=live['JTAG_sampling_mode'],
                    errors=delta[6], data_frames_verified=reader.data_frames,
                    stat_duplicate_frames=len(reader.control_sequence_errors),
                    sample_count_match=tail_delta == 0, tail_count_delta=tail_delta,
                    all_data_frames_verified=True,
                    session_samples=reader.samples, first=first, last=last)
    finally:
        probe.action(0x32, 0)
        reader.quit.set()
        reader.join(2)
        drain_hss(dev)


def rtt_point(probe, mem, dev, out, inp, port, speed, mode, chunk, seconds):
    mem.write_word(STATE + 64, 0)
    for _ in range(100):
        if mem.word(STATE + 68) == 1:
            break
    else:
        raise RuntimeError('RTT producer stop acknowledgement missing')
    mem.write_word(STATE + 24, 0)
    mem.write(RTT, struct.pack('<16sII6I', b'SEGGER RTT', 1, 0, 0, RING, 8192, 0, 0, 0))
    setup(out, inp, speed, mode)
    reader = None
    with serial.Serial(port, 115200, timeout=.025) as com:
        com.reset_input_buffer()
        assert probe.action(0x31, 7, struct.pack('<IHBB', speed, chunk, 0, 1))[0] == 0
        rc, info = probe.action(0x31, 1, struct.pack('<IIB', RTT, 0x100, 0))
        assert rc == 0, ('RTT start', rc, info)
        reader = Reader(com)
        reader.start()
        try:
            mem.write_word(STATE + 64, 1)
            time.sleep(.3)
            live = live_clock_snapshot()
            t0 = time.perf_counter()
            rc, first = probe.action(0x31, 2)
            t0 = (t0 + time.perf_counter()) / 2
            assert rc == 0 and first[1] == RTT, (rc, first)
            received0 = reader.count
            time.sleep(seconds)
            t1 = time.perf_counter()
            rc, last = probe.action(0x31, 2)
            t1 = (t1 + time.perf_counter()) / 2
            received1 = reader.count
            assert rc == 0 and last[5] == 0, (rc, last)
            # Stop between complete publishes, without halting or changing the
            # target's CPU clock. The producer's ACK makes byte accounting exact.
            mem.write_word(STATE + 64, 0)
            for _ in range(100):
                if mem.word(STATE + 68) == 1:
                    break
            else:
                raise RuntimeError('RTT producer failed to stop')
            published = mem.word(STATE + 24) * 4
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and reader.count != published:
                assert reader.error is None, reader.error
                time.sleep(.02)
            assert probe.action(0x31, 0)[0] == 0
            time.sleep(.1)
            reader.quit.set()
            reader.join(2)
            assert reader.error is None and not reader.pending and reader.count == published, (reader.error, reader.count, published)
            return dict(service='rtt', requested_clock_Hz=speed, chunk=chunk,
                        FCLK_Hz=live['FCLK_Hz'], actual_TCK_Hz=live['actual_link_Hz'],
                        JTAG_sampling_mode=live['JTAG_sampling_mode'],
                        host_MB_s=(received1 - received0) / (t1 - t0) / 1e6,
                        probe_MB_s=((last[3] - first[3]) & 0xFFFFFFFF) / (t1 - t0) / 1e6,
                        session_bytes=published, sequence_exact=True, all_published_received=True,
                        errors=last[5], first=first, last=last)
        finally:
            mem.write_word(STATE + 64, 0)
            probe.action(0x31, 0)
            if reader:
                reader.quit.set()
                reader.join(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['memory', 'rtt', 'hss'], required=True)
    parser.add_argument('--bit', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--speeds', default='250000,1000000,10000000,15000000,20000000,25000000,30000000,40000000,50000000,60000000')
    parser.add_argument('--mode', type=int, default=0)
    parser.add_argument('--seconds', type=float, default=2)
    parser.add_argument('--port', default='COM33')
    parser.add_argument('--loops', type=int, default=128)
    parser.add_argument('--resume', action='store_true', help='Resume completed HSS speed/variable groups')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(stage=args.stage, artifacts=provenance(args.bit, args.elf), rows=[], summary=[])
    if args.resume and args.output.exists():
        assert args.stage == 'hss', '--resume is supported for HSS groups'
        previous = json.loads(args.output.read_text())
        for key in ('bit', 'elf'):
            assert previous['artifacts'][key]['sha256'] == report['artifacts'][key]['sha256']
        report = previous
        report.setdefault('resume_runs', []).append(provenance(args.bit, args.elf))
        for key in ('failure', 'restore_error', 'restore_match', 'fixture_restore_match'):
            report.pop(key, None)
    def persist():
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    def record(row):
        report['rows'].append(row)
        persist()
        print(json.dumps(row), flush=True)
    dev, out, inp = open_dap()
    probe = Probe()
    mem = Memory(out, inp)
    saved = None
    fixture_saved = None
    try:
        drain(inp)
        stop(probe, dev)
        setup(out, inp, 10000000, 0, connect=True)
        words = struct.unpack('<18I', mem.read(STATE, 72))
        assert words[0] == 0x48504D50 and words[1] == 360000000 and 355000000 < words[5] < 365000000, words
        report['target'] = dict(cpu_Hz=words[1], ahb_Hz=words[2], mchtmr_Hz=words[3], measured_cpu_Hz=words[5])
        saved = mem.read(BASE, SIZE)
        args.output.with_suffix('.backup.bin').write_bytes(saved)
        report['backup_sha256'] = hashlib.sha256(saved).hexdigest()
        speeds = [int(v) for v in args.speeds.split(',')]
        assert probe.action(0x31, 12, b'\x02')[0] == 0
        target = RiscvTarget(out, inp)
        if args.stage == 'memory':
            target.resume()
            setup(out, inp, 10000000)
            for speed in speeds:
                row = dict(service='memory_acceptance', requested_clock_Hz=speed, passed=False, attempts=[])
                for mode in (0, 1, 17, 16):
                    attempt = dict(mode=mode)
                    try:
                        setup(out, inp, speed, mode)
                        row.update(clock(out, inp))
                        for repeat in range(3):
                            data = random.Random(20261029 + speed + repeat).randbytes(4096)
                            mem.write(BASE, data)
                            assert mem.read(BASE, 4096) == data, 'Random SRAM byte mismatch'
                            assert mem.read(BASE + 3, 4093) == data[3:], 'Unaligned SRAM byte mismatch'
                        row.update(passed=True, accepted_mode=mode, verified_bytes_per_direction=12288)
                        attempt['passed'] = True
                    except Exception as exc:
                        attempt['error'] = repr(exc)
                        try:
                            attempt.update(clock(out, inp))
                        except Exception as clock_exc:
                            attempt['clock_error'] = repr(clock_exc)
                    row['attempts'].append(attempt)
                    recover_link(dev, out, inp)
                    mem.write(BASE, saved[:4096])
                    assert mem.read(BASE, 4096) == saved[:4096], 'SRAM restore failed after phase attempt'
                    if row['passed']:
                        break
                record(row)
            accepted = [r for r in report['rows'] if r.get('passed') and r['requested_clock_Hz'] >= 10000000]
            pattern = random.Random(0x5301).randbytes(SIZE)
            for row in accepted:
                speed, mode = row['requested_clock_Hz'], row['accepted_mode']
                measured = dict(service='memory_peak', target_state='running', requested_clock_Hz=speed, passed=False)
                try:
                    RiscvTarget(out, inp).resume()
                    setup(out, inp, speed, mode)
                    mem.write(BASE, pattern)
                    heartbeat_before = mem.word(STATE + 16)
                    result = peak(mem, out, inp, pattern, args.loops)
                    heartbeat_after = mem.word(STATE + 16)
                    assert heartbeat_after != heartbeat_before, 'Target fixture is not running'
                    measured.update(passed=True, heartbeat_before=heartbeat_before,
                                    heartbeat_after=heartbeat_after, **clock(out, inp), **result)
                except Exception as exc:
                    measured['error'] = repr(exc)
                    recover_link(dev, out, inp)
                record(measured)
        elif args.stage == 'rtt':
            for speed in speeds:
                for chunk in (1024, 2048):
                    for repeat in range(2):
                        setup(out, inp, speed, args.mode)
                        row = rtt_point(probe, mem, dev, out, inp, args.port, speed, args.mode, chunk, args.seconds)
                        row['repeat'] = repeat
                        record(row)
        else:
            fixture_saved = mem.read(HSS_BASE, 4096)
            fixture = random.Random(0x485353).randbytes(4096)
            for speed in speeds:
                for nvars in (1, 8):
                    if any(r['requested_clock_Hz'] == speed and r['variables'] == nvars for r in report['summary']):
                        continue
                    setup(out, inp, speed, args.mode)
                    mem.write(HSS_BASE, fixture)
                    assert mem.read(HSS_BASE, 4096) == fixture
                    expected = fixture[256:288]
                    coarse = (2400, 1200, 600, 300, 200, 120, 80, 60, 40, 24)
                    good, bad = None, None
                    local = []
                    for period in coarse:
                        row = hss_point(probe, mem, dev, speed, period, nvars, min(args.seconds, 1), expected)
                        row['tag'] = 'coarse'
                        record(row)
                        local.append(row)
                        if row['skipped'] == 0:
                            good = period
                        elif good is not None:
                            bad = period
                    if good is not None and bad is not None:
                        for _ in range(12):
                            if good - bad <= 1:
                                break
                            period = (good + bad) // 2
                            row = hss_point(probe, mem, dev, speed, period, nvars, min(args.seconds, 1), expected)
                            row['tag'] = 'refine'
                            record(row)
                            local.append(row)
                            if row['skipped'] == 0:
                                good = period
                            else:
                                bad = period
                    verified = []
                    if good is not None:
                        for margin_attempt in range(4):
                            verified = []
                            for repeat in range(3):
                                row = hss_point(probe, mem, dev, speed, good, nvars, args.seconds, expected)
                                row.update(tag='verify', repeat=repeat, margin_attempt=margin_attempt)
                                record(row)
                                verified.append(row)
                            if all(r['skipped'] == 0 for r in verified):
                                break
                            good += max(2, (good + 49) // 50)
                    report['summary'].append(dict(requested_clock_Hz=speed, variables=nvars,
                        zero_skip_period=good, stable_zero_skip=bool(verified) and all(r['skipped'] == 0 for r in verified),
                        verified_Hz=[r['effective_Hz'] for r in verified],
                        peak_effective_Hz=max(r['effective_Hz'] for r in local)))
                    persist()
    except BaseException as exc:
        report['failure'] = repr(exc)
        persist()
        raise
    finally:
        try:
            stop(probe, dev)
            recover_link(dev, out, inp)
            mem.write_word(STATE + 64, 0)
            if saved is not None:
                mem.write(BASE, saved)
                report['restore_match'] = mem.read(BASE, SIZE) == saved
                assert report['restore_match'], 'Memory benchmark window restore mismatch'
            if fixture_saved is not None:
                mem.write(HSS_BASE, fixture_saved)
                report['fixture_restore_match'] = mem.read(HSS_BASE, 4096) == fixture_saved
                assert report['fixture_restore_match']
            if args.stage == 'memory':
                RiscvTarget(out, inp).resume()
        except BaseException as exc:
            report['restore_error'] = repr(exc)
            raise
        finally:
            persist()
            probe.close()
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
