# J7 转接板速度实测

2026-11-06（上海时间），F103ZE CDC48，CPU/HCLK 名义 48 MHz，TRACECLK 名义 24 MHz。使用 `8c3ade90` 的 J7 配对。测速前检查探针租约、采集、DMA、RTT 和 HSS，随后显式重新加载指定 bit/ELF。加载后与收尾均用物理 MEM-AP0 核对 PS 执行段 85580 字节一致。

| 工件 | SHA-256 |
|---|---|
| J7 bit | `792d4b6c8f38e47b1ba27d19a4ff5211e3a05be642edac7a526baa727df65abc` |
| J7 PS ELF | `1fbf6471e14669a809aa02a3e4a6fbb262370ea9b45511f2a460e6f52a5d4ee5` |
| 目标 CDC48 ELF | `e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f` |

## SWD 与 JTAG

用 1 KiB DAP 块、队列深度 4、固定 4 KiB SRAM 窗口。先用四块不同数据确认 TAR 回绕，再进行写入测量。扫档每方向每轮 128 KiB，三轮。读校验每个回复的全部字节，写校验全部 ACK 及每轮结束的整窗读回。60 MHz 加测每方向三轮，每轮 4 MiB。耗时包含 USB DAP 请求和回包校验，TAR 初设和写后读回单独执行。

| 链路 | 最高通过的实际时钟 | 60 MHz 持续读中位数 | 60 MHz 持续写中位数 |
|---|---:|---:|---:|
| SWD | 59.999999 MHz | 4.113 MB/s | 4.045 MB/s |
| JTAG | 59.999999 MHz | 2.220 MB/s | 2.190 MB/s |

两条链路的 11 个请求档位均通过。35、40、54、57 MHz 请求分别落在约 34.615、39.130、52.941、56.250 MHz。最高档 FCLK 119999998 Hz，频率由物理寄存器读回的 PLL 和分频计算。两条链路请求 60000001 Hz 均收到 `11 FF`，达到当前 PS 固件的 60 MHz 上限。更高频率和电气极限留在本轮范围之外。

JTAG 测试临时打开 F103 SWJ，回包 IDCODE `0x3BA00477`。20 至 25 MHz 的吞吐出现局部下降，原始 PHY 计数及中间档全部保留。两次测试均核对完整 64 KiB SRAM、核心寄存器、FPB、RCC、AFIO/APB2ENR 和原运行状态，未观察到 JTAG 连接复位。 [扫档](raw/sram-limits.json) · [持续测试](raw/sram-60mhz-sustained.json)

## ETM

目标时钟沿用 CDC48。工作负载为目标当前运行的 CDC 轮询主循环，未施加外部串口刺激。SWD 控制约 10 MHz，探针 FCLK 约 120 MHz，RAW4 参考时钟约 200 MHz。三轮普通采集均达到 CLI 允许的 2 秒窗口。 [分段数据](raw/etm-phases.json)

| 指标 | 2 秒普通采集，三轮 | 100 MiB 环形记录，一轮 |
|---|---:|---:|
| 实际硬件写入时长 | 2.000 s | 8.109 s |
| DDR formatter 写入吞吐 | 中位 15.409 MB/s | 15.418 MB/s |
| USB 下载吞吐 | 36.46～38.53 MB/s，中位 38.05 MB/s | 38.73 MB/s |
| 每轮下载数据量 | 约 30.82 MB | 104857593 B |
| 原生解码与建库 | 10.38～11.10 s | 本轮只采集和解复用 |
| CLI 端到端 | 14.75～15.73 s | 12.45 s，含 8 秒触发等待 |

普通窗口每轮解码约 3836 万条指令，包错误、parser 错误、FIFO 丢帧和 DDR writer 错误均为 0。保留各轮解码缺口与 formatter 尾帧状态。原生解码与建库是内置计时，CLI 总时长减去硬件窗、USB 和解码后的剩余约 1.57 s（中位）合计包括控制、进程启动及其他主机开销。浏览器首屏未测。

环形记录延时触发，后窗为硬件 100 ms。累计写入 125019433 B，实际覆盖最早 20161833 B，另因帧对齐移除 7 B。保留区按时序下载 104857593 B。parser、FIFO 和 writer 计数均无错误，环形起点的执行未知状态保留。TRACECLK 在本轮固定为 24 MHz。 [环形回包](raw/etm-ring-100mib.json)

## 最终现场

目标继续运行，DHCSR `0x01010001`。CDC48 的 20168 B Flash 装载段和 RCC 与任务开始时相符，ETM 暂存配置和 FPB 通过每轮恢复检查。目标 Flash 和探针 QSPI 无写入。板上保留本轮指定的 JTAG/RAM 配对，采集、DMA、RTT 和 HSS 空闲。本任务测试进程退出，`hw_server` PID 3904 保持运行。原始大记录留在 `build/j7-adapter-limits-20261106/`，本次提交保存紧凑证据和哈希清单。 [最终目标](raw/target-final.json) · [最终探针](raw/probe-idle-final.json) · [证据清单](raw/manifest.json)
