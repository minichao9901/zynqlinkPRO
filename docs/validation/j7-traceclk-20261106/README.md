# J7 转接板同口径 SOTA 复测与 TRACECLK 边界

2026-11-06（上海时间）。SOTA 指仓库内有原始证据的历史最好值，按目标、频率、工作负载、事务组织和计时范围区分。使用已验收 J7 配对。bit SHA-256 `792d4b6c8f38e47b1ba27d19a4ff5211e3a05be642edac7a526baa727df65abc`，PS ELF `1fbf6471e14669a809aa02a3e4a6fbb262370ea9b45511f2a460e6f52a5d4ee5`。测速前核对占用并重载，装载与收尾均核对物理 MEM-AP0 的 85580 B 执行段。 配对（历史归档 `archive/main-before-formal-release-20261106:prebuilt/j7-adapter-20261106/README.md`） · [历史对照清单](raw/reference-baselines.json)

## SWD 和 JTAG

沿用历史 `tools/h743_peak.py`，F103ZE CDC48/CPU48 MHz，SRAM `0x20008000`，2 KiB 块、队列深度 32、256 块，三轮。SWCLK/TCK 为寄存器推算的 59.999999 MHz，FCLK 119.999998 MHz。两条链路的三轮数据和追加 10 秒校验均通过，SRAM 恢复，JTAG 临时 SWJ 配置恢复。

| 指标 | 本轮中位 MB/s | 历史同频最好中位 MB/s | 差距 |
|---|---:|---:|---:|
| SWD 读 | 4.820 | 4.835 | −0.30% |
| SWD 写 | 4.732 | 4.749 | −0.36% |
| JTAG 读 | 2.419 | 2.421 | −0.11% |
| JTAG 写 | 2.391 | 2.398 | −0.28% |

上一轮 1 KiB、深度 4 的小队列测到 4.11/4.05 和 2.22/2.19 MB/s。同一 J7 配对切换到历史块大小和深度后，原差距基本消失。两项参数同时对齐，未分离各自贡献。剩余不到 0.4% 的差距无足够证据归因到转接板。历史 SWD 绝对最好为固定 FCLK133 实验的 66.667 MHz、5.343/5.249 MB/s。J7 生产配对的 60 MHz 频率上限使绝对吞吐低约 10%，按每 MHz 归一化两者相近。 [同频及 66.667 MHz 历史报告](../performance-limits-20261101/README.md) · [本轮 SWD](raw/sota-swd60.json) · [本轮 JTAG](raw/sota-jtag60.json)

## TRACECLK 和 ETM 吞吐

用户授权暂调目标时钟。各档使用同一 296 B SRAM 分支负载、固定 SWD10 MHz、探针 FCLK 约 120 MHz、RAW4 采样参考约 200 MHz。目标 Flash 应用在改频期间保持暂停。CPU/HCLK 为 HSE8 和 PLL 寄存器计算值，DWT 周期计数独立交叉核对。四位 DDR TRACECLK 取 HCLK/2。测试到 F103ZE 的 72 MHz HCLK 对应 36 MHz TRACECLK。 [ST RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-microcontrollers-stmicroelectronics.pdf)

| TRACECLK / HCLK | 100 ms 成帧及解码 | 延长窗口 |
|---|---|---|
| 24 / 48 MHz | 通过 | 1 s × 3，硬件与解码均通过 |
| 28 / 56 MHz | 通过 | |
| 32 / 64 MHz | 通过 | 1 s × 3，硬件与解码均通过。2 s 硬件完整，建库拒绝 |
| 36 / 72 MHz | 首轮 formatter 237 次错误 | 三档 GPIO 输出各 3 轮 100 ms，全部有错 |

最高完整通过的频率由旧基线 24 MHz 提升到 **32 MHz**。同一 SRAM 负载、三轮 1 秒的 formatter 写入中位从 **18.44 → 25.26 MB/s**，解码指令数从 **2054 → 2739 万**。32 MHz 的 2 秒窗口采到 **50.56 MB** formatter，parser、FIFO、writer 错误均为 0。32 MHz 的 100 MiB 环形写入约 6.10 秒，按相同输入程序累计约 150.2 MB，覆盖最早历史后整环下载，按后窗时间通过。环形试验验收采集、成帧和下载。 [扫档](raw/sweep.json) · [2 秒证据](raw/trace32-2s-acceptance.json) · [整环结果](raw/ring-only.json)

32 MHz 首轮单次 100 MiB 下载为 37.95 MB/s，低于上一轮 24 MHz 的 38.73 MB/s。之后用相同 SRAM 负载和相同环容量交替做三轮，USB 下载中位 **24 MHz 38.750 MB/s、32 MHz 38.689 MB/s**，差 0.16%。之前约 2% 的差距未稳定复现。旧档案中单窗最高 38.767 MB/s 的记录来自 HAL Web 负载，规模和工作流不同，只作为 USB 路径参考。 [等量交替](raw/usb-compare.json)

36 MHz 的重复试验在 GPIO 1/2/3 档分别有 248～583、78～575、15～245 次 parser 错误，伴随重新同步。FIFO、DDR writer 和 IDELAY ready loss 都为 0。GPIO3 失败样本的 USB 与物理 MEM-AP0 DDR 字节一致，故障发生在写入和下载之前的输入采样或成帧。使用相同 RTL 的理想输入模型在 36 MHz 也能通过。人为给单条数据线加 7 ns 延迟时，32 MHz 的 10 个参考相位均正确，36 MHz 有 2 个相位取错。RAW4 在 32/36 MHz 每半拍分别约有 3.125/2.778 个 200 MHz 样本，独立同步与 stable-two 滤波对数据相对时钟的偏差更敏感。模型延迟是故障注入值。实际板上的具体线、偏移及波形尚待测量。 [GPIO 对照](raw/diagnostic.json) · [物理读回](raw/trace36-gpio3-physical.json) · [相位仿真](raw/rtl-margin.json)

## 解码、建库与总耗时

历史 F103 19565799 条指令的固定输入用相同离线 API 重测三轮。原始 ETM、目标 ELF、源码快照三项 SHA-256 均与历史相等。历史最好中位 **6.809 s**，本轮 **6.814 s**，差约 0.07%。 [历史报告](../etm-complete-index-20261103/README.md) · [同输入复测](raw/offline-f103.json)

本轮同一 SRAM 负载的 1 秒窗口，24 → 32 MHz 的采集控制和下载合计中位 **1.959 → 2.164 s**，原生解码建库中位 **7.085 → 9.493 s**。解码时间增加约 34%，对应指令数增加约 33%。USB 吞吐近似相同，下载字节增加。两个阶段的耗时按各自边界报告。旧报告的普通 Web 首屏包含页面呈现，不纳入这组对照。

32 MHz、2 秒的已保存输入能生成约 **5483 万条指令**的候选库。其类型 12 的 `ETMQIDX2` 查询索引为 **134238923 B**，比原生读取器的 **128 MiB** 守卫多 **21195 B**。`line_start` 一张表约 75.86 MB，`fs_start` 和 `ps_start` 各约 18.76 MB。当前程序在完整写出候选后的自检拒绝发布，报 `Invalid native store block`。保留原输入和失败日志，并在离线重现时于清理前读取候选目录。此项是主机索引容量边界 ZL-157。 [拒绝块详情](raw/large-store-diagnosis.json) · [失败日志](raw/trace32-2s-failure.txt)

## 收尾现场

各次高频试验后复核 RCC、APB1ENR、Flash ACR、64 KiB SRAM、核心寄存器、VTOR、FPB 和 DWT。目标恢复 CDC48 时钟及运行，`DHCSR=0x01010001`。Flash 装载段逐字节核对，目标 Flash 与探针 QSPI 无写入。J7 配对保持板上运行，采集、DMA、RTT、HSS 空闲。测试和离线 API 进程已退出，`hw_server` PID 3904 保持。批量原始记录留在本机 `build/j7-traceclk-20261106/`，仓库仅保留一份 36 MHz 原始失败样本和一份 2 秒建库复现输入。 [目标复核](raw/target-final.json) · [探针空闲](raw/idle-final.json) · [证据清单](raw/manifest.json)
