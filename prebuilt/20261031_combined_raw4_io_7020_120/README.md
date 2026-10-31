# Combined RAW4 7020/120MHz with bounded SWCLK launch

JTAG/RAM transport, PS and50/60MHz SOTA acceptance passed. ETM/Web acceptance remains with the peer thread. No QSPI writes; no new persisted BOOT in this package.

Load probe.bit + application.elf with ps7_init.tcl. Bit SHA1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473; ELF SHAe977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c. application_50.elf is the validated50MHz-cap variant. See manifest.json and docs/validation/combined-20261031 for complete source, timing, resource, clock, failure/control and acceptance evidence.
