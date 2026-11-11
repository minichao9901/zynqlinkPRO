# H743 20-pin 灰排线 TRACECLK 上限测试

2026-11-11（北京时间）。在用户接好的标准 20-pin 灰色排线上，本轮最高重复通过的档位为 **25 MHz，GPIO 速度 2 档，1 秒 × 3**。三轮均完成硬件窗口、DDR/USB 下载和 OpenCSD 解码，成帧、包及分支序列错误均为 0。每轮 formatter 数据约 6.97 MB，解码约 2.82 亿条指令。26.67 MHz 起已观察到 1 秒窗口的间歇错误。频率为档位读回推算值。[逐轮证据](evidence.json)

| TRACECLK | GPIO 速度 | 窗口 | 成帧错误及结果 |
| ---: | ---: | --- | --- |
| 20 / 25 / 28.57 MHz | 2 | 各 50 ms | 三档成帧、包及分支序列错误均为 0 |
| 25 MHz | 2 | 1 s × 3 | 0、0、0，三轮完整解码通过 |
| 26.67 MHz | 2 | 1 s × 3 | 4、0、665。无成帧错误的一轮出现 1 个末尾不完整 ETM 包 |
| 26.67 MHz | 3 | 1 s × 3 | 1、0、0 |
| 28.57 MHz | 2 | 1 s × 3 | 6、4724、3 |
| 30.77 MHz | 1 | 50 ms，1 s × 3 | 短窗成帧错误为 0，解码有 17 个包错误。长窗成帧错误为 12832、12898、0 |
| 33.33 MHz | 1 | 50 ms，1 s × 3 | 短窗成帧错误为 0，解码有 35 个包错误。长窗成帧错误为 4、14695、14631 |
| 36.36–57.14 MHz | 1 / 2 / 3 | 50 ms 各档 | 所测档位均出现成帧错误 |

成帧失败时，所记录的帧 FIFO 丢失、DDR 写入错误和 IDELAY ready 丢失均为 0。频率与 GPIO 速度的影响呈非单调变化。现有证据将问题限于写入 DDR 前的接收或成帧，具体电气波形及输入相位仍待定位。历史 CDC 验收通过的 20 MHz 与本次 25 MHz 相差 5 MHz，两次使用的 CPU 时钟和负载不同。[历史 H743 CDC 验收](../h743-comprehensive-20261101/README.md)

## 测试配置与恢复

本轮沿用在线的正式 J7 配对，前后以物理 MEM-AP0 核对 85,844 字节 PS 执行段。bit SHA-256 为 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF SHA-256 为 `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802`。FCLK 为 119,999,998 Hz，SWCLK 约 10 MHz，RAW4 采样参考 199,999,998 Hz，五路 ELD1 均为 0 tap。时钟由寄存器和采集参考读回核对。

在线程序从外部 SDRAM 执行。暂停应用后备份 512 字节 AXI SRAM 和 20 个核心寄存器，运行两个交替调用的临时 Thumb 分支负载。测试档位的 CPU/HCLK 均为 200 MHz，以 HSE 25 MHz、PLL1 VCO 800 MHz 和 PLL1 R 分频推算四位 DDR TRACECLK。变更 R 分频时，先让应用所在 SDRAM bank 1 进入自刷新，短暂切换至 HSI，等 PLL1 重新锁定并恢复系统时钟后退出自刷新。初次通过 AP0 配置 Trace Funnel 的回读失败，临时脚本改用 AP2 的系统 CoreSight 地址后通过。[STM32H743 参考手册 RM0433](https://www.st.com/resource/en/reference_manual/rm0433-stm32h742-stm32h743-753-and-stm32h750-value-line-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf)

每批结束后恢复原 SRAM、核心寄存器、RCC、MPU、调试控制及本轮管理的 CoreSight/GPIO 配置。三页 SDRAM 抽样哈希与测试前一致，完整 2 MiB 目标 Flash 的 SHA-256 前后一致。目标回到原 20 MHz 分频并继续运行，`DHCSR=0x00010000`，`DBGMCU_CR=0`。最终采集、DDR、CDMA、RTT 和 HSS 空闲，既有工作台及共享 `hw_server` 保持在线。相关问题为 ZL-063 与 ZL-199。[逐轮恢复及最终探针状态](evidence.json)

测试脚本、ELF、备份、原始采集及解码产物统一放在系统临时目录。结论归档后，428 个临时文件已移入回收站并核对原路径已清空，本任务进程均已退出。
