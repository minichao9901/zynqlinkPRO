# JTAG internal scan diagnostic pair

Source: 6b14b58. This pair verifies the passive scan-history function; it does not fix the existing target JTAG write corruption.

Load both zynqlink_jtag_trace.bit and zynqlink_jtag_trace.elf with tools/download_dap_fpga.tcl. Hashes, timing and the exact load command are in manifest.json. Original prebuilt/20261028_swd_jtag is unchanged.

At actual FCLK=99,999,999 Hz / TCK=49,999,999 Hz, 4/8-word writes reproduce corruption. All intended/latched/serial-TX/pad-echo data match. Raw ACK alternates WAIT then OK on the subsequent words; both IDDR phases agree. SRAM restored via SWD (restore_match=true).
