"""Characterise the JTAG AP write path: which words of a multi-word write land."""
import sys
import time

sys.path.insert(0, r'E:\zynqlinkPRO\tools')
from dap_pipeline_bench import open_dap, setup, xfer, le

CSW = 0x23000052


def addr_pkt(addr):
    return [5, 0, 3, 8] + le(0) + [1] + le(CSW) + [5] + le(addr)


def write_words(out, inp, addr, words, csw=CSW):
    packet = [5, 0, 3, 8] + le(0) + [1] + le(csw) + [5] + le(addr)
    r = xfer(out, inp, bytes(packet))
    assert r == b'\x05\x03\x01', r.hex(' ')
    reply = xfer(out, inp, bytes([6, 0, len(words) & 255, len(words) >> 8, 0x0D])
                 + b''.join(w.to_bytes(4, 'little') for w in words))
    return reply.hex(' ')


def read_words(out, inp, addr, count, csw=CSW):
    packet = [5, 0, 3, 8] + le(0) + [1] + le(csw) + [5] + le(addr)
    r = xfer(out, inp, bytes(packet))
    assert r == b'\x05\x03\x01', r.hex(' ')
    reply = xfer(out, inp, bytes([6, 0, count & 255, count >> 8, 0x0F]))
    return [int.from_bytes(reply[4 + 4 * i:8 + 4 * i], 'little') for i in range(count)]


dev, out, inp = open_dap()
for attempt in range(6):
    try:
        setup(out, inp, 50000, 'jtag')
        print('setup ok on attempt', attempt + 1)
        break
    except Exception as exc:
        print('setup retry', attempt + 1, exc)
        time.sleep(0.5)
else:
    raise SystemExit('setup never worked')

base = 0x20000200
for n in range(1, 9):
    pattern = [0x11110000 + i * 0x0101 for i in range(n)]
    reply = write_words(out, inp, base, pattern)
    back = read_words(out, inp, base, n)
    good = [i for i in range(n) if back[i] == pattern[i]]
    print(f'write {n} words reply={reply[:12]} landed={good} back={[hex(v) for v in back]}')
