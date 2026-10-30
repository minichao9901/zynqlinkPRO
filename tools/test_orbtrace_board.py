"""Capture real F103ZE parallel ETM through this project's EP2 IN.

Requires the explicitly supplied probe pair to have been loaded already.
Verifies the target Flash against its ELF, saves/restores CoreSight registers
and run state, and records raw USB plus a Web-importable .zetm capture.
Does not program Flash. An optional diagnostic divider temporarily changes
the target clock and is restored before returning.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import threading
import time

from elftools.elf.elffile import ELFFile
import usb.core
import usb.util
from dap_pipeline_bench import open_dap, setup
from test_probe_board import Memory
from probe_build_info import provenance, swd_clock_details

REG = dict(demcr=0xe000edfc, dbg_cr=0xe0042004, etmcr=0xe0041000,
           etmtrigger=0xe0041008, etmteevr=0xe0041020, etmtecr1=0xe0041024,
           etmfflr=0xe004102c, etmtraceidr=0xe0041200, cspsr=0xe0040004,
           sppr=0xe00400f0, ffcr=0xe0040304,
           itm_tcr=0xe0000e80, itm_ter=0xe0000e00, dwt_ctrl=0xe0001000)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target-elf', type=Path, required=True)
    ap.add_argument('--bit', type=Path, required=True)
    ap.add_argument('--elf', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--milliseconds', type=float, default=20)
    ap.add_argument('--speed-khz', type=int, default=10000, help='SWD control clock; independent of TRACECLK')
    ap.add_argument('--hclk-div', type=int, choices=(1, 2, 4), default=1,
                    help='Temporary AHB divider for signal-integrity diagnosis; restored on exit')
    ap.add_argument('--gpio-speed', type=int, choices=(1, 2, 3),
                    help='Temporary PE2..PE6 output mode (1=10,2=2,3=50MHz); restored')
    ap.add_argument('--trace-id', type=int, choices=range(1, 112), default=2, metavar='1..111')
    ap.add_argument('--sync', action='store_true', help='Enable ITM/DWT periodic synchronization')
    ap.add_argument('--raw', action='store_true', help='Capture diagnostic sampled DDR bytes, not decoded ETM')
    args = ap.parse_args()
    if not 0 < args.milliseconds <= 1000:
        ap.error('capture must be 0..1000 ms')
    work = args.output
    work.mkdir(parents=True, exist_ok=True)
    report = dict(artifacts=provenance(args.bit, args.elf),
                  target_elf=str(args.target_elf.resolve()),
                  target_elf_sha256=sha(args.target_elf.read_bytes()),
                  milliseconds=args.milliseconds, periodic_sync=args.sync, hclk_div=args.hclk_div,
                  raw_diagnostic=args.raw)
    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    before, locks, reader = {}, {}, None
    errors, wire, packets, records = [], bytearray(), [], []
    ended = threading.Event()
    armed = False
    was_halted = None
    gpio_before = None

    def control(action=0):
        return struct.unpack('<8I', dev.ctrl_transfer(0xc0, 0x60, action, 0x4554, 32, timeout=3000))

    def wait_program(expected):
        for _ in range(100):
            value = mem.word(0xe0041010)
            if value & 2 == expected:
                return
            time.sleep(.005)
        raise RuntimeError(f'ETM programming handshake failed: {value:#x}, expected {expected}')

    def unlock(base):
        status = mem.word(base + 0xfb4)
        locks.setdefault(base, status)
        if status & 3 == 3:
            mem.write_word(base + 0xfb0, 0xc5acce55)

    def receive():
        pending = bytearray()
        try:
            while not ended.is_set():
                data = bytes(dev.read(0x82, 8192, timeout=3000))
                wire.extend(data)
                pending.extend(data)
                while len(pending) >= 32:
                    h = struct.unpack_from('<8I', pending)
                    assert h[0] == 0x3154455a and h[3] <= 240 and h[7] == 1, h
                    length = 32 + 2*h[3]
                    if len(pending) < length:
                        break
                    packets.append(h)
                    records.extend(struct.iter_unpack('<H', pending[32:length]))
                    del pending[:length]
                    if h[2] & 8:
                        assert not pending, 'bytes after END'
                        ended.set()
                        break
            # Firmware retires up to 16 queued native reads after END.
            for _ in range(16):
                assert not dev.read(0x82, 8192, timeout=3000), 'data after END'
        except BaseException as exc:
            errors.append(repr(exc))
            ended.set()

    try:
        report['IDCODE'] = setup(out, inp, args.speed_khz).hex()
        report['cpuid'] = hex(mem.word(0xe000ed00))
        assert mem.word(0xe0042000) & 0xfff == 0x414, 'requires F103xE'
        report['flash'] = []
        with args.target_elf.open('rb') as f:
            for segment in ELFFile(f).iter_segments():
                if segment['p_type'] != 'PT_LOAD' or not segment['p_filesz']:
                    continue
                address = segment['p_paddr']
                if 0x08000000 <= address < 0x08080000:
                    expected = segment.data()
                    actual = mem.read(address, len(expected))
                    assert actual == expected, f'ELF/Flash mismatch at {address:#x}'
                    report['flash'].append(dict(address=address, bytes=len(expected), sha256=sha(actual)))
        assert report['flash'], 'no Flash image verified'
        report['reference'] = struct.unpack('<4I', dev.ctrl_transfer(0xc0, 0x61, 0, 0x4554, 16))
        assert 190_000_000 <= report['reference'][0] <= 210_000_000 and report['reference'][3] == 1
        report['rcc_before'] = [mem.word(a) for a in (0x40021000, 0x40021004)]
        was_halted = bool(mem.word(0xe000edf0) & (1 << 17))
        mem.write_word(0xe000edf0, 0xa05f0003)
        assert mem.word(0xe000edf0) & (1 << 17)
        if args.hclk_div != 1:
            cfgr = report['rcc_before'][1]
            cfgr = (cfgr & ~0xf0) | (0x80 if args.hclk_div == 2 else 0x90)
            if args.hclk_div == 4:
                cfgr &= ~0x700  # Keep APB1 at 18 MHz for the 72 MHz example.
            mem.write_word(0x40021004, cfgr)
        report['rcc_capture'] = [mem.word(a) for a in (0x40021000, 0x40021004)]
        if args.gpio_speed is not None:
            gpio_before = [mem.word(a) for a in (0x40021018,0x40011800)]
            mem.write_word(0x40021018,gpio_before[0]|64)
            value=(gpio_before[1]&~0x0fffff00)|(int(str(args.gpio_speed)*5,16)<<8)
            mem.write_word(0x40011800,value)
            report['gpio_before']=gpio_before
            report['gpio_capture']=value
        before['demcr'] = mem.word(REG['demcr'])
        mem.write_word(REG['demcr'], before['demcr'] | 0x01000000)
        for name, address in REG.items():
            if name != 'demcr':
                before[name] = mem.word(address)
        (work/'target-before.json').write_text(json.dumps(before, indent=2)+'\n')
        report['tpiu_supported'] = mem.word(0xe0040000)
        assert report['tpiu_supported'] & 8, report['tpiu_supported']
        unlock(0xe0041000)
        unlock(0xe0040000)
        cr = (before['etmcr'] | 0xc00) & ~0x301
        mem.write_word(REG['etmcr'], cr)
        wait_program(2)
        for name, value in dict(etmtrigger=0, etmteevr=0x6f, etmtecr1=0, etmfflr=0,
                                etmtraceidr=args.trace_id, cspsr=8, sppr=0, ffcr=before['ffcr'] | 2,
                                dbg_cr=(before['dbg_cr'] & ~0xe0) | 0xe0).items():
            mem.write_word(REG[name], value)
        if args.sync:
            unlock(0xe0000000)
            mem.write_word(REG['itm_tcr'], 0x0001000d)
            mem.write_word(REG['dwt_ctrl'], before['dwt_ctrl'] | 1)
        config = dict(protocol='ETMv3', idr=mem.word(0xe00411e4),
                      ctrl=mem.word(REG['etmcr']) & ~0x400,
                      ccer=mem.word(0xe00411e8), traceid=mem.word(REG['etmtraceidr']))
        report['config'] = config
        if args.raw:
            # Prepare ETM while the CPU is halted, before arming the raw
            # receiver: the port otherwise floods it with idle bytes while
            # the host configures CoreSight over SWD.
            mem.write_word(REG['etmcr'], cr & ~0x400)
            wait_program(0)
            mem.write_word(0xe000edf0, 0xa05f0001)
        control(0x301)
        armed = True
        for _ in range(100):
            s = control()
            if not s[7] and s[1] & 17 == 17:
                break
            time.sleep(.005)
        else:
            raise RuntimeError(f'PL not armed/calibrated: {s}')
        report['start_status'] = s
        reader = threading.Thread(target=receive, daemon=True)
        reader.start()
        if not args.raw:
            mem.write_word(REG['etmcr'], cr & ~0x400)
            wait_program(0)
            mem.write_word(0xe000edf0, 0xa05f0001)
        time.sleep(args.milliseconds/1000)
        if not args.raw:
            mem.write_word(REG['etmcr'], cr)
            wait_program(2)
        # Raw mode also streams idle/synchronization bytes at line rate;
        # stop promptly to avoid overflowing while no ETM payload is produced.
        if not args.raw:
            time.sleep(.005)
        control(2)
        reader.join(5)
        assert not reader.is_alive(), 'USB reader did not retire'
        assert not errors, errors
        report['stop_status'] = control()
        sequence_ok = all(p[1] == i for i, p in enumerate(packets))
        capture_ok = len({p[6] for p in packets}) == 1
        loss = any(p[2] & 4 for p in packets)
        synced = any(p[2] & 2 for p in packets)
        etm = bytes(v[0] & 255 for v in records if v[0] >> 8 == config['traceid'])
        quality = dict(records=len(records), loss=loss, synced=synced,
                       ended=bool(packets and packets[-1][2] & 8), trailingBytes=0,
                       fclk=packets[-1][5] if packets else None,
                       tckKhz=packets[-1][2] >> 16 if packets else None,
                       refClockHz=report['reference'][0])
        record = dict(format='zynqdap-etm-1', kind='hardware', config=config, quality=quality,
                      etm=base64.b64encode(etm).decode(), etmSha=sha(etm),
                      elf=base64.b64encode(args.target_elf.read_bytes()).decode(),
                      elfName=args.target_elf.name, elfSha=report['target_elf_sha256'])
        if args.raw:
            (work/'raw-ddr.bin').write_bytes(etm)
        else:
            (work/'capture.zetm').write_text(json.dumps(record, indent=2)+'\n')
            (work/'etm.bin').write_bytes(etm)
        report.update(quality=quality, packets=len(packets),
                      sequence_ok=sequence_ok, capture_id_ok=capture_ok)
        if args.raw:
            report.update(raw_bytes=len(etm), raw_sha256=sha(etm),
                          raw_note='sampled DDR bytes before TPIU parsing; source tag 2 is a transport placeholder')
        else:
            report.update(etm_bytes=len(etm), etm_sha256=sha(etm))
        assert sequence_ok and capture_ok and synced and not loss and quality['ended'] and etm
        report['capture_passed'] = True
    except BaseException as exc:
        report['error'] = repr(exc)
        # Reconnect/clear sticky MEM-AP errors before restoring saved state.
        try:
            setup(out, inp, args.speed_khz)
        except BaseException as reconnect:
            report['reconnect_error'] = repr(reconnect)
        raise
    finally:
        if armed and (not reader or reader.is_alive()):
            try:
                control(2)
                if reader:
                    reader.join(4)
            except BaseException as exc:
                report['usb_cleanup_error'] = repr(exc)
        try:
            if was_halted is not None:
                mem.write_word(0xe000edf0, 0xa05f0003)
                if 'etmcr' in before:
                    mem.write_word(REG['etmcr'], (mem.word(REG['etmcr']) | 0x400) & ~1)
                    try:
                        wait_program(2)
                    except RuntimeError:
                        mem.write_word(REG['etmcr'], mem.word(REG['etmcr']) | 1)
                        wait_program(2)
                    for name, value in before.items():
                        if name not in ('demcr', 'etmcr'):
                            mem.write_word(REG[name], value)
                    mem.write_word(REG['etmcr'], before['etmcr'])
                    report['restored'] = all(mem.word(REG[n]) == v for n, v in before.items() if n != 'demcr')
                for base, status in locks.items():
                    if status & 2:
                        mem.write_word(base + 0xfb0, 0)
                if 'demcr' in before:
                    mem.write_word(REG['demcr'], before['demcr'])
                if gpio_before is not None:
                    mem.write_word(0x40011800,gpio_before[1])
                    mem.write_word(0x40021018,gpio_before[0])
                if args.hclk_div != 1:
                    mem.write_word(0x40021004, report['rcc_before'][1])
                report['rcc_after'] = [mem.word(a) for a in (0x40021000, 0x40021004)]
                assert report['rcc_before'] == report['rcc_after'], 'target clock changed'
                if not was_halted:
                    mem.write_word(0xe000edf0, 0xa05f0001)
                if report.get('restored') is False:
                    raise RuntimeError('CoreSight register restoration did not match snapshot')
        except BaseException as exc:
            report['target_cleanup_error'] = repr(exc)
            raise
        finally:
            if args.raw and records and not (work/'raw-ddr.bin').exists():
                partial = bytes(v[0] & 255 for v in records if v[0] >> 8 == 2)
                (work/'raw-ddr.bin').write_bytes(partial)
                report['partial_raw_bytes'] = len(partial)
                report['partial_raw_sha256'] = sha(partial)
            (work/'usb-wire.bin').write_bytes(wire)
            report['usb_reader_errors'] = errors
            (work/'acceptance.json').write_text(json.dumps(report, indent=2)+'\n')
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)
            print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
