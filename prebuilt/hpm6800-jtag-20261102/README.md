# HPM6800EVK RISC-V JTAG accepted pair — 2026-11-02

Load `probe.bit` + `application.elf` + `ps7_init.tcl`. HPM6800EVK SRAM/RTT/HSS passed at the documented frequency points. This separately named pair does not replace Golden/recovery or certify ARM/ETM/QSPI boot.

25MHz TCK: AXI SRAM read/write 1.632/1.622MB/s; RTT 1.487MB/s. HSS 1×/8×u32: 137.931/23.715kSamples/s, three 10-second zero-skip windows. Low-rate HSS uses the explicit shared RTT clock setter; public HSS clock setter minimum remains 15MHz.

Hashes, exact source inputs and timing are in manifest.json. Full evidence: [acceptance report](../../docs/validation/hpm6800-acceptance-20261102/README.md). No Flash/QSPI programming. Failed FCLK100/TCK25 experiment artifacts are separate and are not accepted.
