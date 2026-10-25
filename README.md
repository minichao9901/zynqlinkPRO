# zynqlinkPRO

Zynq-7020 高性能 DAP 的恢复与 USB 实验工作区。

- [50 MHz 批量 RTL/CDMA 优化：SRAM 读 3.052、写 3.367 MB/s](docs/RTL批量与DMA优化.md)
- [LA 微时序测量与优化对照](docs/LA微时序分析.md)
- [已验证 bit/ELF 与源码快照](releases/dma50_20261025/README.md)
- [旧工程关系与源码分析](docs/旧工程梳理与USB性能分析.md)
- [CDC 实测结果](docs/CDC实测报告.md)
- [MSC 与 cache 新一轮对照](docs/MSC与Cache对照分析.md)
- [XUsbPs 官方 MSC 改造 CDC 实测](docs/XUsbPs官方CDC移植报告.md)
- [纯 DAPLink 移植进度](docs/纯DAPLink移植进度.md)
- [复合 USB CDC/WinUSB 基准](docs/复合USB基准.md)
- [OpenOCD 环境（nightly + 异步 CMSIS-DAP）](docs/OpenOCD环境.md)
- [给 Codex 的交接总结](docs/Codex交接总结.md)
- [Kingst LA 使用说明](docs/LA使用说明.md)
- [构建、RAM 下载和测速说明](docs/CDC测试使用说明.md)

原始历史工程保持不变。实验输入副本位于 `reference/legacy_zynq/`，生成文件位于 `build/`，实际测量及校验记录位于 `results/`。

当前 CherryUSB cached 基线为 512 B 提交、IN 约 22.5 MB/s、OUT 约 19.2 MB/s。新增的 XUsbPs 官方 MSC 改造 CDC 已验证：USB MPS 仍为 512 B，软件 IN=16KiB、OUT=16KiB 时，IN 约 32.57 MB/s、OUT 约 39.98 MB/s；连续流结果不能直接代表 DAP 命令往返性能。MSC 对照读取约 39.6 MB/s。
