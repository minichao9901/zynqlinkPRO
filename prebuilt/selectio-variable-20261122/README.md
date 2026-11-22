# SelectIO 可变时钟离线候选

| 镜像 | 配对清单 |
|---|---|
| 融合版 | [full](full/manifest.json) |
| JTAG/HSS/RTT + SPI | [jtag](jtag/manifest.json) |
| SWD/HSS/RTT + COM/SWO/ETM | [swd](swd/manifest.json) |

每个目录中的 probe.bit、application.elf 和 ps7_init.tcl 按该目录的清单配套。三套均有 Vivado 2018.3 路由时序、bitgen、Xilinx SDK 2018.3 ELF 链接和离线加载预检的证据。本轮验收范围为离线。融合版是初版候选，两套裁剪版用于分析。

[时钟、仿真、路由与 PCAP 取舍](../../docs/validation/selectio-variable-20261122/README.md)
