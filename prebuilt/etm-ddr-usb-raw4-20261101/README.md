# DDR USB candidate, not Golden

Fresh bit/ELF and hashes in manifest.json. 120MHz FCLK / 60MHz max SWCLK STA passed.
Actual FCLK119,999,998Hz / SWCLK999,999.98Hz; no Flash/QSPI programmed.
F103ZE24MHz TRACECLK: 100ms,1s,2s hardware windows passed, USB bytes equal full physical MEM-AP0 readback.
Measured USB 35.94/38.01MB/s on 1s/2s records; frame/parser/ready losses and OpenCSD packet issues all zero.
Web fresh-session synchronization failures and fixes are retained, acceptance ongoing.
No higher TRACECLK or per-lane calibration acceptance; Golden unchanged.
