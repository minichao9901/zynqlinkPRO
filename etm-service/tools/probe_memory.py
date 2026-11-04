"""Bounded ARM MEM-AP transactions shared by native Web and service CLI.

Only normal RAM/Flash reads and SRAM writes use this path. MMIO continues to
use explicit register transactions, without speculative reads or write replay.
Every block establishes SELECT/CSW/TAR and drains posted writes before moving.
"""
import struct


class MemoryTransferError(RuntimeError):
    pass


def transfer(exchange, *, address, length=None, data=None, ap=0, csw=0x23000052, check=lambda: None):
    writing = data is not None
    if writing:
        data = bytes(data)
        length = len(data)
    if (type(address) is not int or type(length) is not int or type(ap) is not int or
            not 0 <= ap <= 255 or not 0 < length <= 262144 or not 0 <= address <= 0xffffffff or
            address + length > 0x100000000):
        raise ValueError('无效内存地址、长度或AP')
    if type(csw) is not int or not 0<=csw<=0xffffffff or csw & 0x37 != 0x12:
        raise ValueError('CSW必须使用目标已确认的32位单次递增配置')
    end = address + length
    # No peripheral/PPB/system-memory accesses or aliases guessed as RAM.
    if writing:
        if not 0x20000000 <= address < end <= 0x40000000:
            raise ValueError('批量写仅允许SRAM；寄存器请使用显式DAP命令')
    elif not (0x08000000 <= address < end <= 0x10000000 or
              0x20000000 <= address < end <= 0x40000000):
        raise ValueError('批量读仅允许Flash/SRAM')
    def command(request, expected):
        check()
        reply = bytes(exchange(bytes(request)))
        if not reply.startswith(expected):
            raise MemoryTransferError('DAP批量内存事务失败；未重放，目标可能已部分更新')
        return reply
    def address_at(at):
        ops = bytearray([5, 0, 3])
        for req, value in ((8, ap << 24), (1, csw), (5, at)):
            ops += bytes([req]) + struct.pack('<I', value)
        command(ops, b'\x05\x03\x01')
    def read_aligned(at, size):
        result = bytearray()
        while size:
            n = min(size, 1024 - (at & 1023))
            address_at(at)
            count = n // 4
            expected = struct.pack('<BHB', 6, count, 1)
            reply = command(struct.pack('<BBHB', 6, 0, count, 15), expected)
            if len(reply) != 4 + n:
                raise MemoryTransferError('DAP内存响应长度错误；未补零或重试')
            result += reply[4:]
            at += n
            size -= n
        return bytes(result)
    start = address & ~3
    limit = (end + 3) & ~3
    if not writing:
        return read_aligned(start, limit-start)[address-start:address-start+length]
    # Preserve only boundary bytes; never read an entire aligned write first.
    payload = bytearray(limit-start)
    if start != address:
        payload[:4] = read_aligned(start, 4)
    if end != limit:
        payload[-4:] = read_aligned(limit-4, 4)
    payload[address-start:address-start+length] = data
    at = start
    while at < limit:
        n = min(limit-at, 1024-(at & 1023))
        address_at(at)
        command(struct.pack('<BBHB', 6, 0, n//4, 13) + payload[at-start:at-start+n],
                struct.pack('<BHB', 6, n//4, 1))
        # Completion barrier, no read of the target address and no retry.
        command(b'\x05\x00\x01\x0e', b'\x05\x01\x01')
        at += n
    return length
