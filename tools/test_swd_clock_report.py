"""Check realized-clock reporting against fixed clock/divider examples."""
from unittest.mock import patch

from probe_build_info import live_clock_snapshot, swd_clock_details

old=swd_clock_details(99999999,0xa11)
assert old['SWCLK_Hz']==49999999.5 and not old['short_high']
# A 240-cycle half period at FCLK120 is 250kHz, not 60MHz.
minimum=swd_clock_details(120000000,(14<<28)|(15<<13)|(1<<19))
assert minimum['half_period_fclk']==240 and minimum['SWCLK_Hz']==250000
assert minimum['short_high'] and abs(minimum['intended_high_ns']-8.333333333)<1e-8
# Existing four-bit dividers retain their interpretation without short mode.
legacy=swd_clock_details(100000000,15<<13)
assert legacy['SWCLK_Hz']==3125000 and legacy['intended_high_ns']==160
print('PASS legacy, extended low-frequency and narrow-high waveform reporting')

# Stub XSCT before invoking the observer. No physical probe I/O.
base="LIVECLK 00100A20 00030000 00000000 00000000 00000000 00028000 00020000 00000000"
variable="SELECTIOCLK 00102C00 00000001 00000038 00000001 00000000"
with patch("jtag_internal_trace.run",return_value=f"{base}\n{variable}\nSELECTIOREF 00100800"):
    result=live_clock_snapshot()
    assert abs(result["actual_link_Hz"]-72727272.0)<0.01, result
    assert abs(result["etm_idelay_ref_hz"]-199999998.0)<0.01, result
fixed="SELECTIOCLK 00100800 04000001 00000038 00000000 00000000"
with patch("jtag_internal_trace.run",return_value=f"{base}\n{fixed}"):
    result=live_clock_snapshot()
    assert abs(result["actual_link_Hz"]-49999999.5)<0.01, result
print("PASS fixed and variable SelectIO MEM-AP clock reporting")
