# Deliveries

- fclk133-release-20261101/: new versioned RTL_DEBUG=0 delivery; ARM PLL /10 boot/offline DDR clock, paired bit/ELF and validation manifest. See its README for validated scope and the concurrent ETM/RTT limitation.
- golden/: unchanged 7020/120MHz comparison and rollback pair, target ELF/source and pinned OpenOCD.
- recovery/: complete previously accepted QSPI recovery package, including matching bit/ELF/BOOT and helpers.

The new delivery does not replace the Golden files or program QSPI. Historical versions are in archive/main-before-slim-20261031. Golden identity remains protected by golden-release.json and the Golden Git tag.
