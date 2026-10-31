# 7020 / 120MHz 优化配对

ARM SWD/JTAG 的 SRAM、RTT、HSS、USB 背压/重配置与 OpenOCD 回归已在 ZynqDAP +
STM32F103ZE/HCLK48MHz 上验收。完整数据与失败修复过程见
[实板验收记录](../../docs/validation/orbtrace-hardware-20261031/README.md)。真实 ETM 采集未在此优化 bit 上验收。

| 配对 | 固件链路上限 | 实测最高 FCLK / 链路 |
|---|---:|---:|
| `zynqlink_probe.bit` + `zynqlink_probe.elf` | 50MHz | 99,999,999 / 49,999,999.5Hz |
| 同一 bit + `zynqlink_probe_60.elf` | 60MHz | 119,999,998 / 59,999,999Hz |

两者使用本目录 `ps7_init.tcl`。bit 约束120MHz，WNS +0.499ns、WHS +0.020ns，
LUT14,767、FF16,990、Slice6,304、BRAM36等效10.5。RTL/bit源码 `bc9ced6`；
固件源码 `cbedca2`，包含 SWJ 未对齐复制和 HSS STOP 最终计数修复。

PS可执行段71,300B；含必要静态数据/MMU/堆栈的OCM跨度120,976B，运行缓冲在DDR。
保留DAP16×4096、USB512KiB arena以及原CDC/HSS/HID队列，没有缩队列。

最终50/60MHz配对共178个严格HSS窗口，状态帧序号/样本总数错误0。
50MHz配对的功能脚本遗漏独立服务传输偏好已修正，预置JTAG偏好后连续3次SWD冷启动测试通过。
初版被拒绝和中间版本的ELF身份、失败日志保留在manifest与Git历史，不能混用它们的旧SHA。

当前板上已经恢复另一工作线的原 filtered TPIU bit/ELF；切换工作目录不会加载本配对。
复测时显式调用 `tools/download_dap_fpga.tcl ELF BIT PS_INIT` 并保存加载日志、核对文件SHA和实际时钟。
另一worktree后续ETM滤波/64K FIFO改动未合入本分支，合并后须重新实现和验证。

所有实际加载文件、源文件指纹、构建选项、时序和验收范围见 `manifest.json`；
全目录字节哈希见 `SHA256SUMS`。
