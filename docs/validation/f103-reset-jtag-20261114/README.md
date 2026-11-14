# F103ZE 正常烧录、60 MHz JTAG 与吞吐回归

2026-11-14，基于 `425d0d72` 加本次工作区修订。本机源码工作台 v1.3.8、隔离 Edge、本机 USB 服务。只使用 zynqlinkPRO J7 `12345678`，下载线 `210299008529`，串口按 USB 序列号匹配为 COM33。未加载或改写探针 bit、PS ELF 或 QSPI。物理 MEM-AP0 核对正式 `prebuilt/qspi-release/` 配对的 PL 特征，运行 OCM 执行段 85,716 字节与 ELF 一致。bit SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF SHA-256 `64d00fe597030175920b994e39ff51db8a683dbb8d5f907c0f8d73f8d55044b9`。

目标是 CDC48 `prebuilt/golden/f103ze-cdc48.elf`，两段映像共 20,168 字节；F103ZE CPUID `0x411fc231`、DBGMCU ID `0x10036414`，应用 CPU 48 MHz。实际 SWCLK/TCK **59,999,999 Hz**，FCLK 119,999,998 Hz，来自物理寄存器和分频计算。烧录范围 `0x08000000` 起 20,480 字节，前后读回 SHA-256 `1d90ea67ed4dc7175a916430915e836f560817ae9b957d0d53b402e58d69f000`。

## 故障复现及复测

| 实板轮次 | 结果 |
|---|---|
| JTAG 初始化对照 | 先走 SWD 再直接进入 OpenOCD，1 MHz 和 60 MHz 都能复现扫描链全 1。先发送 ARM SWD→JTAG 选择序列，两档都能识别 CPU TAP `0x3ba00477` 与边界扫描 TAP `0x06414041`，包括直接以 60 MHz 扫描的用例。CDC48 启动时关闭 JTAG 引脚，验收临时开放 AFIO，结束恢复 AFIO/APB2。Web 在同一个 USB 租约内完成 SWJ 选择。原生验收在启动 OpenOCD 前选择 SWJ。 |
| 复位对照 | 1 MHz 下独立写 AIRCR.SYSRESETREQ，运行态心跳继续增长，DHCSR 未见新复位标志。暂停并开启 reset vector catch 后，PC 仍留在 `0x080005a0`，随后恢复 DEMCR 与运行状态。改用 J7 NRST，引脚响应 `0x2c → 0xac`，DHCSR 出现新 `S_RESET_ST`，心跳重新起计。SYSRESETREQ 未触发的底层原因待定位。 |
| 首次定向回归 `round3` | SWD/JTAG 的 SRAM、烧录及调试通过，SWD Viewer 通过，JTAG Viewer 已识别探针和 RTT 控制块，首轮大块读在等待窗口内未回。7 项通过、1 项失败，收尾通过。 |
| 正式 Web 初始化 `round7` | SWD、JTAG 烧录、SRAM 和调试均通过，SWD Viewer 通过，JTAG Viewer 仍卡在大块读。SWD 三轮各 3 个软件压力动作全通过。JTAG 调试的软件断开/重连 2/2 通过，Viewer 失败保留，受控 USB 数据断开和 ZL-226 能力缺口待验。 |
| Viewer 分块 `round8` | 512 字节一批后能持续进数，旧 8 秒跨环判据恰好收到 8192 字节，未跨环。JTAG 三轮软件动作通过数为 1、2、1，合计 4/4。其余动作是物理拔插、ARM/JTAG 网页转发和 J-Scope，仍待验。 |
| JTAG 最后定向回归 `round9` | JTAG 烧录、调试、Viewer 全部通过。烧录原生 1.57 秒、Web 10.86 秒，另 0.88 秒验证启动；新 DHCSR `0x03010001`，应用心跳 47,972 → 96,681 → 145,652。调试连接 2.17 秒，暂停 0.132 秒，指令单步 0.247 秒，变量刷新 0.155 秒，硬件断点、源码步进和现场恢复通过。Viewer 3.132 秒测窗实收 **0.654 kB/s**，完整导出 9,216 字节、2,304 个连续 u32，8 字节下行跨环、WrOff=4 与保护字节经独立回读通过。 |
| SWD 复查 `round10-swd` | 外部 nightly OpenOCD 一次烧录算法超时。原扇区被改动，写入进程退出后以备份回滚并独立双读确认恢复，目标运行，后续 Viewer 49.66 kB/s 且收尾通过。保留该失败。 |
| 仓库随附 OpenOCD `round11` | 同字节的便携副本经 SHA-256 核对后，两路的原生和 Web 烧录、读回及 NRST 确认通过。SWD 原生 / Web / 启动为 1.69 / 4.10 / 0.93 秒，JTAG 为 1.48 / 10.50 / 0.91 秒。SWD Viewer 128.36 kB/s，JTAG Viewer 0.659 kB/s，两路上行、跨环下行与收尾通过。 |
| JTAG Viewer 命令计数 `viewer-count` | 功能及收尾通过，开启浏览器请求计数后测得 0.506 kB/s。完整用例统计到 2,914 条 `DAP_JTAG_Sequence`（`0x14`），没有 `DAP_TransferBlock`（`0x06`）。 |

F103ZE 正常烧录统一用例先验证原生与网页烧录和 Flash 读回，退出写入会话并恢复工作区，再显式使用 J7 NRST 查启动。检查清除旧 sticky 标志、拉低/释放、出现新复位标志及两个正向心跳间隔。初读可能仍是复位前 SRAM，等启动清零后再确认增长。本轮修复覆盖验收入口，网页原有“烧录后复位”复选框仍使用其 OpenOCD 软件复位，本轮未将它计入通过。调试页的软件复位单独于本次调试回归。

## 同负载历史最佳对照

同一目标 48 MHz、链路 60 MHz 档。SRAM 用 512 words × 256 blocks、队列深度 32、三重复中位数和另 10 秒交替校验。RTT 转发用相同 RAM producer、1024 B 块、三次约 2 秒取探针 payload 中位数。历史同档 Golden/release 最佳取自[历史原始性能报告](../performance-limits-20261101/README.md#5060-mhz-对照)，配对为各自当时的发行件。

| 实际链路 | SRAM 读 / 写，本次与历史最佳 | 原生 RTT 转发，本次与历史最佳 |
|---|---:|---:|
| SWD | 4.822 / 4.734 对 4.835 / 4.749 MB/s | 4.638 对 4.646 MB/s |
| JTAG | 2.417 / 2.396 对 2.421 / 2.398 MB/s | 2.318 对 2.320 MB/s |

SRAM 偏差最大 0.32%，原生转发最大 0.2%。四组 SRAM 读写数据及持续校验通过；六窗转发顺序连续、最终发布量等于主机实收、零错误，恢复 RAM 和寄存器后目标运行。历史 66.667 MHz SWD 实验配对的更高数值属于另一个时钟档和探针配对。

网页 SRAM 的 2 KiB API 调用约 SWD 0.016/0.017 MB/s、JTAG 0.0066/0.0063 MB/s，与[上一轮网页同口径](../f103-board-accept-c7d79d1a-20261114/README.md#统一验收结果)相近。这个指标反映单次页面 RPC 墙钟时间。Web 烧录 SWD 约 3.87–4.50 秒，JTAG 约 10.50–11.59 秒，含擦写和校验，另记启动。历史 JTAG 正常烧录建链失败，无同口径可用耗时。

JTAG Viewer **0.65–0.66 kB/s** 对本轮同页 SWD 约 49.66–146.19 kB/s，存在明显性能异常。上一轮 SWD 同负载为 39.30 kB/s。JTAG Viewer 前次未连接，缺少可用历史同页上限。同一 J7 同时钟、相同主机的原生 SRAM 和 RTT 转发快，缩小了瓶颈范围。Wasm ARM/JTAG 用 `read_memory` 将 MEM-AP 流量展开为扫描命令，浏览器请求计数确认密集的 `0x14` 经 Worker 与本机 USB 服务逐次往返。建议为已确认的 J7 和 ARM MEM-AP/JTAG 增加原生使用的 `DAP_TransferBlock`，限定地址、核对 TAP 和 RTT 头，校验 1 KiB TAR 边界及下行保护字节。保留通用 Wasm 路径和 USB 租约，实测 WebUSB 直连与本机代理各三窗，再确定上线阈值。

## 证据与范围

原始证据在 `build/f103-reset-jtag-20261114/` 的 `cold-*`、`warm-*`、`reset-*.json`、`peak/*/result.json` 和逐轮 `summary.json`、`flash-boot.json`、`fixture/restored.json`。保留失败、私有 Flash/RAM 备份和原始顺序记录在本机。CLI 离线回归 96 项、Web 离线回归 178 项，共享驱动一致性检查通过。收尾复核目标继续运行，RCC、AFIO/APB2、夹具 RAM/寄存器及 FPB 恢复，探针 RTT/HSS/采集引擎空闲。本轮未要求拔插，受控物理断线仍按 ZL-237 待验。J-Scope 上限和 ETM 沿用上次验收记录，未复测。定向结果不构成 F103ZE 全量验收。
