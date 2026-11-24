"""Receive the packaged F103ZE SPI1 master fixture on the fusion J7."""
import json
import struct
import time

from fusion_evidence import compare_pattern
from fusion_fixture import confirm_spi_route, read_bytes, target_io
from h743_spi_accept import CHANNEL, spi_config
from selectio_native import native_connection


def pattern(seed, count):
    data = bytearray()
    for _ in range(count):
        seed = (1664525*seed + 1013904223) & 0xffffffff
        data.append(seed >> 24)
    return data


def run_f103_tx(case, image, serial, args, out):
    p = case['parameters']
    pclk = case['clock']['hclkMHz'] * 500000
    divisors = {pclk >> (index + 1): index for index in range(8)}
    if args.rate not in divisors:
        raise ValueError('Requested SPI1 master rate does not match an APB2 divider')
    length = 4096
    settings = {'g_spi_role': 1, 'g_spi_mode': args.spi_mode, 'g_spi_div': divisors[args.rate],
                'g_spi_length': length, 'g_spi_delay_ms': 5000, 'g_spi_timeout_ms': 10000,
                'g_spi_tx_seed': p['payloadSeed'], 'g_spi_stream_ms': p['seconds']*1000}
    status_names = ('g_spi_status', 'g_spi_wire_hz', 'g_spi_rx_hash', 'g_spi_rx_bytes')
    buffers = ('g_spi_tx', 'g_spi_rx')
    expected = out / 'spi-pattern.bin'
    expected.write_bytes(pattern(p['payloadSeed'], length))
    rows = []

    def connect():
        return target_io('f103ze', serial, 'swd')

    with connect() as io:
        if image.word(io, 'g_spi_status') == 1 or image.word(io, 'g_spi_arm'):
            raise RuntimeError('SPI1 target is already armed')
        old = {name: image.word(io, name) for name in (*settings, *status_names)}
        backup = {}
        for name in buffers:
            backup[name] = read_bytes(io, image.address(name), length)
            (out / f'{name}-before.bin').write_bytes(backup[name])
        (out / 'spi-target-before.json').write_text(json.dumps(old), encoding='utf8')

    deadline = 0
    route = 'swd'
    try:
        for number in range(1, p['rounds'] + 1):
            raw = out / f'spi-{number}.bin'
            with connect() as io:
                for name, value in settings.items():
                    image.set_word(io, name, value)
                armed = time.monotonic()
                deadline = armed + 5 + p['seconds'] + 2
                io.write_word(image.address('g_spi_arm'), 1)
            route = 'unknown'
            confirm_spi_route('spi')
            route = 'spi'
            with native_connection(serial) as probe, raw.open('xb') as stream:
                probe.info()
                probe.exchange(CHANNEL, 0, spi_config(3, args.spi_mode, args.rate, tap=args.tap))
                try:
                    if time.monotonic() >= armed + 5:
                        raise RuntimeError('Receiver was not armed before the F103ZE transmit window')
                    while time.monotonic() < deadline:
                        block = probe.exchange(CHANNEL, 1)
                        stream.write(block)
                        if not block:
                            time.sleep(.001)
                    probe.exchange(CHANNEL, 3)
                    while block := probe.exchange(CHANNEL, 1):
                        stream.write(block)
                    state = struct.unpack('<5I', probe.exchange(CHANNEL, 4))
                finally:
                    probe.exchange(CHANNEL, 5)
            route = 'unknown'
            confirm_spi_route('swd')
            route = 'swd'
            with connect() as io:
                source = {name: image.word(io, name) for name in status_names}
            data = compare_pattern(raw, expected)
            if any(state[:3]) or source['g_spi_status'] != 6 or source['g_spi_wire_hz'] != args.rate:
                raise RuntimeError(f'F103 SPI source, link or STOP failed: {source}, {state}')
            if data['bytes'] != source['g_spi_rx_bytes']:
                raise RuntimeError(f'F103 SPI target and host byte counts differ: {source}, {data}')
            rows.append({'round': number, 'transfer_seconds': p['seconds'], 'source': source, 'probe': state, **data})
            (out / 'spi-windows.json').write_text(json.dumps(rows, indent=2), encoding='utf8')
    finally:
        if route != 'swd':
            # Until the fixture's bounded autonomous transfer ends, leave SWD isolated.
            time.sleep(max(0, deadline-time.monotonic()))
            confirm_spi_route('swd')
        with connect() as io:
            while image.word(io, 'g_spi_status') == 1 or image.word(io, 'g_spi_arm'):
                if time.monotonic() >= deadline:
                    raise RuntimeError('F103 SPI bus release not confirmed. Keep the SRAM backup.')
                time.sleep(.1)
            for name, payload in backup.items():
                address = image.address(name)
                io.write(address, payload)
                if read_bytes(io, address, length) != payload:
                    raise RuntimeError(f'F103 SPI restoration differs for {name}')
            for name, value in old.items():
                image.set_word(io, name, value)
            (out / 'spi-restoration.json').write_text(json.dumps({'mailboxes': True, 'buffers': True}), encoding='utf8')
    return {'windows': rows, 'remaining': ['Attach physical SCK/NSS and wiring restoration evidence.']}
