"""Exercise the SRAM, RTT and J-Scope modes of an already loaded fusion target."""
import csv
import json
import struct

from fusion_acceptance import TOOLBOX, run_capture
from fusion_evidence import Blocked, u32_sequence
from fusion_fixture import read_bytes, target_io


# The rounded PS reference can yield 99,999,998 Hz for the 100 MHz profile.
CLOCK_TOLERANCE_HZ = 2


def matching_clock(actual, requested):
    if actual is None or abs(actual - requested) > CLOCK_TOLERANCE_HZ:
        raise Blocked(f'Clock readback {actual} differs from requested {requested} Hz')


def matching_rtt_clock(reported_mhz, requested_hz):
    low = (requested_hz - CLOCK_TOLERANCE_HZ) // 1_000_000
    high = (requested_hz + CLOCK_TOLERANCE_HZ) // 1_000_000
    if not low <= reported_mhz <= high:
        raise Blocked(f'RTT integer-MHz clock {reported_mhz} differs from requested {requested_hz} Hz')


def check_scope(csv_path, channels):
    groups = changed = torn = 0
    previous = None
    with csv_path.open(newline='', encoding='utf8') as stream:
        rows = csv.reader(stream)
        next(rows)
        for row in rows:
            _, *values = map(int, row)
            if len(values) != channels:
                raise ValueError('Unexpected column count in sample')
            tick = values[0]
            groups += 1
            changed += previous is not None and tick != previous
            previous = tick
            if channels == 8:
                expected = [tick, ~tick & 0xffffffff, tick % 100,
                            1000 if tick % 10 < 5 else (-1000 & 0xffffffff),
                            (tick * 0x9e3779b9) & 0xffffffff, int(tick % 2000 < 100),
                            0x80000000 | (tick & 0xffff), tick]
                if tick == values[-1] and tick and values != expected:
                    raise ValueError(f'Dynamic waveform values differ at target tick {tick}')
                torn += tick != values[-1]
    if not groups or not changed or torn == groups:
        raise RuntimeError('Scope capture is missing a changing coherent workload')
    return {'groups': groups, 'changes': changed, 'torn_groups': torn}


def check_subword_access(mem, edge):
    from dap_pipeline_bench import le

    first = edge - 4
    original = mem.read(first, 8)
    rows = []
    try:
        for width, code in ((1, 0), (2, 1)):
            for at in (edge-width, edge, edge+width):
                pos = at-first
                expected = bytearray(mem.read(first, 8))
                value = (int.from_bytes(expected[pos:pos+width], 'little') ^ 0xa35c) & ((1 << (8*width))-1)
                lane = 8*(at & 3)
                setup = bytes([5, 0, 3, 8, *le(0), 1, *le(0x23000050 | code), 5, *le(at)])
                if mem.transfer(setup) != b'\x05\x03\x01':
                    raise RuntimeError(f'Cannot configure {width*8}-bit AP access')
                if mem.transfer(bytes([5, 0, 1, 13, *le(value << lane)])) != b'\x05\x01\x01':
                    raise RuntimeError(f'{width*8}-bit AP write failed')
                if mem.transfer(setup) != b'\x05\x03\x01':
                    raise RuntimeError('Cannot reset TAR before byte/halfword read')
                response = mem.transfer([5, 0, 1, 15])
                expected[pos:pos+width] = value.to_bytes(width, 'little')
                if len(response) != 7 or response[:3] != b'\x05\x01\x01' or \
                        (int.from_bytes(response[3:], 'little') >> lane) & ((1 << (8*width))-1) != value:
                    raise RuntimeError(f'{width*8}-bit AP readback failed')
                if mem.read(first, 8) != expected:
                    raise RuntimeError('Neighboring bytes changed during a subword write')
                rows.append({'address': hex(at), 'width': width, 'value': value})
    finally:
        mem.write(first, original)
        if mem.read(first, 8) != original:
            raise RuntimeError('AP byte/halfword scratch could not be restored')
    return rows


def run_sram(case, image, serial, args, out):
    from dap_pipeline_bench import cmd, setup
    from selectio_cli import connection, PORTS
    from selectio_native import native_connection
    from selectio_pipeline_bench import measure_window
    from test_probe_board import Memory

    p = case['parameters']
    size = p['payloadBytes']
    transport = 'jtag' if args.transport == 'arm-jtag' else 'swd'
    with connection(serial) as (tx, rx), native_connection(serial, tx.device) as native:
        setup(tx, rx, 1000, transport)
        mem = Memory(tx, rx)
        base = image.address('g_perf_sram') + 32
        extent = image.word(mem, 'g_perf_sram_bytes')
        address = ((base + 4 + 1023) & ~1023) + p['offsetFromAlignedPage']
        if address + size + 4 > base + extent:
            raise ValueError('Cross-page transfer exceeds the fixture scratch space')
        original = read_bytes(mem, base - 32, extent + 64)
        if read_bytes(mem, base - 32, extent + 64) != original:
            raise RuntimeError('Unstable scratch backup')
        (out / 'scratch-before.bin').write_bytes(original)
        rows = []
        try:
            subword = check_subword_access(mem, (address + 1023) & ~1023)
            (out / 'sram-subword.json').write_text(json.dumps(subword, indent=2), encoding='utf8')
            seq = 0
            for round_no in range(1, p['rounds'] + 1):
                for direction in p['directions']:
                    pattern = bytes((i * 31 + round_no) & 255 for i in range(size))
                    info = native.info()
                    native.set_frame_size(4096)
                    if native.max_depth < p['depth']:
                        raise RuntimeError('Probe did not negotiate planned pipeline depth')
                    with native.memory(PORTS[transport], args.tap, args.slot, args.idle, args.rate):
                        native.bulk(address, size, pattern)
                        if native.bulk(address, size) != pattern:
                            raise RuntimeError('Scratch prefill mismatch')
                        start = native.memory_stats()
                        n, wall, usb, seq, final = measure_window(
                            native, direction, address, size, p['depth'], p['seconds'], round_no, seq, pattern)
                        end = native.memory_stats()
                        clock = native.memory_clock(PORTS[transport], info['reference_hz'], args.rate)
                        matching_clock(clock['wire_hz'], args.rate)
                    setup(tx, rx, 1000, transport)
                    if read_bytes(mem, address, size) != final:
                        raise RuntimeError('Physical SRAM readback mismatch')
                    payload = n * size
                    written = {'read': 0, 'write': payload, 'mixed': payload // 2}[direction]
                    if (end['read_bytes']-start['read_bytes'], end['write_bytes']-start['write_bytes']) != (payload-written,written):
                        raise RuntimeError('Native queue byte counters differ')
                    row = dict(round=round_no, direction=direction, requests=n, payload_bytes=payload,
                               seconds=wall, usb_seconds=usb, MBps=payload/wall/1e6, clock=clock)
                    rows.append(row)
                    with (out / 'sram-windows.jsonl').open('a', encoding='utf8') as log:
                        log.write(json.dumps(row) + '\n')
        finally:
            try:
                setup(tx, rx, 1000, transport)
                before = read_bytes(mem, base - 32, extent + 64)
                offset = address - base + 32
                unmodified = before[:offset] == original[:offset] and before[offset+size:] == original[offset+size:]
                mem.write(base - 32, original)
                restored = read_bytes(mem, base - 32, extent + 64) == original
                (out / 'sram-restoration.json').write_text(json.dumps(
                    {'scratch_restored': restored, 'surrounding_bytes_untouched': unmodified}), encoding='utf8')
                if not restored or not unmodified:
                    raise RuntimeError('SRAM restoration or bounds check failed')
            finally:
                cmd(tx, rx, [3])
    return {'windows': rows, 'remaining': ['Aggregate all link rates and compare verified SRAM throughput.']}


def run_stream(case, image, serial, args, out):
    from selectio_scope import export_scope

    runner = case['runner']
    p = case['parameters']
    transport = 'swd' if args.transport == 'swd' else 'jtag'
    link = ['--transport', transport, '--clock', str(args.rate)]
    if args.transport == 'riscv-jtag':
        link.append('--riscv')
    else:
        link.extend(('--tap', str(args.tap), '--slot', str(args.slot), '--idle', str(args.idle)))
    root = [*TOOLBOX, 'selectio', '--serial', serial]
    rtt = image.address('_SEGGER_RTT')
    scope = image.address('g_scope')
    rows = []
    def connect():
        return target_io(case['board'], serial, args.transport)

    def rtt_state(io):
        ring_size, write, read = struct.unpack('<III', read_bytes(io, rtt+32, 12))
        if ring_size != p['ringBytes'] or max(write, read) >= ring_size:
            raise RuntimeError('RTT ring descriptor differs')
        return image.word(io, 'g_rtt_published'), (write-read) % ring_size

    with connect() as io:
        if image.word(io, 'g_mode') != 0 or image.word(io, 'g_rtt_use_pattern'):
            raise RuntimeError('Start with a fresh idle fixture and sequence RTT mode')
        if rtt_state(io)[1]:
            raise RuntimeError('Old bytes remain in the RTT ring')
    try:
        for n in range(1, p['rounds'] + 1):
            with connect() as io:
                before, old_tail = rtt_state(io)
                image.set_word(io, 'g_mode', p['firmwareMode'])
            name = f'{runner}-{n}'
            raw = out / f'{name}.bin'
            waveform = out / f'{name}.csv'
            flags = [*link, '--seconds', str(p['seconds'])]
            addresses = [scope + 4*i for i in range(args.channels or 0)]
            ticks = 24000000 // args.group_rate if args.group_rate else 0
            if runner == 'rtt':
                command = ['rtt', *flags, '--address', hex(rtt), '--chunk', str(p['chunkBytes']), '--out', str(raw)]
            elif runner == 'scope':
                command = ['scope', *flags, '--period', str(ticks), '--out', str(raw)]
                for address in addresses:
                    command.extend(('--var', f'{address:#x}:4:4'))
            else:
                command = ['combo', *flags, '--ticks', str(ticks), '--rtt-address', hex(rtt),
                           '--rtt-out', str(raw), '--scope-out', str(waveform)]
                for address in addresses:
                    command.extend(('--var', hex(address)))
            status = json.loads(run_capture([*root, *command], out, name))
            row = {'round': n, 'probe': status}
            with connect() as io:
                image.set_word(io, 'g_mode', 0)
                after, new_tail = rtt_state(io)
            if runner in ('rtt', 'combo'):
                row['sequence'] = u32_sequence(raw)
                count = row['sequence']['bytes']
                if (after-before+old_tail-new_tail) & 0xffffffff != count:
                    raise RuntimeError('RTT producer, host and unread ring counts differ')
                if rows and rows[-1]['sequence']['next'] != row['sequence']['first']:
                    raise RuntimeError('RTT sequence has a gap between rounds')
                row['target_rtt'] = {'published': (after-before) & 0xffffffff, 'unread_after_stop': new_tail}
            if runner == 'rtt':
                state = status['status']
                if state[3] != count or state[5] or state[10]:
                    raise RuntimeError(f'RTT STOP counters differ: {state}')
                row['reported_integer_mhz'] = state[11] >> 24
                matching_rtt_clock(row['reported_integer_mhz'], args.rate)
            if runner == 'scope':
                stats = export_scope(raw, waveform)
                matching_clock(stats['definition']['link_hz'], args.rate)
                if stats['definition']['period_ticks'] != ticks:
                    raise RuntimeError('Scope period readback differs')
                skipped = stats['stat']['skipped']
            if runner == 'combo':
                matching_clock(status.get('clock', {}).get('wire_hz'), args.rate)
                if status['period_ticks'] != ticks:
                    raise RuntimeError('Combo period readback differs')
                skipped = status['skipped_groups']
            if runner in ('scope', 'combo'):
                row['waveform'] = check_scope(waveform, args.channels)
                if skipped / (row['waveform']['groups'] + skipped) >= p['maxSkippedFractionExclusive']:
                    raise RuntimeError(f'Skipped {skipped} sample groups above the limit')
            rows.append(row)
    finally:
        with connect() as io:
            image.set_word(io, 'g_mode', 0)
            (out / 'mode-restoration.txt').write_text('g_mode=0 verified\n', encoding='utf8')
    remaining = ['Attach precise RTT wire clock evidence; the RTT control response only reports integer MHz.'] if runner == 'rtt' else []
    return {'windows': rows, 'remaining': remaining}
