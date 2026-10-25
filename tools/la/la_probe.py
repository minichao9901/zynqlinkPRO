"""Probe the KingstVIS socket API for a working export-data syntax."""
import sys

sys.path.insert(0, r"E:\zynqlinkPRO\tools\la")
from kingst_la import Vis  # noqa: E402

v = Vis()
vis = v.__enter__() if hasattr(v, "__enter__") else v
try:
    print("last-error:", v.cmd("get-last-error"))
    print("rate:", v.cmd("get-sample-rate"))
    print("depth:", v.cmd("get-actual-sample-depth"))
    for cmd in (
        'export-data "E:/zynqlinkPRO/results/daplink/la/probe_a.csv"',
        'export-data "E:/zynqlinkPRO/results/daplink/la/probe_b.csv" --chn-select 0',
        'export-data "E:/zynqlinkPRO/results/daplink/la/probe_c.csv" 0',
        'export-data "E:\\zynqlinkPRO\\results\\daplink\\la\\probe_d.csv"',
    ):
        try:
            print(cmd, "->", v.cmd(cmd, timeout=60))
        except Exception as e:
            print(cmd, "-> ERR", e)
finally:
    v.close() if hasattr(v, "close") else None
