"""Inspect/recover DAP USB queues through EP0 without reloading bit/ELF.

Close OpenOCD first so this process can claim the WinUSB DAP interface.
Recovery discards pending DAP requests/responses. It does not reprogram target
flash or reset the target, and does not claim to reset a stuck RTL engine.
"""
import argparse
import json
import struct

import usb.core
import usb.util
from dap_pipeline_bench import open_dap, xfer

FIELDS = ['pending_requests', 'pending_responses', 'tx_active', 'session_epoch',
          'backpressure_events', 'submit_errors', 'nonfinal_callbacks', 'rx_deferred']

def snapshot(dev):
    raw = dev.ctrl_transfer(0xc0, 0x5b, 0x4441, 0x5052, 32, timeout=3000)
    return dict(zip(FIELDS, struct.unpack('<8I', raw)))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['state', 'recover'])
    a = ap.parse_args()
    dev, out, inp = open_dap()
    try:
        result = {'before': snapshot(dev)}
        if a.action == 'recover':
            r = bytes(dev.ctrl_transfer(0xc0, 0x5a, 0x4441, 0x5052, 4, timeout=3000))
            if r != b'DAP\0':
                raise RuntimeError(f'Endpoint recovery failed: {r.hex()}')
            dev.clear_halt(0x81)
            dev.clear_halt(0x02)
            for n in range(64):
                try:
                    inp.read(4096, timeout=80)
                except usb.core.USBTimeoutError:
                    break
            else:
                raise RuntimeError('Responses did not drain after recovery')
            result['drained_prefetched_responses'] = n
            result['capabilities'] = xfer(out, inp, [0, 0xf0]).hex()
        result['after'] = snapshot(dev)
        print(json.dumps(result, indent=2))
    finally:
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)

if __name__ == '__main__':
    main()
