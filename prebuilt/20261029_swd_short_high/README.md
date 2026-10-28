# SWD short-high board profile, 2026-10-29

Load `probe.bit` with `probe.elf`. This is the accepted pair for the current F103CB and wiring; it retains the existing passive SWD/JTAG trace and clock observer. Low SWD rates use one-FCLK high pulses with an extended divider. Existing known-good pairs elsewhere in `prebuilt/` remain available.

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/20261029_swd_short_high/probe.elf prebuilt/20261029_swd_short_high/probe.bit
```

See `manifest.json` for exact SHA-256, source commit, build settings, timing and evidence identities, and [the acceptance record](../../docs/SWD窄脉宽修复验收-20261029.md) for scope and limitations. Raw evidence is in `results/swd/short_high_20261029/`.

Acceptance covers 43 requested SWD rates from 250 kHz through 60 MHz, six JTAG rates, restored random SRAM data, RTT at 1/15/50 MHz, HSS at 15/50 MHz, and real-CM3 simulation including 1023-word blocks. HSS/RTT rate limits retain their existing values. Requested and actual clocks differ where PLL division or JTAG calibration requires it.

`rejected/early_profile.elf` and `rejected/q2_late_profile.elf` are failed intermediate receive profiles paired with this same `probe.bit`. They are diagnostic comparisons, not accepted replacements. The manifest lists their hashes and failure evidence.

This is a board-specific functional workaround. Target-side analog waveforms and the physical root cause remain unmeasured. No target flash was programmed. No SWCLK pull-up was added; the existing SWDIO pull-up remains enabled.
