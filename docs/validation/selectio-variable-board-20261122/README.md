# F103ZE SelectIO 变频实板复验

使用 HS3 210299008529 临时加载 Zynq 探针，USB 识别为 12345678。目标 DEV/REV 0x10036414，CPUID 0x411FC231。目标通过 SRAM-only 夹具进入 HCLK128，每个窗口独立由 RCC 读回与 DWT 验证。阶段间检查原始 SRAM、核心寄存器、时钟和运行态恢复。探针固化与 Web 不在验收范围。

初始加载的融合版 OCM 核对 79,692 B。50 MHz SRAM 读/写 3.832/3.863 MB/s，逐字校验通过。RTT 首次在取到控制块前返回 -4，AP 诊断首次恢复失败为阶段 6（恢复 SELECT），DAP 请求进入隔离。J7 定向 USB 重枚举后从备份恢复目标。干净临时加载后改用 slot24 仍能复现这一接管失败。独立物理 MEM-AP0 检查采集、队列与 CDMA 空闲后才临时重载 probe。目标 Flash 和探针 QSPI 无写入动作。

验证 ELF 复用主机已经选好的同频 SelectIO 档位，直接接管并保存 AP 上下文。对比时采用相同的 bit 和 PS 初始化脚本。50 MHz、slot22、idle0 的第一个 8 秒窗为 3.808 MB/s，确认收到发布的全部 33,433,596 B，设备错误为零。随后更长窗口继续测试稳定性。

[首轮 RTT 失败](full-first-rtt-failure.json) · [AP 上下文诊断](ap-context-restore.txt) · [修正后首个窗口](full-50-rtt-first-fix.json)

## 实测结果

各档用相同几何。SRAM 为标准 CMSIS-DAP 512 字 TransferBlock，深度 32，每方向 256 个块，三轮取中位数，写入另读回验证。RTT→CDC 为 8 KiB 环、最多 2 KiB 一块、两轮取中位数，逐字检查自增序列、STOP 后验证收到目标已发布的全部字节。50 MHz 两轮各 60 秒，72.727 和 100 MHz SWD 各 12 秒，JTAG 各 8 秒。所有结果为 PC 有效载荷。实际线频来自物理 MEM-AP0 读取 PS PLL/分频与 PL 档位后换算。

| 档位 MHz | 镜像 | 实际 Hz | tap / slot / idle | SRAM 读 / 写 MB/s | RTT→CDC MB/s | 未恢复错误 |
|---|---|---:|---|---:|---:|---:|
| SWD 50 | 融合 | 49,999,999 | 8 / 24 / 0 | 3.759 / 3.823 | 3.733 | 0 |
| SWD 50 | SWD 裁剪 | 49,999,999 | 8 / 24 / 0 | 3.762 / 3.816 | 3.733 | 0 |
| SWD 72.727 | 融合 | 72,727,272 | 8 / 22 / 0 | 5.028 / 5.299 | 5.021 | 0 |
| SWD 72.727 | SWD 裁剪 | 72,727,272 | 8 / 22 / 0 | 5.038 / 5.305 | 5.018 | 0 |
| SWD 100 | 融合 | 99,999,998 | 8 / 25 / 2 | 6.498 / 6.702 | 6.506 | 0 |
| SWD 100 | SWD 裁剪 | 99,999,998 | 8 / 25 / 2 | 6.513 / 6.708 | 6.503 | 0 |
| JTAG 100 | 融合 | 99,999,998 | 16 / 28 / 33 | 4.100 / 4.035 | 4.038 | 0 |
| JTAG 100 | JTAG 裁剪 | 99,999,998 | 16 / 28 / 33 | 4.101 / 4.037 | 4.037 | 0 |

FCLK0 均约 133.333 MHz，FCLK2 均约 200 MHz。50 和 100 MHz 档的 FCLK1 / quad 为 50 / 100 MHz，72.727 MHz 档为 36.364 / 72.727 MHz。定时窗口遇到的普通 WAIT 重试保留在队列状态中。DWT 已确认目标 HCLK128，阶段间恢复目标原始 CDC48 配置。

50 MHz 在 slot22 的短 RTT 窗口为 3.808 MB/s，首轮 60 秒仅送出约 52.96 MB 后失败，队列摘要 0x4C02 显示非法 ACK 0b011。slot24 的融合及裁剪版各两轮 60 秒通过，均为约 3.73 MB/s。历史 HCLK96 的同几何记录为 SRAM 4.047 / 3.983 MB/s、RTT→CDC 3.995 MB/s。当前融合版稳定档读、写、RTT 分别低约 7.1%、4.0%、6.6%。

100 MHz 的 slot20、slot22 实测 IDCODE 阶段失败。slot24 可完成 SRAM 窗口，RTT 在 idle0 或 idle2 出现非法 ACK。tap8、slot25、idle2 的两套镜像均通过。表格使用各档同条件通过的结果。裁剪后同频吞吐基本一致，实板数据支持离线阶段保留融合镜像的取舍。

[原始计数索引](measurements/summary.json) · [50 MHz 历史报告](../swd50-standard-20261122/README.md)

## 现场与归档

F103ZE 原 SRAM、核心上下文和 AFIO 已恢复。最终 SWD 读回 CDC48 的 RCC 与运行态，DHCSR 为 0x01010000。探针仍以 RAM 运行复测的融合镜像，物理 OCM 核对 79,732 B，RTT、HSS、ETM、调试队列与 CDMA 空闲。所有镜像切换均用 JTAG/RAM。

[目标复核](final-target.json) · [探针空闲](final-idle.json) · [最终融合 OCM](final-ocm.json) · [经过实测的配对与使用档位](../../../prebuilt/selectio-variable-board-20261122/README.md)
