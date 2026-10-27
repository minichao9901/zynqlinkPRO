"""Localize the JTAG failure by exercising individual DAP operations per speed.

Every speed starts from the same known-good state: the repo's ``setup()``
connects the transport, switches SWJ to JTAG, configures the scan chain and
clears MEM-AP sticky errors. Each named operation then runs ``--repeat`` times
so a marginal break shows up as a partial ratio instead of a single bool.
"""
import argparse
import json
from pathlib import Path

from dap_pipeline_bench import open_dap, cmd, le, setup, xfer

OPS = {
    'dp_select_w': [(0x08, 0x00000000)],
    'ap_csw_w': [(0x01, 0x23000052)],
    'ap_tar_w': [(0x05, 0x20004000)],
    'ap_w2': [(0x01, 0x23000052), (0x05, 0x20004000)],
    'dp_w_ap_w': [(0x08, 0x00000000), (0x01, 0x23000052)],
    'ap_w_dp_w': [(0x01, 0x23000052), (0x08, 0x00000000)],
    'ap_w3': [(0x08, 0x00000000), (0x01, 0x23000052), (0x05, 0x20004000)],
    'ap_r2': [(0x0F, None), (0x0F, None)],
    'dp_ctrlstat_r': [(0x06, None)],
}


def transfer(out, inp, reqs):
    pkt = [0x05, 0x00, len(reqs)]
    for request, value in reqs:
        pkt.append(request)
        if value is not None:
            pkt += le(value)
    r = xfer(out, inp, pkt)
    if not r or r[0] != 0x05:
        return 'echo:%s' % r.hex(' ')
    return r[2] if len(r) > 2 else 'short'


def set_timing(out, inp, mode):
    """Pin IDDR Q2/Q1 (bit0), current/previous DR window (bit4)."""
    r = cmd(out, inp, [0x89, mode])
    return r[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speeds', default='30000,35000,40000,45000,50000,55000,60000')
    ap.add_argument('--repeat', type=int, default=10)
    ap.add_argument('--timing', type=int, default=None,
                    help='pin JTAG TDO sampling mode instead of auto calibration')
    ap.add_argument('--output', type=Path)
    a = ap.parse_args()

    dev, out, inp = open_dap()
    rows = []
    try:
        for khz in (int(x) for x in a.speeds.split(',')):
            row = {'khz': khz}
            if a.timing is not None:
                row['timing'] = a.timing
            try:
                reply = setup(out, inp, khz, 'jtag')
                row['idcode'] = reply[2:6].hex(' ')
            except Exception as exc:                      # noqa: BLE001
                row['setup_error'] = str(exc)[:160]
                rows.append(row)
                print(json.dumps(row), flush=True)
                continue
            if a.timing is not None:
                cmd(out,inp,[0x11]+le(khz*1000))
                row['timing_applied'] = set_timing(out, inp, a.timing)
                idc = cmd(out, inp, [0x16, 0])
                row['idcode'] = idc[2:6].hex(' ') if len(idc) >= 6 else idc.hex(' ')
            for name, reqs in OPS.items():
                acks = [transfer(out, inp, reqs) for _ in range(a.repeat)]
                ok = sum(1 for x in acks if x == 1)
                row[name] = '%d/%d' % (ok, len(acks))
                if ok != len(acks):
                    row[name + '_acks'] = sorted({str(x) for x in acks})
            state=cmd(out,inp,[0x80,255]);timing=cmd(out,inp,[0x89,255])
            row.update(actual_fclk_hz=int.from_bytes(state[4:8],'little'),sampling_mode=timing[2])
            row['actual_tck_hz']=row['actual_fclk_hz']//2
            rows.append(row)
            print(json.dumps(row), flush=True)
    finally:
        if a.output:
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(json.dumps(rows, indent=2))
        cmd(out, inp, [0x02, 0])


if __name__ == '__main__':
    main()
