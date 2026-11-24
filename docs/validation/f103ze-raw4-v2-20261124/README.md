# F103ZE RAW4 ABI 2 新用例实板复验

本批次从 `ccf3b6e9` 的 `fusion-full-acceptance-v2` 开始。F103ZE 有 18 条用例，其中 12 条有部分或全部单档脚本，6 条由清单标为阻塞。配对固定为 `selectio-usb-split-raw4-20261123`，bit `9b8a3d92…`、PS ELF `1379081a…`、初始化 Tcl `ec37b1f5…`。证据存于本机 `build/runs/fusion-campaign/f103ze-raw4-20261124` 和各用例目录。 [清单](../../../acceptance-cases.json) · [配对清单](../../../prebuilt/selectio-usb-split-raw4-20261123/manifest.json)

HS3 `210299008529` 初次未枚举，用户重新接入后，探针经 JTAG/RAM 下载。J7 USB `12345678`、`bcdDevice=0x0202`，物理 OCM 对拍和 USB／HS3 同一物理探针核对均通过。原始批次对应 128 项 CLI 离线测试通过。

## CDC48 Golden ETM

首轮在父进程读 USB 描述符后，采集子进程打开同一 J7 被拒绝。显式释放枚举 USB 句柄，并补回归后，用同一探针、目标 ELF 和正式验收入口重跑。三轮硬件窗均为 1.000 秒，TPIU 成帧、FIFO、IDELAY 状态及 DDR 写入错误为零，严格核验通过。EP9 下载为 37.19–38.23 MB/s。SWD 请求 10 MHz，寄存器折算实际 9.523809 MHz。目标 Flash 装载字节、RCC 和 FPB 恢复已核对。 [首败及三轮原始摘要](etm-golden.json)

两次按序列号打开目标 COM34 做 CDC 并发回显，均在 Windows 串口配置时报 WinError 31。该行的 CDC 并发与工作台首屏仍待补证据。采集和解码子项已有实板通过记录。

## 128 MHz SRAM 性能镜像的 SWD50 首档

使用 `firmware/target/f103ze/images/performance/fw.elf`，SHA-256 `71971d46…`。备份和双读整个 64 KiB SRAM，装载并独立比对 ELF，在 SRAM 初始化该夹具并核对 RCC 与 DWT。恢复原 RCC、SRAM、核心和 CDC48 运行态，两层恢复证据均保留。

- SRAM 8/16 位跨页预检通过。纯读和纯写分别完成 60 秒，约 3.819／3.795 MB/s。首个交替窗在 2,016 个完成请求后检测到载荷不一致，停止本档并回读验证内层 SRAM、保护字和外层现场恢复。
- RTT 第一次完成 60 秒并收取 215,920,640 B，状态字段把 49,999,999 Hz 以整数 MHz 截断上报为 49，旧判定据此提前结束。修正整数 MHz 截断比较后，同档三轮约 60 秒逐字和 STOP／发布／环余量对账均通过。每轮物理 MEM-AP0 均读到 49,999,999 Hz，主机有效中位 3.599 MB/s。该档已有实板证据，其余档位分别执行。

[首败、时钟和复测摘要](performance-swd50.json)

## 重编 ETM 镜像与恢复

按新清单使用 `firmware/target/f103ze/images/etm/fw.elf`（`0aa69e56…`）。备份并双读 512 KiB Flash，只临时改写所含 20 KiB 扇区。NRST 后新 ELF 的装载字节和运行心跳通过。RAW4 上三轮 1 秒硬件窗口及严格解码通过，EP9 下载 38.17–38.35 MB/s，采集后的目标、RCC 和 FPB 恢复已记录。

写回原烧录区并全量回读，512 KiB Flash 与原备份一致。原 CDC48 已重新启动。独立终态核对发现 OpenOCD 烧录路径更改了 FPB REMAP 和禁用的比较器内容。用此前同板两份一致的原备份恢复，回读一致并核对运行态和心跳。原应用重启后 COM34 仍有 WinError 31，CDC 并发和首屏证据待办。 [逐轮采集及恢复](etm-rebuild.json)

## 启动、RTT 终端与真实 ITM

- Flash A→B 共三轮，六次烧录均先备份必要扇区，编程后逐次独立核对整片 Flash、NRST、启动 ID、数据初始化和心跳。A/B ID 分别为 `0x44424741` / `0x44424742`。原 512 KiB Flash、CDC48、FPB 和 DEMCR 均已回读恢复。
- RAM 版以实际向量启动，停在 `main=0x20000314` 并核对 .data、.bss，再继续到 ID `0x44424752`、初始化标记和递增心跳。恢复原 64 KiB SRAM、核心、RCC、NVIC 使能和 SysTick 配置。SysTick 相位重新起计。
- `dbg-a` 的 help/version/echo 各 20 次回包成功，共 60 次。源码单步、调用栈、数据观察点等 GDB 证据仍需补做。
- 实际新 ITM 夹具的 NRZ 3/48 Mbaud、Manchester 1.5/24 Mbit/s 各三轮，每轮 500,000 个 32 位 ITM 字全部经 ABI 2 标准 EP2 逐项比对，四档 STOP 尾量及错误计数均为零。接收端回读为 3,000,029／48,007,500 baud 和 1,499,993／23,998,125 bit/s。原目标 Flash 与运行态均已恢复。外部仪器测频仍待补证据。

[启动、60 条回包和 12 个 SWO 窗](boot-swo.json)

## 原生 GDB 补测与动态 J-Scope 起始档

同一个 `dbg-a` 双接版本镜像上用 RAW4 与实名 OpenOCD/GDB 跑 20 轮。逐轮核对源码硬断点，以及 `engine_deep_chain` 步入 `deep_l1`、下一语句和步出返回的 PC 与行号。20 次 PendSV 停在异常 14 并可回栈。8/16/32 位 DWT 数据观察点各 20 次，写入值和触发点均确认。工作台关闭后目标 Flash、FPB、DEMCR 和 CDC48 心跳与基线一致。补测将空的 UP/DOWN 环分别从 8,190／254 起步。60 条实际终端命令及回包逐字节通过，上行 980 B、下行 520 B，两环读写指针均按环长对账。 [双向回绕及恢复](gdb-rtt-wrap.json)

128 MHz 新性能镜像、SWD 实际 49,999,999 Hz、1 k组/s 的单路及八路动态 J-Scope 各三轮。每轮 59,994 组，原始序号、组时戳、STOP、读错和跳拍判据通过，并核对 SRAM 及原运行态恢复。八路的异步跨更新边界在报告记录，不计为探针丢帧。

[GDB 源码位置、恢复和两组 J-Scope 逐轮证据](gdb-scope-swd50.json)

## SWD50 三轮并发与 SRAM 复跑

128 MHz 目标的八路动态采样＋RTT 在 250／1,000 组/s 各 3×60 秒。RTT 每窗约 199.64／184.23 MB，组计数分别约 14,999／59,995，全部零跳拍。RTT 序号、两类 STOP 与恢复均通过。停止其中一个消费者后另一端持续运行的证据另待补。

SWD50 原 tap8／slot24／idle0 同档复跑第一轮就报告预填载荷不一致，内外两层恢复均成功。保留首轮的交替失败和复跑的预填失败，根因仍待定位。

[双流逐轮和 SRAM 复跑](combo-and-sram-retry-swd50.json)

## SWD100 SRAM 长窗

新 128 MHz 性能镜像、RAW4 ABI 2、tap8／slot25／idle2，物理队列折算 SWD 99,999,998 Hz。跨 1 KiB 的 8/16 位访问、4,032 B 深度 4 的纯读、纯写和交替各 3×60 秒均通过，九窗中位为 6.674／6.621／6.577 MB/s。逐窗核对方向计数、最后一块及保护字，全部通过。双层 SRAM 和原运行态恢复。 [SWD100 原始摘要](sram-swd100.json)

## JTAG SRAM 多档

128 MHz 目标和 RAW4 同配对的 JTAG 50 MHz 与 72.727 MHz 各完成九窗，4,032 B 深度 4 的纯读／纯写／交替中位分别为 3.065／3.004／3.019 和 3.866／3.769／3.792 MB/s。验证跨页、载荷、保护字和两级恢复。100 MHz 首档 tap16／slot28／idle11 在第一笔原生传输报 status 1、detail 2，内外恢复均确认。首次失败保留，同频率的短窗校准和复跑另取证。 [逐档数据](sram-jtag-first.json)

## SWD100 RTT 与 JTAG100 同频校准

SWD100 RTT 三个 60 秒完整窗口逐轮以物理 MEM-AP0 核对活动时钟为 99,999,998 Hz，序号、目标发布、STOP 与环余量对账通过。主机有效中位 6.197 MB/s，目标 SRAM、时钟和运行态恢复。

JTAG100 在相同 tap16／slot28、idle33 时通过短校准，60 秒读窗约 4.710 MB/s，写窗仍报原生 status 1、detail 4，导致整档失败。保留 idle11 首败、idle33 复跑及两层恢复，根因仍待定位。 [RTT 与复跑](rtt-swd100-and-jtag100-retry.json)

## JTAG RTT 长窗和 SWD50 新校准点的装载异常

128 MHz 性能镜像在 JTAG50 和 JTAG100 的独立 RTT 各 3×60 秒，序号、发布、STOP、环余量对账通过。主机中位 2.584／4.705 MB/s。物理 AP0 在 50 MHz 后两轮、100 MHz 全三轮观察到相应精确档位。72.727 MHz 首轮原始文件为 0 B，退出时 DAP Disconnect 返回 `ff`，恢复确认。72.727 MHz 原生 SRAM 的通过证据单列。

SWD50 替代 tap8／slot22／idle0 通过短窗校准。随后的正式长窗夹具未发布新 SRAM 镜像 ready 标志，启动步骤中止，核对原状态已经恢复。这个尝试未进入正式长窗。
[逐档与恢复](rtt-jtag-and-swd50-startup.json)

## 同频复验补证

SWD50 在同一 RAW4 和 128 MHz 目标、tap8／slot22／idle0 下正式 3×60 秒纯读／写／交替全部通过，中位 3.895／3.823／3.837 MB/s。跨页、方向计数、SRAM 和保护字恢复均确认。保留 slot24 两次失败和 slot22 首次装载中止。

JTAG 72.727 MHz RTT 在 tap16／slot28 改 idle33 再次复现 0 B，退出 `ff`。目标恢复已核对。 [校准点长窗与 RTT 复验](sram-swd50-trained.json)

## SWD50 动态 J-Scope 网格

1／10／25／50／100 k组/s 共十个单／八路组合。单路五档、八路到 50 k组/s 共九个组合通过各三轮长窗。八路 100 k组/s 在首个 60 秒窗跳 2,999,685 组，超过门槛，记录为失败。十项的目标 SRAM 与运行态均已恢复。[SWD50 全网格](scope-swd50-grid.json)

## SWD100 动态 J-Scope 网格

128 MHz 新性能镜像、实际 SWD 99,999,998 Hz，单路和八路在 1／10／25／50／100 k组/s 的十个组合均通过三轮 60 秒。各点核对动态值、时戳、跳拍和 STOP，内外层恢复确认。[SWD100 全网格](scope-swd100-grid.json)

## JTAG50 动态 J-Scope 网格

同一 128 MHz 目标镜像、tap16／slot28／idle17，单路 1–100 k组/s 和八路到 50 k组/s 共九个组合各三轮通过。八路 100 k组/s 首窗跳 2,999,672 组，超限。十个组合均完成现场恢复。 [JTAG50 全网格](scope-jtag50-grid.json)
