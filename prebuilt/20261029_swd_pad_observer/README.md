# Standalone SWD clock-pad diagnostic

Source and SHA-256 identities, exact bit/ELF pairs, build options and limitations are in `manifest.json`.
Load either `slow4.bit` or `slow16.bit` with the same `minimal_swd.elf`; this firmware is a mailbox fixture, not a USB probe.
The source commit records the default SLOW/4 design. The SLOW/16 file changes only the output-drive property on its frozen routed checkpoint.

The independent SLOW/16 DPIDR result passes; the full probe is still under investigation. Neither pair is accepted for production memory transfers.
No extra FPGA-side edge was counted in either case. This does not measure the waveform at the target MCU.
The invalid first-read CTRL/STAT experiment is explicitly excluded from the evidence.
