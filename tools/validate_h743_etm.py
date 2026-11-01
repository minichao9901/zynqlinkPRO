"""H743 continuous CDC load plus 10/200/500/1000 ms native ETMv4 captures.

The firmware/clock profile must already be programmed and verified. Never
programs Flash or alters target PLLs. Preserve failed captures; do not retry.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import zlib

import serial

ROOT = Path(__file__).resolve().parents[1]


class Echo:
    def __init__(self, port):
        self.port = serial.Serial(port, 115200, timeout=.02, write_timeout=1)
        self.stop = threading.Event()
        self.rows, self.error = [], None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            self.port.reset_input_buffer()
            for seq in range(100000):
                if self.stop.is_set(): break
                body = f'H743_ETM_{seq:06d}'.encode()
                payload = body+f'_{zlib.crc32(body):08x}\r\n'.encode()
                sent_monotonic = time.monotonic()
                sent = time.time()
                self.port.write(payload)
                data = bytearray()
                until = time.monotonic()+10
                while payload not in data and time.monotonic()<until:
                    data.extend(self.port.read(self.port.in_waiting or 1))
                exact = payload in data
                self.rows.append(dict(seq=seq, sentUnix=sent, receivedUnix=time.time(), bytes=len(payload),
                                      exact=exact, receivedSha256=hashlib.sha256(data).hexdigest()))
                if not exact: raise RuntimeError('CRC-tagged CDC echo missing: '+str(seq))
                # Event.wait(4ms) is rounded to ~15.6ms on this Windows host.
                # Python's high-resolution sleep keeps the actual send period
                # near 4ms; record timestamps rather than trusting the request.
                time.sleep(max(0,.004-(time.monotonic()-sent_monotonic)))
        except Exception as error: self.error=repr(error)

    def close(self):
        self.stop.set(); self.thread.join(11); self.port.close()
        return dict(rows=self.rows,error=self.error,threadStopped=not self.thread.is_alive(),requestedSendPeriodSeconds=.004)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target-elf',type=Path,required=True)
    p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--cdc-port',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--windows-ms',default='10,200,500,1000');p.add_argument('--repeats',type=int,default=3)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for window in map(int,a.windows_ms.split(',')):
        for repeat in range(a.repeats):
            label=f'{window}ms-{repeat+1}';record=a.out/label
            echo=Echo(a.cdc_port);echo.thread.start();time.sleep(.15)
            argv=[sys.executable,'-X','utf8','toolbox.py','trace','capture','--elf',str(a.target_elf),
                  '--bit',str(a.bit),'--zynq-elf',str(a.elf),'--out',str(record),'--seconds',str(window/1000),
                  '--swd-khz','10000','--gpio-speed','2','--json-out',str(a.out/(label+'-result.json'))]
            started=time.perf_counter()
            print('START',label,flush=True)
            try:
                completed=subprocess.run(argv,cwd=ROOT,capture_output=True)
                elapsed=time.perf_counter()-started
                (a.out/(label+'.log')).write_bytes(completed.stdout+completed.stderr)
            finally:stimulus=echo.close()
            (a.out/(label+'-echo.json')).write_text(json.dumps(stimulus,indent=2)+'\n')
            row=dict(windowMs=window,repeat=repeat+1,argv=argv,elapsedSeconds=elapsed,
                     recordedAtUtc=datetime.now(timezone.utc).isoformat(),returncode=completed.returncode)
            result=json.loads(completed.stdout)
            row.update(ok=result.get('ok'),result=result.get('result'),error=result.get('error'))
            q=(row.get('result') or {}).get('quality') or {}
            bracket=q.get('hardwareStartBracketUnix')
            if bracket:
                margin=min(.02,window/10000)
                lo,hi=bracket[1]+margin,bracket[0]+q['hardwareSeconds']-margin
                row['guaranteedEchoWindow']=[lo,hi]
                row['echoInsideWindow']=sum(r['exact'] and lo<=r['sentUnix']<=r['receivedUnix']<=hi for r in stimulus['rows'])
            row.update(echoPackets=len(stimulus['rows']),echoExact=all(r['exact'] for r in stimulus['rows']),
                       echoError=stimulus['error'],echoThreadStopped=stimulus['threadStopped'])
            rows.append(row);(a.out/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
            assert completed.returncode==0 and row['ok'] and row['echoExact'] and not row['echoError'], row
            assert window<200 or row.get('echoInsideWindow',0)>0, 'No echo proven inside hardware window'
            assert q.get('requestedWindowComplete') and not q.get('loss'),q
            assert row['result']['summary']['packetIssues']==0,row
            print('PASS',label,round(elapsed,3),'echoInside',row.get('echoInsideWindow'),flush=True)


if __name__=='__main__':main()
