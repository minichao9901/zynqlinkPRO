"""The cases that can delegate directly to validated fusion command line interfaces."""
import json

from fusion_acceptance import TOOLBOX, run_capture


def run_case(case, plan, campaign, pair, args, target):
    from fusion_fixture import TargetImage, confirm_spi_route, target_io

    runner = case['runner']
    out = args.out
    serial = campaign['serial']
    if runner == 'probe-self':
        for i in range(case['parameters']['rounds']):
            name=f'usb-{i+1}'
            run_capture([*TOOLBOX,'selectio','--serial',serial,'usb-test',
                         '--seconds',str(case['parameters']['seconds'])],out,name)
        ddr = run_ddr_loopback(case, serial, out)
        return {'status':'pending', 'ddr':ddr, 'remaining':['Attach in-flight close/reopen evidence.']}

    image = TargetImage(target['files']['fw.elf']['path'], case['board'])
    if runner.startswith('spi-'):
        confirm_spi_route('swd')
    profile = plan['profiles'].get(case['clock'].get('profile'), case['clock'])
    markers = {'sram': 0x46585046, 'rtt': 0x46585046, 'scope': 0x46585046, 'combo': 0x46585046,
               'uart': 0x55415254, 'swo-itm': 0x49544d31, 'swo-source': 0x53574f53, 'gdb': 0x44424731,
               'flash': 0x44424731, 'ram': 0x44424731}
    if case['board'] == 'f103ze' and runner == 'spi-target-tx':
        markers[runner] = 0x53504931
    transport = args.transport or profile.get('transport')
    control_rate = profile.get('requestedHz', 1_000_000) if runner == 'gdb' else 1_000_000
    with target_io(case['board'], serial, transport, control_rate) as io:
        before = image.verify(io)
        (out / 'target-before.json').write_text(json.dumps(before, indent=2), encoding='utf8')
        if runner in markers:
            if image.word(io, 'g_fixture_ready') != markers[runner]:
                raise RuntimeError('Target firmware has not published the expected ready marker')
            clocks = image.clocks(io, profile['cpuMHz'], profile.get('hclkMHz'))
            (out / 'target-clocks.json').write_text(json.dumps(clocks, indent=2), encoding='utf8')
        if runner in ('flash', 'ram', 'gdb'):
            from fusion_boot import verify_boot, verify_rtt_terminal
            result = verify_boot(case, image, target['image'], io)
            if runner == 'gdb':
                result['rtt_commands'] = verify_rtt_terminal(case, image, io, out)
            return {'status': 'pending', **result}

    if runner == 'sram':
        from fusion_performance import run_sram
        result = run_sram(case, image, serial, args, out)
    elif runner in ('rtt', 'scope', 'combo'):
        from fusion_performance import run_stream
        result = run_stream(case, image, serial, args, out)
    elif runner == 'uart':
        from fusion_uart import run_uart
        result = run_uart(case, image, serial, args, out)
    elif runner == 'swo-itm':
        from fusion_swo import run_itm
        result = run_itm(case, image, serial, args, out)
    elif runner == 'swo-source':
        from fusion_swo import run_dma_source
        result = run_dma_source(case, image, serial, args, out)
    elif runner.startswith('spi-'):
        if case['board'] == 'f103ze':
            from fusion_f103_spi import run_f103_tx
            result = run_f103_tx(case, image, serial, args, out)
        else:
            confirm_spi_route('spi')
            result = run_spi(case, serial, args)
            confirm_spi_route('swd')
    elif runner == 'etm':
        result = run_etm(case, pair, out, target, serial)
    else:
        raise ValueError(f'No executor for {runner}')
    with target_io(case['board'], serial, transport) as io:
        after = image.verify(io)
        (out / 'target-after.json').write_text(json.dumps(after, indent=2), encoding='utf8')
    return {'status': 'pending', **result}


def run_ddr_loopback(case, serial, out):
    from selectio_native import native_connection
    from selectio_pipeline_bench import measure_window

    rows = []
    with native_connection(serial) as native, (out / 'ddr-windows.jsonl').open('x', encoding='utf8') as log:
        info = native.info()
        if info['max_queue_depth'] != 4:
            raise RuntimeError('Expected depth 4 for transport-only DDR loopback')
        size = 4032
        initial = bytes(range(256)) * 16
        expected = initial[:size]
        address = 0x20008020
        if native.bulk_many([(address, size, expected), (address, size, None)], 4, transport_only=True) != [b'', expected]:
            raise RuntimeError('Private probe loopback prefill failed')
        seq = 0
        for round_no in range(1, case['parameters']['rounds'] + 1):
            for direction in ('read', 'write', 'mixed'):
                count, elapsed, usb, seq, expected = measure_window(
                    native, direction, address, size, 4, case['parameters']['seconds'], round_no, seq, expected,
                    transport_only=True)
                row = dict(round=round_no, direction=direction, requests=count, payload_bytes=count*size,
                           seconds=elapsed, usb_seconds=usb, MBps=count*size/elapsed/1e6)
                rows.append(row)
                log.write(json.dumps(row) + '\n')
                log.flush()
    return rows


def run_spi(case, serial, args):
    from h743_spi_accept import H743_USB, Fixture, open_fixture_port, raw_duplex, receive_on_h743, receive_on_j7
    from selectio_native import native_connection
    from serial.tools.list_ports import comports

    p = case['parameters']
    runner = case['runner']
    rows = []
    ports = [port.device for port in comports() if (port.vid, port.pid, port.serial_number) == H743_USB]
    if len(ports) != 1:
        raise RuntimeError(f'Expected one explicit H743 SPI fixture, found {ports}')
    with open_fixture_port(ports[0]) as port:
        fixture = Fixture(port)
        identity = fixture.identify()
        if 'revision=3' not in identity:
            raise RuntimeError(f'Expected the packaged H743 revision 3 SPI fixture: {identity}')
        divider, remainder = divmod(fixture.kernel, args.rate)
        if runner == 'spi-target-tx' and (remainder or divider not in (2, 4, 8, 16, 32, 64, 128, 256)):
            raise ValueError('This SCK rate does not divide the live SPI2 kernel clock')
        with native_connection(serial) as native:
            info = native.info()
            if runner == 'spi-duplex':
                reference = info['reference_hz']
                half = (reference + args.rate - 1) // args.rate
                if abs(reference//half - args.rate) > 1 or 112 + 16 * half * args.frame_bytes > 4096:
                    return {'status': 'blocked', 'reason': 'Current raw waveform buffer or clock does not fit this point'}
            try:
                for round_no in range(1, p['rounds'] + 1):
                    row = {'round': round_no, 'mode': args.spi_mode, 'fixture': identity}
                    try:
                        if runner == 'spi-target-tx':
                            receive_on_j7(native, fixture, args.spi_mode, divider, row, seconds=p['seconds'], tap=args.tap)
                        elif runner == 'spi-target-rx':
                            receive_on_h743(native, fixture, args.spi_mode, args.frame_bytes, row,
                                            hz=args.rate, tap=args.tap)
                        else:
                            raw_duplex(native, fixture, args.spi_mode, reference, row,
                                       hz=args.rate, length=args.frame_bytes)
                        row['passed'] = True
                    except Exception as error:
                        row.update(passed=False, error=str(error))
                        raise
                    finally:
                        with (args.out / 'spi-windows.jsonl').open('a', encoding='utf8') as stream:
                            stream.write(json.dumps(row) + '\n')
                    rows.append(row)
            finally:
                state = fixture.state('SPI STOP')
                (args.out / 'spi-stop.json').write_text(json.dumps(state, indent=2), encoding='utf8')
    remaining = ['Attach physical SCK and ownership/target restoration evidence.']
    if runner != 'spi-target-tx':
        remaining.append('Add the 60 second sustained transfer and byte counters for this direction.')
    return {'windows': rows, 'remaining': remaining}


def run_etm(case, pair, out, target, serial):
    import libusb_package
    import usb.core

    devices = [d for d in usb.core.find(find_all=True, idVendor=0x0d28, idProduct=0x0204,
               backend=libusb_package.get_libusb1_backend()) if d.manufacturer == 'CherryUSB']
    if [d.serial_number for d in devices] != [serial]:
        raise RuntimeError('The current Trace CLI requires exactly one J7, matching the campaign serial.')
    elf=target['files']['fw.elf']['path']
    rows=[]
    for ms in case['parameters']['windowsMs']:
        for round_no in range(1, case['parameters']['rounds']+1):
            name=f'capture-{ms}ms-{round_no}'
            record=out/name
            args=[*TOOLBOX,'trace','capture','--elf',elf,'--bit',str(pair/'probe.bit'),
                  '--zynq-elf',str(pair/'application.elf'),'--out',str(record),
                  '--swd-khz',str(case['clock']['requestedHz']//1000),'--seconds',str(ms/1000),
                  '--gpio-speed',str(case['clock']['gpioSpeed']),'--json-out',str(out/(name+'.json'))]
            if case['parameters']['mode']=='running-window':
                args.append('--running-window')
            run_capture(args,out,name)
            run_capture([*TOOLBOX,'trace','verify','--record',str(record),'--require-decoded'],out,'verify-'+name)
            rows.append({'milliseconds':ms,'round':round_no,'record':str(record)})
    return {'captures':rows,
            'remaining':['Attach the pre/post target CDC, clocks, workload and restoration evidence before signing off.']}
