# Bounded RAW4 DDR trace candidate

Not Golden. Fresh RTL d212517 and freshly rebuilt PS ELF; source/hash/options in manifest.json.
120MHz FCLK / 60MHz maximum SWCLK static timing passed; this is not a TRACECLK claim.
First real F103ZE 24MHz TRACECLK / exact 1s window passed with physical AP0 readback and native ETMv3 decode.
19,277,266 formatter bytes -> 4,567,468 ETM bytes; no frame drops/parser errors/ready loss; packetIssues=0.
Two 1MiB memory-pattern rounds passed without reload; actual FCLK119,999,998Hz and SWCLK999,999.98Hz.
Full stress, Web/USB DDR download and higher TRACECLK/lane-calibration acceptance remain pending.
Evidence: docs/validation/etm-ddr-trace-board-20261101. No Flash/QSPI programmed.
PS USB DDR download is not implemented. Existing Golden remains unchanged.
