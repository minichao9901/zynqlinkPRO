# SelectIO 变频实测配对

三套 bit、PS 初始化脚本来自对应的离线时序候选。配套 ARM ELF 含有在同频 SelectIO 下直接接管 AP 上下文的修正。表中各目录包含实际加载的文件及 SHA-256。

| 目录 | 实板范围 |
|---|---|
| [full](full/manifest.json) | 50、72.727、100 MHz SWD SRAM/RTT，100 MHz JTAG SRAM/RTT |
| [swd](swd/manifest.json) | 50、72.727、100 MHz SWD SRAM/RTT |
| [jtag](jtag/manifest.json) | 100 MHz JTAG SRAM/RTT |

F103ZE 测试固定 HCLK128。SWD tap8，50 MHz 用 slot24 / idle0，72.727 MHz 用 slot22 / idle0，100 MHz 用 slot25 / idle2。JTAG 100 MHz 同频比较用 tap16、slot28、idle33。原生 profile 命令可写入这些参数，72.727 MHz 用 73000000 Hz 请求选档。50 MHz 的稳定采样档尚未达到历史 PC 吞吐。

[现场、时钟、失败证据和原始计数](../../docs/validation/selectio-variable-board-20261122/README.md)
