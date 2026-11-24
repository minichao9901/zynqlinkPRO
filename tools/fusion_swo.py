"""Capture real F103ZE ITM output from the versioned target fixture."""
import struct
import time

from fusion_evidence import compare_pattern
from fusion_fixture import read_bytes, target_io
from selectio_cmsis_swo import cmsis_swo
from selectio_f103_swo import f103_swo


def capture(source, stream, count, start):
    start()
    deadline = time.monotonic() + 60
    while stream.tell() < count and time.monotonic() < deadline:
        stream.write(source.pull())
    source.stop()
    deadline = time.monotonic() + 3
    while True:
        stream.write(source.pull())
        state = source.status()
        if not state['pending'] and state['index'] == stream.tell():
            break
        if time.monotonic() > deadline or state['status']:
            raise RuntimeError(f'SWO STOP counters differ: {state}')
    if state['status'] or stream.tell() != count:
        raise RuntimeError(f'SWO capture has {stream.tell()} bytes, expected {count}: {state}')
    return state


def check_receiver_rate(source, requested):
    if abs(source.rate - requested) > requested / 100:
        raise RuntimeError(f'SWO receive rate {source.rate} differs from requested {requested} by more than 1%')


def verify_itm(path, start, count, port):
    packet = struct.Struct('<BI')
    end = start + count
    with path.open('rb') as raw:
        for index in range(start, end):
            data = raw.read(packet.size)
            want = (index * 0x9e3779b9 & 0xffffffff) ^ 0xa55aa55a
            if len(data) != packet.size or packet.unpack(data) != (port * 8 + 3, want):
                raise ValueError(f'ITM stimulus packet differs at index {index}')
        if raw.read(1):
            raise ValueError('Unexpected bytes after last ITM packet')


def run_itm(case, image, serial, args, out):
    p = case['parameters']
    port = p['port']
    rows = []
    with f103_swo(serial, args.encoding, args.rate, 1 << port, expected_cfgr=0x0011c40a,
                  swd_khz=case['clock']['requestedHz']//1000) as target:
        io = target.memory
        request = image.word(io, 'g_itm_request')
        old_port = image.word(io, 'g_itm_port')
        if request != image.word(io, 'g_itm_sent'):
            raise RuntimeError('Wait for the current ITM request to finish')
        try:
            image.set_word(io, 'g_itm_port', port)
            for round_no in range(1, p['rounds'] + 1):
                start = image.word(io, 'g_itm_sent')
                end = start + p['words']
                if end > 0xffffffff:
                    raise ValueError('Restart the target before ITM request counter wraps')
                raw = out / f'itm-{round_no}.bin'
                with cmsis_swo(*target.endpoints, args.encoding, args.rate) as source, raw.open('xb') as stream:
                    check_receiver_rate(source, args.rate)
                    target.start()
                    state = capture(source, stream, p['words']*5, lambda: image.set_word(io, 'g_itm_request', end))
                    if image.word(io, 'g_itm_sent') != end:
                        raise RuntimeError(f'ITM source failed to complete: {state}')
                verify_itm(raw, start, p['words'], port)
                rows.append({'round': round_no, 'words': p['words'], 'baud_readback': source.rate, **state})
        finally:
            image.set_word(io, 'g_itm_request', request)
            image.set_word(io, 'g_itm_port', old_port)
    return {'windows': rows, 'remaining': ['Attach the physical source clock measurement for this rate.']}


def run_dma_source(case, image, serial, args, out):
    p = case['parameters']
    settings = ('g_source_mode', 'g_source_repeats', 'g_source_ticks')
    symbol_rate = args.rate * (2 if args.encoding == 'manchester' else 1)
    ticks, remainder = divmod(case['clock']['hclkMHz'] * 1_000_000, symbol_rate)
    if remainder or not 16 <= ticks <= 65535:
        raise ValueError('Requested source rate needs an exact TIM2 divisor between 16 and 65535')
    count = p['payloadBytes'] * p['repeats']
    rows = []
    with target_io(case['board'], serial, 'swd') as io:
        if image.word(io, 'g_source_request') or image.word(io, 'g_source_status') == 1:
            raise RuntimeError('The target DMA source is active')
        original = {name: image.word(io, name) for name in settings}
        pattern = out / 'target-payload.bin'
        expected = bytearray()
        value = 1
        for _ in range(p['payloadBytes']):
            value = (1664525 * value + 1013904223) & 0xffffffff
            expected.append(value >> 24)
        if read_bytes(io, image.address('g_source_payload'), p['payloadBytes']) != expected:
            raise RuntimeError('Target DMA payload differs from the fixture pattern')
        pattern.write_bytes(expected)
        try:
            image.set_word(io, 'g_source_mode', int(args.encoding == 'manchester'))
            image.set_word(io, 'g_source_repeats', p['repeats'])
            image.set_word(io, 'g_source_ticks', ticks)

            def start():
                # The running target can consume the request before host readback.
                io.write_word(image.address('g_source_request'), p['payloadBytes'])

            for number in range(1, p['rounds'] + 1):
                raw = out / f'dma-{number}.bin'
                with cmsis_swo(io.out, io.inp, args.encoding, args.rate) as source, raw.open('xb') as stream:
                    check_receiver_rate(source, args.rate)
                    state = capture(source, stream, count, start)
                status = image.word(io, 'g_source_status')
                sent = image.word(io, 'g_source_sent')
                readback = image.word(io, 'g_source_symbol_hz')
                if (status, sent, readback) != (2, count, symbol_rate):
                    raise RuntimeError(f'DMA source status/bytes/symbol rate differ: {status}/{sent}/{readback}')
                rows.append({'round': number, 'receiver_rate': source.rate, 'source_symbol_hz': readback,
                             'probe': state, **compare_pattern(raw, pattern)})
        finally:
            io.write_word(image.address('g_source_request'), 0)
            deadline = time.monotonic() + 2
            while image.word(io, 'g_source_status') == 1:
                if time.monotonic() > deadline:
                    raise RuntimeError('Target DMA source did not stop')
            for name, value in original.items():
                image.set_word(io, name, value)
    return {'windows': rows, 'remaining': ['Attach physical SWO symbol clock and wiring restoration evidence.']}
