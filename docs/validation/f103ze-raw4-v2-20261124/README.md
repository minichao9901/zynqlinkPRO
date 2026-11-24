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

同一个 `dbg-a` 双接版本镜像上用 RAW4 与实名 OpenOCD/GDB 跑 20 轮。逐轮核对源码硬断点，以及 `engine_deep_chain` 步入 `deep_l1`、下一语句和步出返回的 PC 与行号。20 次 PendSV 停在异常 14 并可回栈。8/16/32 位 DWT 数据观察点各 20 次，写入值和触发点均确认。工作台关闭后目标 Flash、FPB、DEMCR 和 CDC48 心跳与基线一致。现有终端 60 条往返覆盖了 DOWN 环回绕，UP 环回绕仍需单独造窗。

128 MHz 新性能镜像、SWD 实际 49,999,999 Hz、1 k组/s 的单路及八路动态 J-Scope 各三轮。每轮 59,994 组，原始序号、组时戳、STOP、读错和跳拍判据通过，并核对 SRAM 及原运行态恢复。八路的异步跨更新边界在报告记录，不计为探针丢帧。

[GDB 源码位置、恢复和两组 J-Scope 逐轮证据](gdb-scope-swd50.json)
