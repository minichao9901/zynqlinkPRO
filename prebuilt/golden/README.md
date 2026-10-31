# Golden: Zynq-7020 /120MHz, JTAG RAM

Accepted bit SHA-256:1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473.
Accepted PS ELF SHA-256:e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c.
Target F103ZE CDC48 ELF:e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f.

Unchanged accepted bytes curated from311fc3b/6df6298. No PL/PS rebuild or board programming in this cleanup. RTL/application sources954de8f, bounded I/O constraint9bfd403, static verifierdcd4f3e. Full RAW4/FIFO16, WNS+.167ns/WHS+.024ns; OCM span120976B. USB/DAP queues unchanged.

Transport/SOTA and documented ETM/Web points passed. Cross-session HSS missingDEF is DEFERRED, not fixed. Golden was not QSPI-programmed; recovery package contains the previously accepted QSPI image.

Use probe.bit + application.elf + ps7_init.tcl. f103ze-cdc48.elf/source-snapshot are the matching target dependency. host/openocd contains the pinned prior OpenOCD deployment and source/license information. golden-release.json gives component identities and scope.
