"""Run byte-checked physical UART echo over the selected J7 CDC port."""
import json
import time

from fusion_acceptance import TOOLBOX, run_capture
from fusion_fixture import target_io

UART_WORDS = ('g_uart_baud_request', 'g_uart_baud', 'g_uart_mode', 'g_uart_config_errors',
              'g_uart_rx', 'g_uart_tx', 'g_uart_rx_errors', 'g_uart_rx_hash')


def fnv1a(data, state):
    for octet in data:
        state = ((state ^ octet) * 16777619) & 0xffffffff
    return state


def run_uart(case, image, serial, args, out):
    from serial import Serial
    from serial.tools.list_ports import comports

    p = case['parameters']
    ports = [port.device for port in comports()
             if (port.vid, port.pid, port.serial_number) == (0x0d28, 0x0204, serial)]
    if len(ports) != 1:
        raise RuntimeError(f'Expected one J7 CDC port for {serial}, found {ports}')

    def state():
        with target_io(case['board'], serial) as io:
            return {key: image.word(io, key) for key in UART_WORDS}

    def set_baud(baud):
        with target_io(case['board'], serial) as io:
            image.set_word(io, 'g_uart_baud_request', baud)
            end = time.monotonic() + 1
            while image.word(io, 'g_uart_baud') != baud:
                if time.monotonic() >= end:
                    raise RuntimeError(f'Target did not accept baud {baud}')

    initial = state()
    if initial['g_uart_mode'] != 0 or initial['g_uart_baud_request'] != initial['g_uart_baud']:
        raise RuntimeError('Prepare the target in idle echo mode first')
    rows = []
    root = [*TOOLBOX, 'selectio', '--serial', serial, 'com']
    bound = False
    try:
        set_baud(args.rate)
        for number in range(1, p['rounds'] + 1):
            before = state()
            count = 0
            expected_hash = before['g_uart_rx_hash']
            aux_before = json.loads(run_capture([*root, 'bind'], out, f'bind-{number}'))
            bound = True
            try:
                with Serial(ports[0], args.rate, timeout=2, write_timeout=2) as com, \
                        (out / f'echo-{number}-tx.bin').open('xb') as raw_tx, \
                        (out / f'echo-{number}-rx.bin').open('xb') as raw_rx:
                    com.reset_input_buffer()
                    start = time.monotonic()
                    while time.monotonic()-start < p['seconds']:
                        for length in p['edgeBytes']:
                            payload = bytes((j * 31 + count) & 255 for j in range(length))
                            if com.write(payload) != length:
                                raise RuntimeError('Short UART write')
                            echoed = com.read(length)
                            raw_tx.write(payload)
                            raw_rx.write(echoed)
                            if echoed != bytes(b ^ 0xa5 for b in payload):
                                raise RuntimeError(f'UART echo mismatch after {count} bytes')
                            expected_hash = fnv1a(payload, expected_hash)
                            count += length
                    elapsed = time.monotonic()-start
                    aux_after = json.loads(run_capture([*root, 'status'], out, f'com-status-{number}'))
                    if (aux_after['binding'] != 'uart' or aux_after['baud'] != args.rate
                            or any(aux_after[key] != aux_before[key] for key in ('overflow', 'framing_errors'))):
                        raise RuntimeError(f'Probe UART readback or errors differ: {aux_after}')
            finally:
                run_capture([*root, 'release'], out, f'release-{number}')
                bound = False
            after = state()
            if (after['g_uart_rx']-before['g_uart_rx']) & 0xffffffff != count or \
                    (after['g_uart_tx']-before['g_uart_tx']) & 0xffffffff != count or \
                    after['g_uart_rx_hash'] != expected_hash or \
                    any(after[key] != before[key] for key in ('g_uart_rx_errors', 'g_uart_config_errors')):
                raise RuntimeError(f'UART target counters or FNV-1a differ: {before} -> {after}')
            rows.append({'round': number, 'baud_requested': args.rate, 'bytes_each_direction': count,
                         'seconds': elapsed, 'payload_Bps': count / elapsed, 'before': before, 'after': after,
                         'probe_before': aux_before, 'probe_after': aux_after})
            (out / 'uart-windows.json').write_text(json.dumps(rows, indent=2), encoding='utf8')
    finally:
        if bound:
            run_capture([*root, 'release'], out, 'release-on-error')
        set_baud(initial['g_uart_baud'])
        (out / 'uart-restoration.json').write_text(json.dumps(state(), indent=2), encoding='utf8')
    return {'windows': rows, 'remaining': ['Measure the physical baud and run the three sustained direction cases.']}
