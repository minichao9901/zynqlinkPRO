"""Qualify fixed-page F103ZE SelectIO transfers inside the CDC48 backup fixture."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import random
import subprocess
import sys
import time

from jtag200 import PROFILES, ROOT, load_pair
from jtag200_f103_fixture import PAGE, SIZE, TAP, guards, low_link
from jtag200_h743_scan import Scan, identify, select, slow_read
from jtag200_pipeline import BlockBenchmark, Ownership, PhysicalPort, need
from probe_flash import Session
from probe_load import check_streams, probe_state

PATTERN = random.Random(0xf103200).randbytes(1024)
INVERSE = bytes(b ^ 255 for b in PATTERN)


def sweep(port, folder, args, report, save):
    bench = BlockBenchmark(port, folder)
    low = None
    current = PATTERN
    qualified = {}
    read_points = {}

    def run(config, seconds, mixed):
        rate, tap, slot, advance, idle = config
        half, hz = select(port, rate, tap)
        control = int(port.command('read_word 0xf8000180'))
        divisor = (control >> 8 & 63) * (control >> 20 & 63)
        need(divisor and not control & 0x30 and abs(6.4e9/divisor/half - hz) < 1,
             'Unexpected TCK divider')
        stream = half == 2 or (args.quad and half == 1)
        bench.configure(rate, idle, slot, arm=True, arm_page=PAGE, stream=stream,
                        verify_in_pl=stream, advance_tdi=advance[1], advance_tms=advance[0])
        row = bench.run(0 if mixed else 1, seconds, profile=True)
        for field in ('dmi_busy','dmi_invalid','wire_dmi'):
            row.pop(field, None)
        row.update(config=config, tck_hz=hz, fclk1=hex(control))
        report['windows'].append(row)
        if seconds or len(report['windows']) % 20 == 0:
            save()
        return row

    def rearm():
        half, _ = select(port, '50', low[1])
        probe = Scan()
        probe.instruction(8)
        probe.data(0, 1, 24)
        probe.transfer(port, half, 0)
        result = slow_read(port, half, 0, 0xe0042000, 1, {low[2]})[low[2]]
        need(result['values'] == [(0x10036414 << 3) | 2] and all(a == 2 for a in result['acks'])
             and not result['status'] & 0xa2, 'Low-speed MEM-AP recovery failed')
        bench.pattern(PATTERN)
        need(run(low, 0, True)['passed'], 'Guarded reference page recovery failed')

    def independent(row):
        nonlocal current
        current = (INVERSE if (row['write_bytes']//1024 - 1) % 2 else PATTERN)
        bench.pattern(current)
        check = run(low, 0, False)
        need(check['passed'], 'Independent non-streamed readback failed')
        report['last_verified_sha256'] = sha256(current).hexdigest()

    bench.pattern(current)
    for rate in dict.fromkeys(['50', *args.rates]):
        center = 36 if PROFILES[rate][1] == 4 else 35
        half = PROFILES[rate][1]
        taps = list(dict.fromkeys((16, 8, 24, 0, 31, *(range(32) if args.dense else ()))))
        point = report['points'][rate] = dict(taps={}, reads=[], mixed=[])
        for tap in taps:
            select(port, rate, tap)
            slots = identify(port, half, 3, expected=TAP)
            point['taps'][str(tap)] = sorted(slots)
            if not slots:
                continue
            for slot in sorted(slots, key=lambda s: abs(s-center)):
                for adv in (((False,False), (True,True), (False,True), (True,False)) if half==2 else ((False,False),)):
                    if low is None:
                        idles = (32, 64)
                    elif args.idles and rate != '50':
                        idles = args.idles
                    elif args.quad and half==1:
                        idles = (9, 13, 17, 21, 25, 29, 33, 41, 49, 65)
                    elif half==2:
                        idles = (7, 9, 11, 13, 15, 17, 19, 25, 33, 49, 65)
                    else:
                        idles = (4, 12, 24, 40, 64, 96)
                    for idle in idles:
                        config = (rate,tap,slot,adv,idle)
                        bench.pattern(current)
                        probe = run(config, 0, False)
                        if not probe['passed']:
                            continue
                        if low is None:
                            low = config
                        if rate not in read_points:
                            read = run(config, 1, False)
                            if read['passed']:
                                read_points[rate] = config
                                point['reads'].append(read)
                        # Force a different first word even for a single-block pilot.
                        if current == PATTERN:
                            bench.pattern(INVERSE)
                            expected = INVERSE
                        else:
                            bench.pattern(PATTERN)
                            expected = PATTERN
                        pilot = run(config, 0, True)
                        if not pilot['passed']:
                            rearm()
                            current = PATTERN
                            continue
                        current = expected
                        bench.pattern(PATTERN)
                        mix = run(config, 1, True)
                        if not mix['passed']:
                            rearm()
                            current = PATTERN
                            continue
                        independent(mix)
                        qualified[rate] = config
                        point['mixed'].append(mix)
                        break
                    if rate in qualified:
                        break
                if rate in qualified:
                    break
            if rate in qualified:
                break
            if not args.dense and sum(bool(v) for v in point['taps'].values()) >= 3:
                break
        save()
        print(rate, 'read', point['reads'] and point['reads'][0]['read_MBps'],
              'mixed', [(r['read_MBps'],r['write_MBps']) for r in point['mixed']], flush=True)
        need(low is not None, 'Could not identify/verify the 50 MHz reference page')
    # Prefer the highest and fastest mixed points, with fallback on a failed long run.
    if args.seconds:
        def metric(rate, key):
            row = report['points'][rate]['mixed'][0]
            return PROFILES[rate][2] if key == 'hz' else row[key]
        done = {}
        for key in ('hz','write_MBps','read_MBps'):
            for rate in sorted(qualified, key=lambda r:metric(r,key), reverse=True):
                if rate not in done:
                    bench.pattern(PATTERN)
                    rows = []
                    for _ in range(3):
                        row = run(qualified[rate],args.seconds,True)
                        rows.append(row)
                        if not row['passed']:
                            rearm()
                            current = PATTERN
                            break
                        independent(row)
                        bench.pattern(PATTERN)
                    done[rate] = all(r['passed'] for r in rows) and len(rows)==3
                    report['points'][rate]['long_mixed'] = rows
                    save()
                if done[rate]:
                    break
        for rate in sorted(read_points, key=lambda r:report['points'][r]['reads'][0]['read_MBps'], reverse=True):
            rows = []
            bench.pattern(current)
            for _ in range(3):
                row = run(read_points[rate], args.seconds, False)
                rows.append(row)
                if not row['passed']:
                    break
            report['points'][rate]['long_read'] = rows
            save()
            if all(r['passed'] for r in rows):
                break
    if args.host_payload and qualified:
        # Measure new host data, including XSCT file transfers and completion checks.
        rate = max(qualified, key=lambda r: report['points'][r]['mixed'][0]['write_MBps'])
        rate, tap, slot, advance, idle = qualified[rate]
        half, _ = select(port, rate, tap)
        stream = half == 2 or (args.quad and half == 1)
        bench.configure(rate, idle, slot, arm=True, arm_page=PAGE, stream=stream,
                        verify_in_pl=stream, advance_tdi=advance[1], advance_tms=advance[0])
        sendfile, recvfile = folder/'host-tx.bin', folder/'host-rx.bin'
        rng = random.Random(0xf103)
        host = report['host_payload'] = dict(rate=rate, samples=[])
        check = ('if {[read_word 0x40000020] != 1 || [read_word 0x40002000] != 0x10100} '
                 '{error "Host payload completion failed"}')
        for _ in range(8):
            data = rng.randbytes(1024)
            sendfile.write_bytes(data)
            start = time.perf_counter()
            port.command(f'physwr -force -bin -file {{{sendfile.as_posix()}}} 0x40001004 256; '
                         f'physwr -force 0x40000008 13; wait_mask 0x40000004 31 15; {check}; '
                         'physwr -force 0x40000008 0; wait_mask 0x40000004 31 5')
            end_write = time.perf_counter()
            port.command(f'physwr -force 0x40000008 5; wait_mask 0x40000004 31 15; {check}; '
                         f'physrd -force -bin -file {{{recvfile.as_posix()}}} 0x40002004 256; '
                         'physwr -force 0x40000008 0; wait_mask 0x40000004 31 5')
            need(recvfile.read_bytes()==data, 'New host payload differs from SRAM readback')
            elapsed_read = time.perf_counter()-end_write
            host['samples'].append(dict(write_s=end_write-start, read_s=elapsed_read))
            current = data
        save()
    report['last_verified_sha256'] = sha256(current).hexdigest()


def main(args):
    folder = args.fixture.resolve()
    state = json.loads((folder / 'state.json').read_text())
    original = (folder / 'backup.bin').read_bytes()
    need(len(original)==SIZE and sha256(original).hexdigest()==state['ram_sha256'] and
         not state.get('restored') and state['tap']==hex(TAP), 'Live F103 fixture required')
    report = dict(points={}, windows=[])
    def save():
        path = folder / 'windows.tmp'
        path.write_text(json.dumps(report, indent=2)+'\n')
        path.replace(folder / 'windows.json')
    with low_link() as mem:
        need(mem.word(0xe000edf0) & (1<<17) and mem.read(PAGE,SIZE)==original and
             guards(mem)==state['guards'], 'Fixture changed before selectio test')
        mem.write(PAGE,PATTERN)
        need(mem.read(PAGE,1024)==PATTERN,'Test pattern preload failed')
    try:
        with closing(Ownership()):
            report['streams_before_load'] = check_streams()
            session = Session(folder, args.sdk, args.server, cable_serial=args.cable_serial)
            report['probe_before_load'] = probe_state(session)
        args.out = folder / 'candidate'
        load_pair(args)
        with closing(Ownership()), closing(PhysicalPort(folder,args.cable_serial,args.sdk)) as port:
            report['pair'] = port.verify_probe(args.pair)
            report['io_pll'] = hex(int(port.command('read_word 0xf8000108')))
            sweep(port,folder,args,report,save)
    finally:
        save()
        subprocess.run([sys.executable,'-X','utf8','toolbox.py','probe-load',
                        '--out',str(folder/'historical-restored')],cwd=ROOT,check=True)
    with low_link() as mem:
        live = mem.read(PAGE, SIZE)
        need(sha256(live[:1024]).hexdigest()==report['last_verified_sha256'] and
             live[1024:]==original[1024:] and guards(mem)==state['guards'],
             'Independent USB payload/guard check failed')
        report['usb_final_payload_verified'] = True
        save()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--pair',type=Path,required=True)
    p.add_argument('--rates',nargs='+',choices=PROFILES,required=True)
    p.add_argument('--seconds',type=int,choices=range(61),default=60)
    p.add_argument('--host-payload', action='store_true', help='Verify and time distinct PC payloads via physical AP0')
    p.add_argument('--quad',action='store_true',help='Enable the four-TCK stream on the corresponding PL pair')
    p.add_argument('--idles',type=int,nargs='+',help='Specific idle counts for refinement')
    p.add_argument('--dense',action='store_true')
    p.add_argument('--sdk',type=Path,default=Path('E:/Xilinx/SDK/2018.3'))
    p.add_argument('--cable-serial',required=True)
    p.add_argument('--server',default='tcp:127.0.0.1:3121')
    p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    if args.execute:
        main(args)
    else:
        print('Read, qualify alternating writes and restore through the F103 backup fixture.')
