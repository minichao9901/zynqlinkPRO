"""Arm/read the 32-scan passive JTAG history in the diagnostic bitstream.

CSR 0xCC: signature 0x4A54, frozen[12], armed[11], count[10:5], head[4:0].
Write 3 to clear+arm; write 4 to freeze. 0xD0 selects a row, 0xD4..F4
return meta/frontend/latched/TX/pad/RX/extra/alternate-RX/ACK sample windows.
XSCT uses the Zynq debug port; this does not scan the target JTAG interface.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(body):
    work = ROOT / 'build/jtag_internal_trace'
    work.mkdir(parents=True, exist_ok=True)
    script = work / 'read_trace.tcl'
    script.write_text('connect\ntargets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}\n'
                      + body + '\ndisconnect\nexit\n', encoding='ascii')
    return subprocess.check_output([sys.executable, str(ROOT / 'tools/run_xsct.py'), str(script)],
                                   text=True, encoding='utf-8', errors='replace')


def control():
    result = run('set s [mrd -force -value 0x400100cc]\n'
                 'if {($s >> 16) != 0x4a54} {error "JTAG trace bitstream signature missing"}\n'
                 'mwr -force 0x400100cc 3\nputs "ARMED"')
    assert 'ARMED' in result, result


def dump(path):
    text = run('mwr -force 0x400100cc 4\n'
               'set s [mrd -force -value 0x400100cc]\nputs [format "STATUS %08X" $s]\n'
               'set n [expr {($s >> 5) & 63}]\n'
               'if {$n > 32} {error "Invalid JTAG trace count"}\n'
               'for {set i 0} {$i < $n} {incr i} {\n'
               ' mwr -force 0x400100d0 $i\n set line "TRACE $i"\n'
               ' for {set a 0x400100d4} {$a <= 0x400100f4} {incr a 4} {\n'
               '  append line [format " %08X" [mrd -force -value $a]]\n }\n puts $line\n}')
    status = re.search(r'STATUS ([0-9A-Fa-f]{8})', text)
    assert status, text
    rows = []
    fields = ['meta', 'frontend', 'latched', 'tx', 'pad', 'rx', 'extra', 'alternate_rx', 'samples']
    for match in re.finditer(r'TRACE (\d+)((?: [0-9A-Fa-f]{8}){9})', text):
        values = [int(v, 16) for v in match[2].split()]
        row = dict(zip(fields, values))
        meta = row['meta']
        row.update(index=int(match[1]), timestamp=meta >> 19, operation=(meta >> 16) & 7,
                   phase=(meta >> 14) & 3, request=(meta >> 6) & 255,
                   raw_ack=(meta >> 3) & 7, ack=meta & 7,
                   tx_request=row['extra'] & 7, pad_request=(row['extra'] >> 3) & 7)
        row['tx_matches_latched'] = row['tx'] == row['latched']
        row['pad_matches_tx'] = row['pad'] == row['tx']
        row['ack_windows'] = {str(offset): {
            'selected_raw': (row['samples'] >> offset) & 7,
            'alternate_raw': (row['samples'] >> (16 + offset)) & 7}
            for offset in range(2, 7)}
        rows.append(row)
    report = {'status': int(status[1], 16), 'rows': rows}
    assert len(rows) == (report['status'] >> 5) & 63, text
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    path.with_suffix('.txt').write_text(text)
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['arm', 'dump'])
    ap.add_argument('--output', type=Path, default=ROOT / 'build/jtag_internal_trace/capture.json')
    args = ap.parse_args()
    if args.action == 'arm':
        control()
    else:
        report = dump(args.output)
        for row in report['rows']:
            print('scan=%d phase=%d req=%02x ack=%d front=%08x latch=%08x tx=%08x pad=%08x rx=%08x' %
                  tuple(row[k] for k in ('index', 'phase', 'request', 'ack', 'frontend', 'latched', 'tx', 'pad', 'rx')))
