# J7 转接板 SWD 66.666 MHz 性能

2026-11-06（上海时间）。沿用 J7 已验收 bit `792d4b6c…65abc` 及 7.5 ns 实现时序，setup/hold 余量 0.074/0.054 ns。由源码 `8ce26c56` 重新编译转接板专用固定时钟 PS，ELF SHA-256 `c58d209f882af3dc1ed1d15671444f4e910b00e4e42077f19d590930385df374`。核对探针租约、DDR、DMA、HSS 和 RTT 空闲后，用 JTAG/RAM 加载实际配对。物理 MEM-AP0 核对实验 PS 的 85068 B 执行段。 实验配对（历史归档 `archive/main-before-formal-release-20261106:prebuilt/j7-swd66666-20261106/README.md`） · [OCM 核对](raw/experimental-ocm.json)

目标 F103ZE CDC48，CPU/HCLK 48 MHz，ETMCR `0x411`。FCLK 133333332 Hz，SWCLK 66666666 Hz，按物理寄存器读回的 ARM PLL 来源和分频推算。`CFG=0xa11`，单 FCLK 半周期，标准占空比，Q2/legacy 边界。目标 PLL、总线分频和 Flash 内容与前一轮 60 MHz 保持相同。

复用历史 `h743_peak.py` 和 `0x20008000` 起 4 KiB SRAM 窗口，2 KiB 块、深度 32、每方向 256 块、三轮取中位数。追加 60.012 秒交替测量，共 302 轮，读回字节及写 ACK 校验、结束整窗读回均通过。

| 测量 | 读 MB/s | 写 MB/s |
|---|---:|---:|
| J7 66.666 MHz 三轮中位 | 5.333 | 5.239 |
| J7 66.666 MHz 持续窗口中位 | 5.343 | 5.240 |
| 历史同频同口径三轮中位 | 5.343 | 5.249 |
| J7 生产配对 60 MHz 三轮中位 | 4.820 | 4.732 |

较历史同频中位低约 0.19%/0.19%，较当前生产配对 60 MHz 提高 10.63%/10.72%。结论限定该板、目标和 SRAM 批量传输条件。 [本轮回包](raw/sram666.json) · [历史对照](../performance-limits-20261101/README.md) · [差异计算](raw/comparison.json)

收尾重新加载原生产配对并核对 85580 B PS 执行段。64 KiB SRAM 全量读回、核心寄存器、FPB、RCC、ETMCR 和目标 Flash 装载段一致。目标恢复运行，DHCSR `0x01010001`，探针采集、DMA、RTT、HSS 空闲。目标 Flash 和探针 QSPI 无写入。测速进程退出，`hw_server` PID 3904 保留。 [恢复证据](raw/restoration.json) · [逐文件哈希](raw/manifest.json)
