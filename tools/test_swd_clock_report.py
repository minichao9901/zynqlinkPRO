"""Check realized-clock reporting against fixed clock/divider examples."""
from probe_build_info import swd_clock_details

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
