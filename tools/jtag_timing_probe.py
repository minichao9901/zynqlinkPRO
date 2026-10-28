"""Report the FCLK the firmware actually programmed for each requested clock.

Uses vendor command 0x80 (query only, 255) which recomputes FCLK from
SLCR_FPGA0_CLK_CTRL on the PS side, so it sees the same value the JTAG PHY
runs at.
"""
import argparse
import json

from dap_pipeline_bench import open_dap, cmd, le, setup


def query(out, inp):
    r = cmd(out, inp, [0x80, 255])
    hz = int.from_bytes(r[4:8], 'little')
    cfg = int.from_bytes(r[8:12], 'little')
    return hz, cfg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speeds', default='30000,42000,43000,45000,50000,53000,60000')
    a = ap.parse_args()
    dev, out, inp = open_dap()
    rows = []
    try:
        for khz in (int(x) for x in a.speeds.split(',')):
            row = {'khz': khz}
            try:
                setup(out, inp, khz, 'jtag')
                row['idcode_ok'] = True
            except Exception as exc:                      # noqa: BLE001
                row['idcode_ok'] = False
                row['error'] = str(exc)[:80]
            hz, cfg = query(out, inp)
            row['fclk_hz'] = hz
            row['tck_hz'] = hz // 2
            row['swd_cfg'] = hex(cfg)
            rows.append(row)
            print(json.dumps(row), flush=True)
    finally:
        cmd(out, inp, [0x02, 0])
    print(json.dumps(rows))


if __name__ == '__main__':
    main()
