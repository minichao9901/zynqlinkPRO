# F103ZE 50 MHz SWD 差距和复测

J7 `12345678` 与 HS3 `210299008529` 恢复枚举。候选经 HS3 临时加载，并从物理 MEM-AP0 校验 OCM。F103 性能验收以 HCLK128 为准，HCLK96 只用于重放历史条件。时钟使用 RCC、DWT 和探针时钟寄存器取证，吞吐均为十进制 MB/s。[配对核对](original-load-result.json)

## 历史同条件对照

2026-10-31 基线的 F103 HCLK 为 96 MHz，标准 CMSIS-DAP 每块 512 字，深度 32，每方向 256 块，三轮取中位数。RTT 使用相同的 8 KiB 环和 2 KiB 搬运块，经 CDC 运行两个 3 秒窗口。当前固件以同样的参数重放。RTT 恢复过程调整为先停转发、再暂停目标，避免同时请求 AP 所有权，计时窗口位于切换之前。[历史原件](../combined-20261031/README.md) · [HCLK96 SRAM](historical-hclk96-cmsis.json) · [HCLK96 RTT](historical-hclk96-rtt.json) · [HCLK128 SRAM](historical-hclk128-cmsis.json) · [HCLK128 RTT](historical-hclk128-rtt.json)

| 条件 | CMSIS-DAP SRAM 读 / 写 | RTT→CDC |
|---|---:|---:|
| 历史 HCLK96 | 4.047 / 3.983 | 3.995 |
| 当前融合配对 HCLK96 | 3.649 / 3.695 | 3.645 / 3.646 |
| 当前融合配对 HCLK128 | 3.649 / 3.696 | 3.602 / 3.602 |
| 最终配对 HCLK96，slot 22 | 3.748 / 3.747 | 3.711 / 3.711 |

标准 CMSIS-DAP 与旧 RTT 服务使用每笔 AP 请求跨域一次的 SelectIO 实时通路。把 HCLK96 提高到 128 的对照基本重合。相同 50 MHz 线上，融合版原生 SRAM 硬件队列达到 4.021 / 4.103，原生 PC 达到 3.850 / 3.833。旧同步 SWD 引擎在融合板上要额外经过引脚电平跨域复用，在试验中读 IDCODE 失败，已恢复对应目标 SRAM 和时钟。直接换回旧时钟设置无法复用历史的引脚采样条件。[原生分层计数](original-hclk128-memory.json) · [旧引擎试验](legacy-direct-failure-cmsis.json)

## 重叠 CDMA 和完整 TAR 页

旧固件每页依次搬运载荷、运行 SWD、检查 DP 状态。新固件在当前页运行时把下一页写入另一块 PL TX bank，读时则在运行下一页的同时复制已通过 DP fence 的上一页。页头和页尾的短段仍按实际边界提交。两次测试均用 HCLK128、实际 SWCLK 49,999,999 Hz、tap 8、slot 24、idle 0、15 KiB 页对齐、USB 深度 4。各方向三轮，全部检查有效载荷和哨兵。[串行 CDMA](page-ab-original-memory.json) · [交叠 CDMA](page-ab-overlap-memory.json)

| PC 有效载荷 | 原固件 | 重叠 CDMA | 提升 |
|---|---:|---:|---:|
| 读 | 3.852 | 3.934 | 2.1% |
| 写 | 3.840 | 3.935 | 2.5% |

同一配对的 slot 22 短窗为 4.020 / 3.976 MB/s，slot 23 结果接近，slot 24–27 约 3.93–3.94，slot 28 进一步下降。更早的 slot 20 首轮读回失败。采样点带来的收益主要出现在队列计时，说明影响来自回采后等待的 serializer 时隙。读链路从 slot 24 的 4.020 升到 slot 22 的 4.104 MB/s，USB 头和事务规模相同。[相位扫描](slot-sweep.json)

slot 22 的长窗每方向 3 × 60 秒。50 MHz SRAM 的理想连续 DRW 为 4.348 MB/s，硬件队列实测读 / 写 4.105 / 4.145，PS 层 4.080 / 4.119，PC 中位 **4.016 / 3.972 MB/s**。写入生成新的图案，读取逐块核对，最后独立复核原 SRAM 和哨兵。相对历史 4.047 / 3.983，原生路径分别达到 99.2% 和 99.7%。[长窗分层记录](slot22-60s-memory.json) · [恢复记录](slot22-60s-state.json)

## RTT 到 PC

原生独立 RTT 在 HCLK128、tap 8、slot 24 下用实板 60 秒读 3.647 MB/s。把相位改为 slot 22 后，相同 2 KiB 块达到 3.717 MB/s。改用 SRAM 队列与 4 KiB 上限后，10 秒得 3.895 MB/s。最终在探针 DDR 收妥后，使用 SWD 写入的 RDBUFF 和 CTRL/STAT 检查确认 RdOff，不再对本路径重复读回同一指针。出现写入不确定或队列错误时停止；已提交的包保留核对结果。并发 RTT 与采样服务继续使用带读回的提交路径。[原始相位长窗](original-hclk128-rtt.json) · [新相位长窗](slot22-60s-rtt.json)

| 窗口 | PC 有效字节 | MB/s |
|---|---:|---:|
| 60 秒第 1 轮 | 234,909,696 | 3.915 |
| 60 秒第 2 轮 | 234,844,160 | 3.914 |
| 60 秒第 3 轮 | 235,077,632 | 3.918 |

中位数 **3.915 MB/s**，达到历史 RTT→CDC 的 98.0%，比优化前的原生 slot 24 提升 7.3%。三个窗口共收到 704,831,488 B。主机记录逐字检查，队列确认、主机尾部、目标生产计数与读指针一致。按整个 CLI 进程计时，中位数为 3.881 MB/s。以第 1 轮为例，线路队列的 AP 事务合计占 57.77 秒，PS 块函数合计占 58.68 秒，余约 1.32 秒包含服务调度、USB 与环提交后的数据处理。标准 CMSIS-DAP 在 50 MHz 的历史差距仍存在。[第一轮](queue-rtt-1.json) · [第二轮](queue-rtt-2.json) · [第三轮](queue-rtt-3.json) · [最终 OCM 核对](final-load.json)

## USB 容量与非对齐 SRAM

同一最终配对用探针私有 DDR 测量，深度 4、16 KiB 帧、16,320 B 有效载荷，PC 单向读 **29.024 MB/s**、写 **25.855 MB/s**。该路径使用与 SRAM 请求相同的帧头、大小和方向。USB 总吞吐有余量，目标侧等待、CDMA 设置以及单请求交接仍占时间。[探针 DDR A/B 数据](usb-ddr.json)

重放原 16,320 B 非对齐窗口时，第一次 10 秒写入为 3.585 MB/s，同窗内 PS 块速度仍为 4.103 MB/s。三秒复测为 3.953 MB/s，PS 块速率几乎相同。数据、哨兵和恢复均通过，首次差异落在 PS 计时边界外，确切来源待定位。[首次](final-unaligned-first-memory.json) · [不同块长复测](geometry-short-windows.json)

最终配对在历史标准 CMSIS-DAP 两方向为 3.748 / 3.747 MB/s，CDC 为 3.711 MB/s。这三个值均来自 HCLK96、实际 SWCLK 50 MHz 的旧口径重放。[标准 CMSIS-DAP](optimized-historical-96-cmsis.json) · [RTT→CDC](optimized-historical-96-rtt.json)
