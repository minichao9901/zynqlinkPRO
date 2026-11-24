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
