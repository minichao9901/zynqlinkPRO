"""Data-checked raw CMSIS-DAP DRW streaming, separate from linear SRAM APIs.

Detects the auto-increment wrap window on F103. Repeated data follow the TAR
offset, so arbitrary packet lengths do not silently invalidate the test. The
original window is backed up and restored. No target reset/flash programming.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import time

import usb.core
import usb.util
from dap_pipeline_bench import open_dap, setup, send, xfer, le

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed', type=int, default=60000, help='SWCLK kHz')
    ap.add_argument('--words', type=int, default=1022)
    ap.add_argument('--loops', type=int, default=500)
    ap.add_argument('--depths', default='1,4,16')
    ap.add_argument('--ack-hold',type=int,choices=range(8),
                    help='Diagnostic ACK capture hold, applied AFTER Connect resets CFG')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    depths = [int(x) for x in a.depths.split(',')]
    if not 1 <= a.words <= 1022 or not all(1 <= x <= 16 for x in depths) or a.loops < 1:
        ap.error('words 1..1022, depths 1..16 and positive loops required')
    d, out, inp = open_dap()
    backup = None
    modified = False
    result = {'kind': 'raw_DRW_stream_auto_increment_wrap', 'speed_kHz': a.speed,
              'words': a.words, 'loops': a.loops, 'rows': [], 'restore_match': False}

    def write_reg(req, value):
        r = xfer(out, inp, [5, 0, 1, req]+le(value))
        if r[:3] != bytes([5, 1, 1]):
            raise RuntimeError(f'Register write failed: {r.hex()}')

    def tar(address):
        write_reg(5, address)

    def check_block(r, n, reading):
        if r[:4] != bytes([6, n & 255, n >> 8, 1]) or len(r) != (4+4*n if reading else 4):
            raise RuntimeError(f'Invalid block response {r[:16].hex()} len={len(r)}')
        return r[4:]

    def block(n, reading, data=b''):
        r = xfer(out, inp, bytes([6, 0, n & 255, n >> 8, 15 if reading else 13])+data)
        return check_block(r, n, reading)

    def read32(address):
        tar(address)
        return struct.unpack('<I', block(1, True))[0]

    try:
        setup(out, inp, a.speed)
        if a.ack_hold is not None:
            assert xfer(out,inp,[0x84,a.ack_hold])==bytes([0x84,0,a.ack_hold])
        result['configuration']=xfer(out,inp,[0x80,255]).hex()
        dhcsr = read32(0xe000edf0)
        if not dhcsr & (1 << 17):
            tar(0xe000edf0)
            block(1, False, struct.pack('<I', 0xa05f0003))
            if not read32(0xe000edf0) & (1 << 17):
                raise RuntimeError('Target did not halt')
        result['RCC_CR'] = hex(read32(0x40021000))
        result['RCC_CFGR'] = hex(read32(0x40021004))
        # Cortex-M implementations differ: this F103 has a 4KiB TAR wrap,
        # whereas the DesignStart M0 model has 1KiB. Detect it via read-only
        # transfers instead of assuming a window and corrupting the benchmark.
        tar(0x20000000)
        chunks=[]
        for step in range(1,17):
            chunks.append(block(256,True))
            reg=xfer(out,inp,[6,0,1,0,7])  # posted MEM-AP TAR read
            current=struct.unpack('<I',check_block(reg,1,True))[0]
            if current==0x20000000:break
            if current!=0x20000000+step*1024:raise RuntimeError(f'Unexpected TAR {current:#x}')
        else:raise RuntimeError('No TAR wrap within safe 16KiB window')
        backup=b''.join(chunks)
        wrap_words=len(backup)//4
        result['wrap_bytes']=len(backup)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.with_suffix('.backup.bin').write_bytes(backup)
        def write_window(data):
            tar(0x20000000)
            for off in range(0,len(data),1024):block(256,False,data[off:off+1024])
        def read_window():
            tar(0x20000000)
            return b''.join(block(256,True) for _ in range(len(backup)//1024))
        page = random.Random(0x20261026).randbytes(len(backup))
        modified = True
        write_window(page)
        assert read_window() == page, 'Initial SRAM pattern mismatch'
        period = wrap_words // math.gcd(a.words, wrap_words)
        repeated = page * ((a.words+2*wrap_words-1)//wrap_words)
        payloads = [repeated[((k*a.words)%wrap_words)*4:((k*a.words)%wrap_words)*4+a.words*4]
                    for k in range(period)]
        header = bytes([6, 0, a.words & 255, a.words >> 8])
        packets = [header+b'\x0d'+p for p in payloads]
        for depth in depths:
            for reading in [True, False]:
                tar(0x20000000)
                t0 = time.perf_counter()
                sent = 0
                while sent < a.loops:
                    count = min(depth, a.loops-sent)
                    for k in range(sent, sent+count):
                        send(out, header+b'\x0f' if reading else packets[k % period])
                    for k in range(sent, sent+count):
                        data = check_block(bytes(inp.read(4096, timeout=5000)), a.words, reading)
                        if reading and data != payloads[k % period]:
                            raise RuntimeError(f'Raw read data mismatch depth={depth}, block={k}')
                    sent += count
                elapsed = time.perf_counter()-t0
                if not reading:
                    assert read_window() == page, 'Final SRAM write pattern mismatch'
                row = {'direction': 'read' if reading else 'write', 'depth': depth,
                       'seconds': elapsed, 'bytes': a.loops*a.words*4,
                       'MB_s': a.loops*a.words*4/elapsed/1e6, 'data_match': True}
                result['rows'].append(row)
                print(json.dumps(row), flush=True)
    except BaseException as exc:
        result['error'] = str(exc)
        raise
    finally:
        try:
            if backup is not None and modified:
                # Drain any responses left after a failed batched assertion.
                for _ in range(64):
                    try:
                        inp.read(4096, timeout=30)
                    except Exception as exc:
                        if isinstance(exc, usb.core.USBTimeoutError):
                            break
                        raise
                try:
                    write_window(backup)
                except Exception as restore_error:
                    # A failed zero-idle experiment can leave the DP out of
                    # framing. Recover conservatively solely to restore SRAM;
                    # the original test exception remains a failure.
                    result['restore_recovery_reason']=str(restore_error)
                    setup(out,inp,a.speed)
                    assert xfer(out,inp,[4,1,64,0,0,0])==bytes([4,0])
                    write_reg(0,0x1e)
                    write_window(backup)
                    result['restore_used_idle1_reconnect']=True
                result['restore_match'] = read_window() == backup
                assert result['restore_match'], 'SRAM restoration mismatch'
                result['backup_sha256'] = hashlib.sha256(backup).hexdigest()
        finally:
            usb.util.release_interface(d, 0)
            usb.util.dispose_resources(d)
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
