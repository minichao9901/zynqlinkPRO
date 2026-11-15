"""Fixed-rate native HSS acceptance using the existing byte verifier."""
import struct
import time

from tools.board_acceptance_target import checked, wait_for
from tools.run_board_acceptance import SCOPE_TICK_HZ, Unsafe, native_scope_rate_matches


def native_window(dev, probe, case, address, expected, clock, result):
    """Measure with a single EP87 reader, including the post-STOP tail."""
    from benchmark_probe_stream import HssReader
    from test_probe_board import drain_hss

    speed, channels = case['requestedHz'], case['channels']
    profile = case['native']
    result.update(profile)
    period, seconds = profile['periodTicks'], profile['seconds']
    addresses = tuple(address+4*i for i in range(channels))
    checked(probe.action(0x31, 12, bytes([1 if case['transport']=='swd' else 2]))[0] == 0,
            'Native HSS transport selection was rejected')
    checked(probe.action(0x32, 3, struct.pack('<I', speed))[0] == 0,
            'Native HSS link clock was rejected')
    config = struct.pack('<IBB', period, 0, channels)
    config += b''.join(struct.pack('<IBB', item, 4, 4) for item in addresses)
    checked(probe.action(0x32, 10, config)[0] == 0, 'Native HSS fixed period was rejected')
    drain_hss(dev)
    reader = HssReader(dev, expected, period, definition=(speed, addresses), drain_after_error=True)
    reader.start()

    def metrics(running):
        rc, row = probe.action(0x32, 11)
        checked(rc == 0 and row[0] == 0x31535348 and row[2] == SCOPE_TICK_HZ
                and row[10] == period and bool(row[11] & 0x100) == running,
                f'Native HSS counter state invalid: {rc}, {row}')
        return row

    def request_stop():
        rc, _ = probe.action(0x32, 0)
        checked(rc in (0, -7), f'Native HSS STOP rejected: {rc}')
        return rc

    try:
        checked(probe.action(0x32, 1)[0] == 0, 'Native HSS START failed')
        wait_for(lambda: reader.definition_verified and reader.samples > 0 or reader.error,
                 bool, 3, 'Native HSS did not receive DEF and data')
        checked(reader.error is None, f'Native HSS data invalid: {reader.error}')
        result['clock'] = clock()
        first = metrics(True)
        started = time.monotonic()
        time.sleep(seconds)
        last = metrics(True)
        elapsed = time.monotonic()-started
        window = [(after-before) & 0xffffffff for before,after in zip(first,last)]
        measured = window[1]/SCOPE_TICK_HZ
        produced, skipped = window[3], window[4]
        checked(measured >= seconds and produced > 0, 'Native HSS fixed window was not acquired')
        result.update(first=first, last=last, counterSeconds=measured, wallSeconds=elapsed,
                      groups=produced, groupsPerSecond=produced/measured, windowSkipped=skipped,
                      skipFraction=skipped/(produced+skipped), readErrors=window[6], dapYields=window[7])
    finally:
        try:
            wait_for(request_stop, lambda rc:rc == 0, 4, 'Native HSS STOP remained busy')
            quiet = reader.quiet_reads
            wait_for(lambda: reader.quiet_reads, lambda value: value > quiet,
                     2, 'Native HSS USB tail did not reach a fresh quiet read')
            end = metrics(False)
        except Exception as error:
            raise Unsafe(f'Native HSS STOP or release not confirmed: {error}') from error
        finally:
            reader.quit.set()
            reader.join(2)
            if reader.is_alive():
                raise Unsafe('Native HSS USB reader did not retire')
        result.update(definitionVerified=reader.definition_verified, usbBytes=reader.bytes,
                      formattedBytes=end[9], usbFrames=reader.packets, completedUsbFrames=end[8],
                      receivedGroups=reader.samples, finalProduced=end[3], finalSkipped=end[4],
                      tailCountDelta=reader.samples-end[3], transferByteDelta=reader.bytes-end[9],
                      dataFrames=reader.data_frames, allFramesVerified=reader.error is None,
                      droppedUsbFrames=end[8]-reader.packets, finalReadErrors=end[6], finalDapYields=end[7],
                      decodedTimelineSkips=reader.timeline_skips, finalMetrics=end, readerError=reader.error)

    checked(reader.error is None and reader.definition_verified and reader.data_frames > 0,
            f'Native HSS frame integrity failed: {reader.error}')
    checked(reader.samples == end[3] and reader.bytes == end[9] and reader.packets == end[8]
            and not end[6] and not end[7] and end[3] > 0,
            'Native HSS transport, final count or STOP tail differs')
    checked(result['skipFraction'] < .001 and end[4]/(end[3]+end[4]) < .001,
            'Native HSS fixed point exceeds the 0.1% scheduling skip threshold')
    checked(native_scope_rate_matches(result), 'Native HSS measured group rate differs from the fixed point')
