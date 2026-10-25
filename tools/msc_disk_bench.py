"""Unbuffered I/O on the freshly RAM-downloaded Xilinx virtual MSC disk only.

No formatting or partition changes. Writes are confined to a test range starting
at 64 MiB on a USB disk with the exact Xilinx PS USB VirtDisk identity.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import random
import statistics
import struct
import subprocess
import time

K = C.WinDLL('kernel32', use_last_error=True)
K.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
K.CreateFileW.restype = W.HANDLE
K.VirtualAlloc.argtypes = [C.c_void_p, C.c_size_t, W.DWORD, W.DWORD]
K.VirtualAlloc.restype = C.c_void_p
K.VirtualFree.argtypes = [C.c_void_p, C.c_size_t, W.DWORD]
K.ReadFile.argtypes = K.WriteFile.argtypes = [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
K.SetFilePointerEx.argtypes = [W.HANDLE, C.c_longlong, C.POINTER(C.c_longlong), W.DWORD]
K.CloseHandle.argtypes = [W.HANDLE]
K.DeviceIoControl.argtypes = [W.HANDLE, W.DWORD, C.c_void_p, W.DWORD, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]


def find_ram_disk():
    cmd = "Get-CimInstance Win32_DiskDrive | Select-Object Index,Model,Size,BytesPerSector,InterfaceType,PNPDeviceID | ConvertTo-Json -Compress"
    raw = subprocess.check_output(['powershell', '-NoProfile', '-Command', cmd], text=True, errors='replace')
    devices = json.loads(raw)
    if isinstance(devices, dict):
        devices = [devices]
    found = [d for d in devices if d['InterfaceType'] == 'USB' and d['Model'] == 'Xilinx PS USB VirtDisk USB Device' and d['PNPDeviceID'].upper().startswith('USBSTOR\\DISK&VEN_XILINX&PROD_PS_USB_VIRTDISK&') and 500_000_000 <= int(d['Size']) <= 600_000_000 and int(d['Index']) != 0]
    if len(found) != 1:
        raise RuntimeError('Expected exactly one confirmed Xilinx RAM disk; refusing raw I/O: ' + raw)
    return found[0]


def benchmark(chunk=65536, length=32*1024*1024, repeat=3):
    device = find_ram_disk()
    if chunk % max(4096, int(device['BytesPerSector'])) or length % chunk:
        raise ValueError('Chunk must be sector-aligned; length must be a multiple of chunk')
    path = '\\\\.\\PhysicalDrive' + str(device['Index'])
    handle = K.CreateFileW(path, 0xC0000000, 3, None, 3, 0x20000000, None)  # NO_BUFFERING, synchronous
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    buffer = K.VirtualAlloc(None, chunk, 0x3000, 4)
    if not buffer:
        K.CloseHandle(handle)
        raise C.WinError(C.get_last_error())
    base = 64 * 1024 * 1024
    if base + length > int(device['Size']):
        raise ValueError('Test range exceeds verified RAM disk size')
    transferred = W.DWORD()
    def seek(offset):
        if not K.SetFilePointerEx(handle, offset, None, 0):
            raise C.WinError(C.get_last_error())
    def io(write):
        transferred.value = 0
        if not (K.WriteFile if write else K.ReadFile)(handle, buffer, chunk, C.byref(transferred), None):
            raise C.WinError(C.get_last_error())
        if transferred.value != chunk:
            raise RuntimeError(f'Short disk I/O {transferred.value}/{chunk}')
    result = {'device': device, 'host_cache': 'FILE_FLAG_NO_BUFFERING', 'offset': base, 'length': length, 'chunk': chunk, 'runs': []}
    try:
        # READ first: raw I/O bypasses the Windows filesystem cache.
        for direction in ['read', 'write']:
            for trial in range(repeat):
                seek(base)
                payload = random.Random(20261025).randbytes(chunk)
                C.memmove(buffer, payload, chunk)
                start = time.perf_counter()
                for offset in range(base, base + length, chunk):
                    if direction == 'write':
                        C.memmove(buffer, struct.pack('<QQ', offset, offset ^ 0x5A8319EF19441111), 16)
                    io(direction == 'write')
                seconds = time.perf_counter() - start
                row = {'direction': direction, 'repeat': trial + 1, 'bytes': length, 'seconds': seconds, 'MB_per_second': length / seconds / 1e6}
                result['runs'].append(row)
                print(direction, trial + 1, round(row['MB_per_second'], 3), 'MB/s', flush=True)
        # Read back every byte and every block's unique offset marker after writes.
        seek(base)
        for offset in range(base, base + length, chunk):
            io(False)
            data = C.string_at(buffer, chunk)
            if data[:16] != struct.pack('<QQ', offset, offset ^ 0x5A8319EF19441111) or data[16:] != payload[16:]:
                raise RuntimeError(f'RAM disk readback mismatch at {offset:#x}')
        result['write_readback_verified_bytes'] = length
        result['median_MB_per_second'] = {d: statistics.median(x['MB_per_second'] for x in result['runs'] if x['direction'] == d) for d in ['read', 'write']}
        print('PASS full readback', length, 'bytes', flush=True)
        return result
    finally:
        K.VirtualFree(buffer, 0, 0x8000)
        K.CloseHandle(handle)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--chunk', type=int, default=65536)
    ap.add_argument('--mib', type=int, default=32)
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    result = benchmark(args.chunk, args.mib * 1048576, args.repeat)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
