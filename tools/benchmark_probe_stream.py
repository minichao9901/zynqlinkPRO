"""Measure the shipped probe pair, with warmup excluded and target RAM restored.

HSS loss = skipped / (produced + skipped) in the same 24MHz counter window.
Host USB is drained continuously in a separate thread; all received frames are
checked and the post-STOP sample count must equal the probe's produced count.
"""
import argparse
import array
import hashlib
import json
from pathlib import Path
import random
import struct
import threading
import time

import usb.core
import usb.util

from dap_pipeline_bench import open_dap, setup
from probe_stream import Probe
from test_probe_board import Memory, drain_hss, stop
from probe_build_info import provenance,live_clock_snapshot


class HssReader(threading.Thread):
    def __init__(self, dev, expected, period, allow_duplicate_stat=False):
        super().__init__(daemon=True)
        self.dev, self.expected = dev, expected
        self.quit = threading.Event()
        self.samples = self.packets = self.bytes = 0
        self.previous_seq = None
        self.previous_data = None
        self.error = None
        self.period=period
        self.timeline_skips=0
        self.allow_duplicate_stat=allow_duplicate_stat
        self.control_sequence_errors=[]
        self.data_frames=0          # kind-2 frames byte-compared against the fixture
        self.stat_frames=0          # kind-3 counter frames

    def consume(self, data):
        assert len(data) % 512 == 0, len(data)
        for off in range(0, len(data), 512):
            magic, ver, kind, seq, stamp, n, aux = struct.unpack_from('<HBBIIHH', data, off)
            assert magic == 0x4a53 and ver == 2
            if self.previous_seq is not None:
                if seq!=((self.previous_seq+1)&0xffffffff):
                    if self.allow_duplicate_stat and kind==3 and seq==self.previous_seq:
                        self.control_sequence_errors.append(dict(kind=kind,previous_seq=self.previous_seq,seq=seq,timestamp=stamp))
                    else:raise AssertionError(('frame sequence',self.previous_seq,seq,'kind',kind,'timestamp',stamp,'samples',n))
            self.previous_seq=seq
            if kind == 2:
                assert aux == n*len(self.expected) and n > 0
                self.validate_values(data[off+16:off+16+aux],n,seq,stamp)
                self.data_frames += 1
                if self.previous_data is not None:
                    previous_stamp,previous_n=self.previous_data
                    delta=(stamp-previous_stamp)&0xffffffff
                    missing=delta-previous_n*self.period
                    assert missing>=0 and missing%self.period==0, ('compressed timeline',self.previous_data,stamp,n)
                    self.timeline_skips+=missing//self.period
                self.previous_data=(stamp,n)
                self.samples += n
            elif kind == 3:
                self.stat_frames += 1
            self.packets += 1
        self.bytes += len(data)

    def validate_values(self,data,n,seq,stamp):
        assert data==self.expected*n,(seq,stamp,n,len(data))

    def run(self):
        try:
            while not self.quit.is_set():
                try:
                    # PyUSB preserves partial data returned on a libusb timeout.
                    data = bytes(self.dev.read(0x87, 32768, timeout=50))
                    self.consume(data)
                except usb.core.USBTimeoutError:
                    pass
        except BaseException as exc:
            self.error = repr(exc)


def hss_point(probe, mem, dev, speed, period, nvars, seconds, repeat, allow_low_clock=False, activate_transport=None, allow_duplicate_stat=False):
    base = 0x20004000
    fixture = random.Random(0x485353).randbytes(4096)
    mem.write(base, fixture)
    assert mem.read(base,4096)==fixture,'HSS fixture did not verify'
    if activate_transport:activate_transport()
    variables = [(base+256+4*i, 4, 4) for i in range(nvars)]
    expected = fixture[256:256+4*nvars]
    clock_rc=probe.action(0x32,3,struct.pack('<I',speed))[0]
    clock_method='HSS public clock setter'
    if clock_rc==-6 and allow_low_clock and 1000000<=speed<15000000:
        # Services share requested_hz. Exercise the existing low-rate path
        # without changing the accepted firmware or lying about its API.
        assert probe.action(0x31,7,struct.pack('<IHBB',speed,1024,0,1))[0]==0
        clock_method='shared RTT clock setter (HSS public setter rejected low rate)'
    else:assert clock_rc==0,('HSS clock rejected',clock_rc,speed)
    cfg = struct.pack('<IBB', period, 0, nvars)+b''.join(struct.pack('<IBB', *v) for v in variables)
    assert probe.action(0x32, 10, cfg)[0] == 0
    drain_hss(dev)
    reader = HssReader(dev, expected, period,allow_duplicate_stat)
    reader.start()
    final = None
    partial=None
    try:
        start_rc=probe.action(0x32,1)[0]
        assert start_rc==0,('HSS start rejected',start_rc,'requested clock',speed)
        time.sleep(0.25)
        clock=live_clock_snapshot()
        t0 = time.perf_counter()
        rc, m0 = probe.action(0x32, 11)
        t0 = (t0+time.perf_counter())/2
        assert rc == 0, (rc, m0)
        host0 = reader.samples
        time.sleep(seconds)
        t1 = time.perf_counter()
        rc, m1 = probe.action(0x32, 11)
        t1 = (t1+time.perf_counter())/2
        assert rc == 0, (rc, m1)
        host1 = reader.samples
        delta=[(b-a)&0xffffffff for a,b in zip(m0,m1)]
        tick_hz=min(24000000,clock['FCLK_Hz']);dt=delta[1]/tick_hz
        partial=dict(service='hss',speed_hz=speed,period_ticks=period,requested_Hz=tick_hz/period,
                     effective_Hz=delta[3]/dt,skip_percent=100*delta[4]/(delta[3]+delta[4]),
                     produced=delta[3],skipped=delta[4],counter_window_s=dt,period_clock_Hz=tick_hz,
                     m0=m0,m1=m1,**clock)
        for _ in range(100):
            rc, _ = probe.action(0x32, 0)
            if rc == 0:
                break
            assert rc == -7, rc
            time.sleep(0.01)
        else:
            raise RuntimeError('STOP did not finish')
        time.sleep(0.12)
        reader.quit.set()
        reader.join(2)
        assert not reader.is_alive() and reader.error is None, reader.error
        drain_hss(dev, reader.consume)
        rc, final = probe.action(0x32, 11)
        assert rc == 0 and reader.samples == final[3], (reader.samples, final)
        delta = [(b-a) & 0xffffffff for a, b in zip(m0, m1)]
        # The sampler advances at most one timer tick per FCLK. Below
        # 24MHz (experimental low-rate JTAG), the timer cannot run at 24MHz.
        tick_hz=min(24_000_000,clock['FCLK_Hz'])
        dt = delta[1]/tick_hz
        produced, skipped = delta[3], delta[4]
        row = {'service': 'hss', 'speed_hz': speed, 'period_ticks': period,
               **clock,
               'clock_setter_rc':clock_rc,'clock_method':clock_method,
               'requested_Hz': tick_hz/period,'nominal_24MHz_requested_Hz':24_000_000/period,
               'period_clock_Hz':tick_hz,'variables': nvars, 'repeat': repeat,
               'counter_window_s': dt, 'host_window_s': t1-t0,
               'produced': produced, 'skipped': skipped,
               'effective_Hz': produced/dt, 'skip_percent': 100*skipped/(produced+skipped),
               'host_received_Hz': (host1-host0)/(t1-t0),
               'swd_errors': delta[6], 'DAP_yields': delta[7],
               'session_received_samples': reader.samples, 'session_packets': reader.packets,
               # 'all_data_frames_verified' is the real byte check: every kind-2 frame is
               # compared byte-for-byte against the fixture in HssReader.validate_values
               # and raises on mismatch. 'all_frames_byte_exact' is a historical misnomer:
               # it only reports duplicate control/stat frames (kind=3, same sequence),
               # which carry counters, not samples. Keep both, but read the new names.
               'all_data_frames_verified': True,
               'data_frames_verified': reader.data_frames,
               'stat_duplicate_frames': len(reader.control_sequence_errors),
               'all_frames_byte_exact': not reader.control_sequence_errors,
               'sample_count_match': True,
               'control_sequence_errors': reader.control_sequence_errors,
               'all_frame_sequences_valid': not reader.control_sequence_errors,
               'timeline_gaps_preserved':True,'session_timeline_skipped':reader.timeline_skips,
               'm0': m0, 'm1': m1, 'final': final}
        assert delta[6] == 0 and delta[7] == 0, row
        return row
    except Exception as exc:
        if partial is not None:
            partial.update(validation_error=repr(exc),sample_count_match=False,
                           session_received_samples=reader.samples,control_sequence_errors=reader.control_sequence_errors)
            if final is not None:partial['final']=final
            exc.measurement=partial
        raise
    finally:
        probe.action(0x32, 0)
        reader.quit.set()
        reader.join(2)
        drain_hss(dev)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seconds', type=float, default=2)
    ap.add_argument('--speeds', default='50000000,60000000')
    ap.add_argument('--periods', default='2400,480,240,160,120,96,72,60,48')
    ap.add_argument('--variables', default='1,8')
    ap.add_argument('--repeats', type=int, default=1)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--bit',type=Path)
    ap.add_argument('--elf',type=Path)
    ap.add_argument('--transport', choices=['swd','jtag'], default='swd')
    ap.add_argument('--allow-duplicate-stat', action='store_true',
                    help='Diagnostic only: record repeated kind-3 status sequences; data/count checks remain strict')
    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    probe = Probe()
    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    backup = initial = None
    report = {'artifacts':provenance(args.bit,args.elf), 'kind': 'HSS sustained end-to-end sweep',
              'allow_duplicate_stat_diagnostic': args.allow_duplicate_stat, 'rows': []}
    try:
        stop(probe, dev)
        setup(out, inp, 50000, args.transport)
        # The probe services keep their own transport flag; set it after the DAP setup.
        rc_tr = probe.action(0x31, 12, bytes([2 if args.transport == 'jtag' else 1]))[0]
        if rc_tr not in (0, -7):
            print('transport flag ->', rc_tr)
        initial = mem.word(0xe000edf0)
        if not initial & (1 << 17):
            mem.write_word(0xe000edf0, 0xa05f0003)
        backup = mem.read(0x20004000, 4096)
        args.output.with_suffix('.backup.bin').write_bytes(backup)
        report['backup_sha256'] = hashlib.sha256(backup).hexdigest()
        for speed in map(int, args.speeds.split(',')):
            for nv in map(int, args.variables.split(',')):
                for period in map(int, args.periods.split(',')):
                    for repeat in range(args.repeats):
                        row = hss_point(probe, mem, dev, speed, period, nv, args.seconds, repeat,
                                        allow_duplicate_stat=args.allow_duplicate_stat)
                        report['rows'].append(row)
                        args.output.write_text(json.dumps(report, indent=2))
                        print(json.dumps({k: v for k, v in row.items() if k not in ('m0','m1','final')}), flush=True)
    finally:
        try:
            stop(probe, dev)
            if backup is not None:
                setup(out, inp, 50000, args.transport)
                mem.write(0x20004000, backup)
                restored = mem.read(0x20004000, 4096)
                report['restore_match'] = restored == backup
                assert report['restore_match']
            if initial is not None and not initial & (1 << 17):
                mem.write_word(0xe000edf0, 0xa05f0001)
        finally:
            args.output.write_text(json.dumps(report, indent=2))
            probe.close()
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
