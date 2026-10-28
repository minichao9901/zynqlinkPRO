# SWD high-pulse-width control

Use `gpio_oddr.bit` with `gpio.elf` for the independent fixture. With the same bit/ELF pair, direct clocks fail, ODDR short pulses pass, and direct clocks fail again at nominal 10kHz/100kHz/1MHz. Both 5ns and 10ns requested high pulses pass DPIDR/parity. Actual FCLK registers are recorded in the test JSON.

The separate `production_slow16.bit` + `main_no_usb.elf` pair removes USB/DAP firmware while keeping the production FPGA. It still reproduces ACK5/FE3F019F. This pair is an experiment, not USB probe firmware.

Build identity, exact SHA-256 hashes, timing, limits and evidence are in `manifest.json`. The standalone loader always restores an explicit full probe pair. The target Flash is untouched.
