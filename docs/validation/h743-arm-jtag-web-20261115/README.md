# H743 ARM/JTAG 网页实板验收

2026-11-15（上海时间）。按用户确认，本轮范围包括两条链路的功能、性能和六轮跨页软件动作。需要在台架上拔插 J7 数据线的六个动作排除在本轮，统一入口保留其待验状态。 [上一轮实板证据](../h743-board-rerun-20261115/README.md)

## 现场及版本

- 唯一探针 J7 USB/HID `12345678`、COM33，下载线 `210299008529`。源工作台使用本机代理和独立 Edge，页面是真实浏览器业务通路。首测源码 `2bbbd33b`，干净 worktree。`d2e3481a` 为 STOP 测试夹具更新。
- 物理 MEM-AP0 确认正式 QSPI `0.8-nonce32` 启动标记及 85,716 字节 OCM 全等。bit SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，Zynq ELF SHA-256 `64d00fe597030175920b994e39ff51db8a683dbb8d5f907c0f8d73f8d55044b9`。初始 FCLK 99,999,999 Hz，SWD/JTAG 业务请求 50 MHz。时钟证据来源为探针寄存器读回。
- 原应用 RTT 示例装载段 1,192 字节与 `d0079519…` ELF 全等，CPU480/HCLK240、I-cache 开、D-cache 关、核心运行。读回 2 MiB SHA-256 `7b6a4f9e7b83de0b9cf81236fe38508b5bcd519b7dc85fd9b811befdb77e666b` 与上次两份独立备份一致，本轮又独立双读。使用同一 Bank1 sector0 128 KiB 临时切换两份 Golden。探针全程使用原正式 QSPI 运行配对。

## 变更范围

- ZL-236：原生 OpenOCD 独占探针前，H743 和 F103ZE 都显式完成 ARM SWJ→JTAG 选择。后续真正烧录走标准 `board.accept`。
- ZL-226：RTT 转发和 J-Scope 复用现有 J7 传输选择。浏览器把 HID 与 USB 按序列号绑定，CMSIS-DAP 先核对 ARM IDCODE 指令、IR4/5 及 CPU/边界 TAP，释放 DAP 后由 HID `0x31/action12` 选择 JTAG。转发由 Web 串口收取，波形由探针 HSS EP87 收取。验收另外读回 PL 路由与时钟，并逐项确认 STOP。
- ZL-241：调试验收从 Golden DWARF 和 Thumb BL 确认主循环调用点，再核对实际步入、下一源码行、调用栈、步出返回 PC 和 SP。
- ZL-242、ZL-243：ETM 上传要求新标签、镜像散列及异步按钮就绪；解码验收调用仓库同一条 `trace verify` 并保存尾部诊断。

首测原版统一入口已经实烧录 JTAG，原生约 4.225 s、网页 61.016 s、独立启动核对 5.430 s，SWD/JTAG 的严格源步进也通过。首测两个流页在边界 TAP 身份处失败。按索引读边界 TAP 会进入 ARM MEM-AP 的定时校准。`6df21416` 改用 64 位 DR 扫描，第二次整跑仍因 TMS 序列在进入 Shift-DR 前发生误选而失败。两次整跑均保留，试后分别恢复并独立读回用户应用。

`74b7e65e` 让 TAP 按 Test-Logic-Reset → Run-Test/Idle → Select-DR → Capture-DR → Shift-DR 前进，并在 H743 实物上对照原始应答 `14 00 77 04 a0 6b 41 00 45 06`。随后按请求 50 MHz 复读 CPU TAP，再释放 DAP。定向诊断直接在原应用现场，以临时 RAM 夹具验证两页：物理 AP0 各读到 `JTAG_ROUTE=0x0e03`、49,999,999.5 Hz，RTT 保存 2,603,008 字节连续序号且 STOP 的 4,237,312 字节搬运和主机实收一致，J-Scope 八路采到有效 DEF 和 10,785 组，原始 JSP 逐值通过、STOP 尾差 0。两页退出后路由 0、租约释放，原 Flash 双读一致。首个 RTT 定向脚本的内存导出达到原缓存上限，后续改用页面有界文件记录接口。

首测修订后的 ETM 连续两次在同一个工作台完成 1 秒窗口，分别有 223 和 222 个完整 CRC/序号目标 CDC 回显落在独立硬件窗内，解码均无包问题；同名上传没有触发忙状态。此前真实尾部截断记录用同一条 `trace verify --require-decoded` 离线重验通过，保留 1 字节终止包诊断，未计入新板测次数。

主机验证通过 Web 184 项、CLI 96 项，`web.check` 通过，并在隔离工作台读到两个页面的真实 ARM/JTAG 选项。Web 列表及 CLI 预览只是主机取证。

## 双 TAP 修订后的实测

统一入口使用完整提交 `74b7e65edf77a75a0824be06c0fc4692ac12cc4e`，最终往返配对及黄金目标哈希均在逐项报告中绑定。SWD 在两个 60 秒窗口检查原始包、有效变量值和 STOP，八路 416 ticks / 60.250 s / 3,475,988 组 / 57,692.3 组/s，零跳拍及零尾差。先前 416 ticks 的短窗跳拍 0.42% 和 476 ticks 稳定对照继续保留。

JTAG 网页转发两轮各记录 6,594,560 / 6,240,256 B，约 1.993 / 1.990 MB/s，数据连续。STOP 最终计数分别为 8,290,304 / 7,880,704 B，与浏览器整段实收相同，探针读写错误为 0。511 / 512 / 513 B 三个有限负载逐字节通过。两轮物理 AP0 都读到 ARM 路由和实际 49,999,999.5 Hz。使用 2,048 B 搬运，历史 1,024 B 口径的原生经匹配测试见上一轮报告，吞吐不直接相减。

JTAG 单路 89 ticks 的 60 秒长窗和 STOP 通过。八路 450 ticks 短窗的本机 HSS 接收队列在 4 MiB 上限溢出，接收线程原实现立即退出，探针最后的 EP87 帧失去消费者，导致 STOP 持续报忙。原始错误保留，剩余三轮 JTAG 跨页及该轮目标终态标为阻塞。CPU60 切换在工作台交接阶段拒绝，独立双读确认首扇区仍精确匹配 CPU480 夹具，其他扇区相同。

旧工作台仅本轮进程退出后，按序列号连接原 J7，独立 STOP 首轮返回 -7，EP87 实际读出 16,384 B（32 帧），再次 STOP=0。HID 状态和物理 MEM-AP0 核对采样与 DMA 空闲。将保留的 32 B 八路夹具 RAM 回写并独立比较，然后恢复原应用首扇区、完整双读并复位，原 Flash、时钟、缓存、调试配置和心跳全部核对通过。

`bb3a645e` 保留 16 MiB 固定接收队列上限并输出实测高水位。发生队列溢出时采样立即定为数据不完整，后台保留无缓存增长的 USB 排空，只有收到 STOP 成功及随后新的 USB 静默信号，才确认资源释放。受控注入复验了 512 B 尾包和新静默、历史溢出仍对采集读取报错、正常队列拒绝丢弃路径，以及溢出恢复失败时继续占用的保护。真实定向八路 529 ticks 窗在原应用上用临时 RAM 核对 47,249 组及 STOP 计数，高水位 49,664 B，尾差 0，整片 Flash 双读一致。队列过载的模拟与正常实板吞吐各自取证。

## 主机 HSS 修订后的阶段证据

实板阶段验收使用干净源码 `bb3a645ec7922d809edcbaf9d11a05544874f403` 及其离线 `--review`。主机 Web 186 项、CLI 97 项、共享检查与 Web 语法检查通过。

| 业务 | 本轮实板结果 |
|---|---|
| SRAM | SWD/JTAG 读写、跨 1 KiB 边界、非对齐宽度、保护带和恢复通过 |
| 烧录 | 原版统一入口 SWD/JTAG 均通过。JTAG 原生 4.216 s，Web 55.952 s，独立启动态确认 5.390 s，实际 TCK 49,999,999.5 Hz |
| 调试 | 双链路识别、暂停/运行、指令单步、硬断点、源码进入/步过/步出、调用栈、返回 PC/SP 与恢复通过 |
| RTT Viewer | SWD/JTAG 真实原始上行、下行回绕和保护区校验通过 |
| RTT 转发 | SWD 通过。JTAG 标准功能及两轮跨页在 STOP 最终核对时发现浏览器少收 1,536 B，见下节 |
| J-Scope | 四个标准网页 60 秒窗口均通过，含原始 JSP 字段、逐值、包序、CSV 和重放。JTAG 单路 89 ticks，60.244 s、16,245,696 组、约 269.66k 组/s，队列高水位 36,352 B。JTAG 八路 529 ticks，60.225 s、2,732,346 组、45,368.6 组/s，队列高水位 51,200 B。尾差均为 0。 |
| ETM | CPU/HCLK 60 MHz、TRACECLK 20 MHz、SWD 10 MHz，一次工作台两次完整 1 秒硬件窗。两轮 USB 下载约 0.066 s（35.36/35.33 MB/s），解码 4.387/4.066 s，网页采集至解码 7.993/7.601 s，保存记录重开可用首屏 93.6/98.6 ms。零包问题，记录 8,721/8,722 条未知执行。目标 CDC 窗内准确回显 222/223，保存匹配 ELF。 |

最终 JTAG 八路 450 ticks 首短窗再次出现队列溢出。探针报告 68,571 组、68,833 跳拍、35,109,376 B，相当于一组约一帧；网页只收到 35,455 组，保留缺失诊断。修订后的 STOP 和夹具恢复在首次溢出中成功，原工具在同一轮继续，529 ticks 的正常短窗与完整长窗均过。稳定档位符合指南的原始计数和跳拍判据，450 ticks 的失败完整保留。

### JTAG RTT 接收流中的 1,536 B 缺口

| 同源码失败用例 | 探针搬运 B | 浏览器实收 B | 差值 B |
|---|---:|---:|---:|
| 日常长窗 STOP | 8,103,936 | 8,102,400 | 1,536 |
| 第 2 轮活动断开 | 4,009,984 | 4,008,448 | 1,536 |
| 第 3 轮空闲断开 | 4,216,832 | 4,215,296 | 1,536 |

三个用例都报告 STOP 完成，读/写错误为 0，COM 保持开启后计数也未变化。随后 6 次独立带 USBPcap 的成功 STOP 对照共匹配 48,445,440 B。该对照的物理 AP0 读回无法观察 A9 私有缓存中的动态 PS 队列。

按原种子 680014 完整压力顺序再次重现首轮「JTAG RTT → 切页」。探针搬运 3,332,096 B，浏览器实收 3,330,560 B。探针 EP83 总线捕获完整，唯一有负载的取消 URB 是 34516→34517，`0xc0010000`，带序列 3,584–3,967 的连续 1,536 B。成功 URB 先收到 3,583，再从 3,968 续收。完整流含此负载则连续，成功 URB 字节数精确等于页面实收。该次实际缺口在第一笔有效数据后的 6.270 ms，距最后一笔成功有效 URB 还有 1.662 s。上表三笔未抓包个例保留为相同总差指纹。

最后一次 `SET_LINE_CODING` 完成时间为 1794681257.529570（Unix 秒），最后一次信号设置完成为 1794681257.575083，首笔数据 1794681258.188749，取消发生在 1794681258.195019。取消前后没有 CDC 控制请求或 COM 重开。旧版每个 64 KiB overlapped read 有 15 ms 总超时，可能在 USB 数据到达途中结束。USBPcap 给出取消与字节证据，Windows 取消的内部调用来源未直接采集。

修订只对 Windows 本机 J7 探针 RTT 读取移除总超时，收到数据后通过 5 ms 字节间隔回交部分读取。DTR/RTS 与缓冲在 reader 启动前配置，关闭期间有界取消并确认线程退出。网页 RTT 连接明确发出 RTS，而普通串口仍使用原配置路径。该探针接受 DTR 或 RTS 任一有效，旧抓包最后状态为 `0x0002`，早期候选因两个信号均低导致零传输并已保留。Linux 和非 RTT 串口保留原总超时。  [Microsoft COMMTIMEOUTS](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-commtimeouts)

同一正式探针配对和原应用、相同种子和过滤抓包下，干净源码 `7974dbf29460f8310ff5d449613b5c5f71af3363` 的三轮 JTAG 跨页软件动作 9/9 通过。五次实际会话共 18,483,200 B，逐会话的成功 URB 连续，取消均为 0 字节。单独准备过读取 CDC dTD 的离线诊断候选；获取主机抓包证据后停在离线阶段。

同一候选在原应用上另测两条链路的 511 / 512 / 513 B 有限负载。六笔网页导出和 STOP 计数逐字节正确，每笔对应一个成功 EP83 数据 URB，共 3,072 B，另外六个结束取消均为 0 字节。原应用 Flash 及心跳复核通过。

### 离线原始证据

所有路径都相对本机 `E:\zynqlinkPRO\build\h743-board-hostfix-20261115\`。USBPcap 只保留该 J7 设备的流量，不随 Git 提交。

| 记录 | 本机路径 |
|---|---|
| 主机旧版有载荷取消、原步骤和时序 | `stress-full-j7-only-r1.pcap`、`stress-full-r1-decoded/streams.json`、`stress-full-r1-decoded/timeline.tsv`、`stress-full-with-pcap-r1/` |
| 旧版无抓包、切页仅转发、普通 STOP 重复样本 | `stress-full-no-pcap/`、`stress-stop-forensics/`、`rtt-stop-forensics/` |
| 新读法但 RTS/DTR 均低的早期候选 | `stress-full-j7-only-cdc.pcap`、`stress-full-with-pcap-cdc/` |
| 修后相同种子的三轮原步骤及抓包 | `stress-full-j7-only-cdc-fixed.pcap`、`cdc-fixed-rtt-usb.json`、`stress-full-with-pcap-cdc-fixed/` |
| 修后两链路纯小包 | `finite-j7-only-cdc-fixed.pcap`、`finite-fixed-decoded/result.json`、`cdc-fixed-boundaries/` |
| HSS 溢出、现场排空/恢复和候选单测 | `gate-throughput/`、`emergency-stop/`、`hss-short-normal/`、`hss-gate-throughput/` |
| 未加载的 PS 诊断实验 | `cdc-ps-diagnostic/`（候选 ELF、manifest、源码补丁）、`cdc-ps-host-test-final.log`、`cdc-ps-load-plan.json` |

## 标准复跑入口

以下命令从匹配验收源码的干净检出执行。先用默认命令预览，并按[验收规则](../../板卡精简验收与交付.md#一键执行)匹配 J7 序列号和下载线。起浏览器并保留一个鉴权工作台标签页。常规阶段先独立确认 CPU480 Golden 和恢复资料，ETM 阶段另核对 CPU60 Golden。

```powershell
python -X utf8 toolbox.py project run board.accept -- --board h743
python -X utf8 toolbox.py --runtime build/h743-cdc-workbench serve --native-probe --bit prebuilt/qspi-release/probe.bit --zynq-elf prebuilt/qspi-release/application.elf
```

```powershell
python -X utf8 toolbox.py project run board.accept -- --board h743 --runtime build/h743-cdc-workbench --out build/h743-cdc-functional --only sram --only flash --only debug --only rtt-viewer --only rtt-forward --only jscope --only stress --seed 680014 --jtag-cable-serial 210299008529 --allow-flash --execute
python -X utf8 toolbox.py project run board.accept -- --board h743 --runtime build/h743-cdc-workbench --out build/h743-cdc-etm-1 --only etm --jtag-cable-serial 210299008529 --execute
python -X utf8 toolbox.py project run board.accept -- --board h743 --runtime build/h743-cdc-workbench --out build/h743-cdc-etm-2 --only etm --jtag-cable-serial 210299008529 --execute
python -X utf8 toolbox.py project run board.accept -- --review build/h743-cdc-functional build/h743-cdc-etm-1 build/h743-cdc-etm-2 --out build/h743-cdc-review
```

压力中需要现场独立供电和实体操作的项目仍在标准报告内。当另行开始物理拔插验收时，在相同速率和种子下用交互终端加 `--only stress --usb-data-cycle`，只拔 J7 数据连接，接回后确认 J7 序列号、COM 重枚举和每项业务可恢复。

## 最终实板结论

干净源码 `7974dbf29460f8310ff5d449613b5c5f71af3363`，本机源码工作台 v1.3.8（OpenOCD Wasm，源码模式），同一个隔离 Edge 工作台。三份标准输入报告均为同一提交及同一探针。H743 原版 `--review` **17 通过、0 失败、6 待验、0 阻塞**，全板门槛保持 `accepted=false`。跨板总表另列本轮未测的 F103ZE、HPM6800EVK 36 项待验。用户本轮范围内的全部适用项目通过，其中 SWD 和 JTAG 各三轮、共 **18/18** 软件动作通过。

标准待验 ID 是 `swd-stress-1`、`swd-stress-2`、`swd-stress-3`、`jtag-stress-1`、`jtag-stress-2`、`jtag-stress-3`。每条链路三轮的唯一待验子项依次是调试暂停中、J-Scope 采样中、RTT Viewer 收数中的实体 J7 数据拔插。对应软件初始业务已实际运行并在退出后恢复。每轮真实顺序、计数与重连时间见[机器可读证据](evidence.json)。

| 项目 | SWD 50 MHz | JTAG 50 MHz |
|---|---|---|
| SRAM 单次 2 KiB 暂停态原生读/写、网页读/写（MB/s，网页含命令往返） | 1.414/1.279、0.01614/0.01652 | 1.467/1.040、0.00631/0.00620 |
| 同一 128 KiB 扇区烧录，原生/网页/启动（s） | 1.378/6.832/3.889 | 4.291/56.999/5.182 |
| 调试连接/暂停/指令单步/变量刷新（s） | 1.970/0.107/0.140/0.124 | 3.205/0.148/0.309/0.119 |
| RTT Viewer 本机通用 OpenOCD Wasm，3 秒有效吞吐（B/s） | 76,389 | 659 |
| RTT 转发网页两轮/原生（MB/s） | 4.001/3.970、3.997 | 1.985/1.988、1.992 |
| RTT 网页两次 STOP 最终搬运/实收（B，分别相等） | 16,384,000 / 16,506,880 | 8,527,872 / 8,089,600 |
| J-Scope 单路 | 52 ticks / 60.244 s / 27,805,130 样本 / 461,538.5 样本/s（461.539 kS/s） / 2 跳 | 89 ticks / 60.126 s / 16,213,877 样本 / 269,662.9 样本/s（269.663 kS/s） / 1 跳 |
| J-Scope 八路 | 416 ticks / 60.242 s / 3,475,527 组 / 57,692.3 组/s（57.692 k组/s） / 0 跳 | 529 ticks / 60.138 s / 2,728,399 组 / 45,368.6 组/s（45.369 k组/s） / 1 跳 |

J-Scope 四个正式窗口的 USB 丢失、帧序缺口、读错及 STOP 尾差均为零，队列高水位分别为 61,952 / 64,000 / 39,424 / 50,688 B（表内按 SWD 单/八、JTAG 单/八）。JTAG 八路 450 ticks 再现超载并正确 STOP 恢复，实际候选 529 ticks 符合稳定判据。RTT 每轮 STOP 后目标环内仍留 8,188 B，实收与搬运比较不包含这些字节。

SRAM 的原生流水线对照使用同一 J7 和 CPU480/HCLK240、512 words、depth 32、64 blocks、三轮中位数。11-15 对照 SWD 读/写为 **4.042/3.983 MB/s**，JTAG 为 **3.968/2.006 MB/s**。同档历史最佳分别为 **4.0494/3.9894** 和 **3.9771/2.0076 MB/s**。网页单次命令没有同口径流水线基线。[纠线复验原生对照](../h743-board-rerun-20261115/README.md)

JTAG RTT Viewer 的 659 B/s 是 H743 本机通用 OpenOCD Wasm 路径的实测吞吐，功能检查通过，速度仍是该通路的性能短板（ZL-248）。此前同口径最快一轮 676.5 B/s，本轮 −2.58%，之前多次为 655.5–658.8 B/s。F103ZE 的网页块读快路径带芯片身份和内存范围守卫，适用 F103ZE。[F103ZE 块读对照](../f103-viewer-transferblock-20261114/README.md)

J-Scope 的硬件调度时基为 24 MHz，组速约为 24 MHz ÷ ticks。统一网页流程为 68 秒完整会话预留样本缓冲，SWD 的单/八路最短周期为 52/416 ticks。历史原生 SWD 50 MHz 的单路 1 MS/s 有三次 2 秒零跳，60 秒实测跳拍约 0.00295%；八路 238 ticks 的 60 秒实测 100.84 k组/s、零跳。JTAG 50 MHz 同档 89/529 ticks 的记录约为 269.66 kS/s 和 45.37 k组/s，原生与本轮网页稳定点相近。[历史综合基线](../h743-workbench-acceptance-20261109/README.md) · [纠线复验](../h743-board-rerun-20261115/README.md)

JTAG RTT 转发的 2,048 B 搬运和约 3 秒窗，与 11-09 原生 1,024 B、三轮 2 秒和另一个配对的吞吐口径有别。同探针、同目标、同路径的阶段复跑中，JTAG 网页 Flash 最佳 55.952 s，本轮 +1.87%。调试、SRAM 和单次页面往返的各轮时间保留在索引。

### ETM 实采、解码与网页

同一工作台连续两次上传并校验 CPU60 Golden `246640bf79c8b1e568441a286812326dfb0ae68a0df061a0c023262c07cf221b`。ETMv4 专用配置为 SWD 10 MHz、CPU/HCLK 60 MHz、TRACECLK 20 MHz。硬件两次均为完整 1.000 s、无帧丢失、无硬件解析错误。标准 `trace verify --require-decoded` 两次通过，解码零包问题，各保留 1 个 gap 和 8,758 / 8,759 条未知执行。独立目标 CDC 在锁定硬件窗内分别 224 / 223 个连续 CRC 回显。

| ETM | 下载 s / MB/s | 解码 s / 解码建库任务 s | 网页采到解码 s | 重开首屏 ms | 指令 |
|---|---:|---:|---:|---:|---:|
| 第一次 | 0.0662 / 35.336 | 4.188 / 4.344 | 8.054 | 99.0 | 18,368,011 |
| 第二次 | 0.0664 / 35.252 | 4.160 / 4.330 | 7.764 | 88.1 | 18,366,969 |

两份原报告均传给原版 `--review`。同一 `etm` ID 按规则选最新通过，合并只计一项；独立第二次实板记录与第一份均保留完整 `capture.bin`、`capture.frm1`、所用 ELF、解码和浏览器日志。与同探针的上个软件修订两次历史相比，USB 速率差小于 0.31%，相同定义的测量已记录两轮。

### 收尾和交付

- [x] H743 原应用复位后实际运行，`g_ms` 前进、时钟错误和故障寄存器均为零。全片 2 MiB 独立双读与入场备份 SHA-256 一致。配置读回包括 Flash 选项、PLL/RCC、CCR、VTOR、FPB、DEMCR、DBGMCU 和看门狗冻结配置。临时 SRAM 各用例独立比对，应用重启后易失状态由原应用重新初始化。
- [x] 正式 QSPI 的 BOOT_MODE 1、启动标记及 OCM 85,716 字节再确认。最终 FCLK 99,999,999 Hz，GPIO 方向 `0xf`、路由 `0`，RTT/HSS/ETM、DDR/DMA 空闲，工作台 USB/HID/COM 租约释放。
- [x] 独立归档标准输入 `cdc-gate-throughput/`、`cdc-gate-etm/`、`cdc-gate-etm-repeat/`，原版汇总 `cdc-gate-review/summary.json`，原始 ETM 及匹配 ELF `trace-records/`，恢复 `final-physical-check.json`、`final-ocm/`，私有 Flash/RAM 备份、先前失败及修后证据均保存在上述本机目录。
- [x] 问题表更新 ZL-011、ZL-070、ZL-094、ZL-226、ZL-236、ZL-240–ZL-244。主工作区既有 ZL-006 改动、F103ZE 证据、固定程序和用户数据保留；任务所属服务和浏览器退出，核对 Trace 归档后清理本轮运行目录和临时检出，共享 `hw_server` 保留。

| 交付位置 | 本轮结论 |
|---|---|
| 本地源码 | 按本轮范围本地提交，验收源码见本节及 Git 记录 |
| 远端 `main` | 本轮未推送；只读核对 `d340cc3ef6a8b213f1bf8d46e387d972dc5fe229` |
| 固定 EXE | 本轮不更新；现场为 v1.3.8、`3255b515`、2026-11-14 16:24:18 +08:00，EXE SHA-256 `03d32e5b288336d805b491476186ef0fbe18129b9c683a26c7810c7fd5a54ca6` |
| Pages | 本轮不发布；公开首页 HTTP 200，远端 `gh-pages` `97ac02bc` |
| Release 下载包 | 本轮不发布；公开 v1.3.8，GitHub ZIP digest `7ed9bcde00d2ae120d13cd1b9a945beb31234fb4f1ada8a7c9502188e8d7199e` |
| J7 QSPI 实体冷启动 | 本轮范围外；沿用原正式 0.8-nonce32 镜像，运行态启动身份与 OCM 双端复核通过 |
