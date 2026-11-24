"""Verify one prepared Flash A/B or RAM boot signature without writing storage."""
import json
import struct
import time

from fusion_fixture import read_bytes


def verify_boot(case, image, alias, io):
    expected = {'dbg-a': 0x44424741, 'dbg-b': 0x44424742, 'dbg-ram': 0x44424752}[alias]
    actual = image.word(io, 'g_boot_id')
    initialized = image.word(io, 'g_boot_data_verified')
    first = image.word(io, 'g_ticks')
    time.sleep(0.03)
    second = image.word(io, 'g_ticks')
    if (actual, initialized) != (expected, 1) or first == second:
        raise RuntimeError(f'Boot signature, initialized data or progress differs: {actual:#x}, {initialized}, {first}/{second}')
    return {'boot_id': f'{actual:#010x}', 'initialized_data': initialized, 'ticks': [first, second],
            'remaining': [case['pass']]}


def verify_rtt_terminal(case, image, io, out):
    cb = image.address('_SEGGER_RTT')

    def channel(offset):
        data, size, write, read = struct.unpack('<4I', read_bytes(io, cb + offset + 4, 16))
        if not 64 <= size <= 16384 or size & (size - 1) or max(write, read) >= size:
            raise RuntimeError('Invalid RTT descriptor')
        return data, size, write, read

    def advance(offset, value):
        io.write(cb + offset, struct.pack('<I', value))

    def exchange(command, reply):
        payload = command.encode('ascii') + b'\n'
        buf, size, write, read = channel(48)
        if write != read or len(payload) >= size:
            raise RuntimeError('RTT DOWN is not idle')
        for index, byte in enumerate(payload):
            io.write(buf + (write+index) % size, bytes([byte]))
        advance(60, (write+len(payload)) % size)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            buf, size, write, read = channel(24)
            if write == read:
                time.sleep(.005)
                continue
            count = (write-read) % size
            first = min(count, size-read)
            actual = read_bytes(io, buf+read, first)
            if count > first:
                actual += read_bytes(io, buf, count-first)
            if actual != reply + b'\r\n':
                raise RuntimeError(f'RTT {command!r} returned {actual!r}')
            advance(40, write)
            return actual.decode('ascii').rstrip()
        raise RuntimeError(f'RTT {command!r} timed out')

    if read_bytes(io, cb, 10) != b'SEGGER RTT' or image.word(io, 'g_rtt_binary_echo'):
        raise RuntimeError('Target is not ready for ASCII terminal commands')
    for offset in (24, 48):
        _, _, write, read = channel(offset)
        if write != read:
            raise RuntimeError('Prepare empty RTT rings before the terminal test')
    version = read_bytes(io, image.address('g_build_id'), 64).split(b'\0', 1)[0]
    commands = {'help': b'help version echo <text>', 'version': version, 'echo fixture': b'fixture'}
    count = 0
    with (out / 'rtt-terminal.jsonl').open('x', encoding='utf8') as log:
        for repeat in range(1, case['parameters']['repeats'] + 1):
            for command in case['parameters']['commandReplies']:
                result = exchange(command, commands[command])
                log.write(json.dumps({'round': repeat, 'command': command, 'reply': result}) + '\n')
                log.flush()
                count += 1
    for offset in (24, 48):
        _, _, write, read = channel(offset)
        if write != read:
            raise RuntimeError('RTT rings are not empty after command round trip')
    return count
