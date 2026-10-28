# JTAG internal scan diagnostic pair

Source: 6b14b58. This pair verifies the passive scan-history function; it does not fix the existing target JTAG write corruption.

Load both zynqlink_jtag_trace.bit and zynqlink_jtag_trace.elf with tools/download_dap_fpga.tcl. Hashes, timing and the exact load command are in manifest.json. Original prebuilt/20261028_swd_jtag is unchanged.

At actual FCLK=99,999,999 Hz / TCK=49,999,999 Hz, 4/8-word writes reproduce corruption. All intended/latched/serial-TX/pad-echo data match. Raw ACK alternates WAIT then OK on the subsequent words; both IDDR phases agree. SRAM restored via SWD (restore_match=true).

## Preserved baseline

The passive trace code, reader, evidence and paired bit/ELF are committed on main.
The annotated tag `probe-jtag-passive-trace-120mhz-20261028` preserves this baseline
for recovery and comparison. It is a local Git tag until explicitly pushed.
Keep this named pair available when testing later changes; the rejected WAIT-exit
experiment is stored separately and is not the active passive trace design.

## What the trace observes

The history can replace an external logic analyzer for the recorded internal
requests, payload progression, transmitted digital bits and sampled ACK/data.
The TDI pad echo observes the FPGA end at discrete FCLK instants. It does not
prove the voltage or setup/hold margin at the target MCU end of the cable.
It cannot measure analog ringing, overshoot, ground bounce or unobserved glitches.
The 120 MHz routed timing result is an FPGA timing result, not acceptance of the
complete 60 MHz off-board interface over arbitrary cables.

The user reports loose Dupont wires and no attached logic analyzer. Cable-related
signal integrity is a hypothesis, not a proven root cause. For a controlled test,
keep this exact bit/ELF, actual FCLK/TCK and sampling mode fixed; change only wire
length/ground return, then compare the same poisoned-memory write/readback test.
Start with shorter connections and a close ground return beside TCK. Source-side
damping is a separate experiment, not an assumed fix.

Vendor references: [XJTAG grounding guide](https://docs.xjtag.com/xjtag/current/userguide/jtagsetup/grounding.html),
[SEGGER signal damping](https://www.segger.com/products/production/flasher/accessories/adapters/signal-smoothing-adapter/).
