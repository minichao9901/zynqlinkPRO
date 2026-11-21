# 双频 SelectIO 效率实验

工作基线为 cf544741。当前 F103 CDC 仍枚举，HS3 和探针 USB 的设备实例 Present=false；物理加载预检未找到目标。现有融合配对保留原样。以下新频点属于数字模型。100 MHz 实板对照来自[原始验收](../selectio-fusion-20261121/README.md)，相同 idle 的原生/主机分层数据见[分层复测](../selectio-fusion-20261121/compare100/README.md)。

## RAM、RTT 与 HSS 的计时边界

100 MHz、SWD idle 2 的长流 DRW 净载荷上限是 8.333 MB/s。JTAG 同时计入两个 TAP 的扫描序列，每字 43+idle 个时钟；批量 idle 29 的上限 5.556 MB/s，运行态服务 idle 33 的上限 5.263 MB/s。50 MHz SWD idle 0 的理想值 4.348 MB/s。以 256 个数据字加 TAR、RDBUFF、CTRL/STAT 及末条两拍空闲计，50 MHz 单页理想上限为 4.297 MB/s。每个服务按自己的有效载荷和确认条件计时。[Arm ADIv5 B4.2](https://documentation-service.arm.com/static/622222b2e6f58973271ebc21)

| 服务 | 100 MHz 理想上界 | 已交付 F103 HCLK48 | 主要差距 |
|---|---:|---:|---|
| SWD SRAM 读 / 写 | 8.333 / 8.333 MB/s | 6.16–6.18 / 6.16–6.17 MB/s | 队列已达 7.274 / 7.547；读尾采样、页事务、CDMA 与 USB 帧处理分别占时 |
| JTAG SRAM 读 / 写 | 5.556 / 5.556 MB/s | 4.68 / 4.55–4.57 MB/s | 队列约 5.31；等待目标 AP 的 idle 29 已计入上界，余差含页首尾和主机搬运 |
| SWD RTT UP | 8.333 MB/s 裸 DRW 上界 | 5.413 MB/s | 轮询真实环描述符，页界/环尾分段，RdOff 写入及其确认，活跃目标争用和主机排空 |
| JTAG RTT UP | 5.263 MB/s 裸 DRW 上界 | 3.485 MB/s | 同上，另有 IR 切换和 DP sticky 状态检查 |
| SWD HSS，1 / 8 个连续 u32 | 2.083 M / 208.3 k组/s | 1.000 M / 125.0 k组/s 档 | 1 字稳态固定 TAR，一组一次 DRW；8 字需要 TAR、8 次 DRW、RDBUFF。旧固件/RTL 周期下限 24 tick，另外有 CDC、提交与采样截止时间 |
| JTAG HSS，1 / 8 个连续 u32 | 1.316 M / 131.6 k组/s 乐观上界 | 250.0 k / 57.7 k组/s 档 | 还要支付 DP fence、IR 路由和段交接，跳拍会使部分采样包提前结束 |

RTT 的理想数是只读数据时的上界。对完整 1 KiB 页内的 255 个有效字，单段 SWD 在描述符 4 字与数据两轮 TAR/prime/RDBUFF 以及提交 SELECT/CSW/TAR/RdOff/RDBUFF 均执行时，大致需 255+13 笔事务；实际环在边界、空闲或短块时需要更多控制时间。HSS 的 8 字上界按 10 次等成本访问估算；JTAG 的 RDBUFF 还需检查 sticky，故不能直接达到该数。

50 MHz 已在实际 SelectIO 原语与 Cortex-M3 模型检查了引脚周期、两方向 256 个实际 SRAM 字、DMA 输入选择与回读。一字分两个 quartet 发射时，允许在描述符开始拍直接发出低半周期。相同时隙 16、idle 0，队列读从 4.109 到 4.196 MB/s，写从 4.147 到 4.192 MB/s。模型比例约为单页上界的 97.6%。[修改前](swd50-before.log.txt) · [修改后](swd50-after.log.txt)

[服务台架计数](cm3-meter.json)记录 50/100 MHz、两种协议、1/8 字。该表有意以 8 tick 超额请求以观察跳拍、实收率与物理边沿成本；它不等于无跳拍的可交付档。RTT 是打开真实 CM3 中未对齐描述符至首个 2 KiB 包就绪的时间，包括读目标、封装，不包括 USB，也没有把后续 RdOff 确认算进这段时间。50 MHz SWD 该边界约 3.856 MB/s，4 MB/s 的 PC 持续速率仍须实板验证。

## RTT 与变量采样窗口

### 多包 RTT 计时

固定 HCLK48 的 Cortex-M3 模型，环长 8,191 B，首地址与页边界错开。连续 4 包共 8,048 B，跨环尾及多个 TAR 页。从打开服务开始，计入 AXI 消费者读取整包、逐字节核对、四次目标 RdOff 写回和最终确认。时钟活动时间按实际引脚上升沿数除以该档时钟计算，尾差包含事务交接、CDC 和包调度。数字台架的消费者每次四包测试总耗时 30.315 µs。[原始计时和应答数](rtt-window.json)

| 模型档位 | idle | 有效 MB/s | 物理时钟边沿 | WAIT 应答 | 总时间 µs | 扣除消费者与时钟活动后的时间 µs |
|---|---:|---:|---:|---:|---:|---:|
| SWD 50 MHz | 0 | 3.770 | 96,642 | 28 | 2,134.76 | 171.60 |
| SWD 100 MHz | 0 | 6.626 | 96,954 | 52 | 1,214.57 | 214.71 |
| JTAG 50 MHz | 17 | 2.602 | 129,180 | 0 | 3,092.84 | 478.92 |
| JTAG 100 MHz | 33 | 3.993 | 163,436 | 0 | 2,015.70 | 351.02 |

50 MHz SWD 的 8,048 B 理想纯 DRW 需要 92,552 个时钟；实际多出 4,090 个，包括环描述符、换页、确认和 WAIT。以实际时钟数量计算，持续打钟阶段相当于 4.164 MB/s。消费与停钟合计约 202 µs，解释了到 3.770 MB/s 的差距。复现命令为 `python tools/selectio_cm3.py --services --rtt-window --swd-only --half-rate --idle 0 --out build/rtt50-model`。

实板运行态验收入口另支持 1 KiB / 8 KiB 生产者对照。以 Unicorn 2.1.4 执行同一份 56 B Cortex-M3 程序，用非整字的消费步长使环反复写满、停写、续写和跨环尾；1 KiB 环逐字节核对了 67,236 B，8 KiB 环核对了 78,494 B，两侧哨兵一致。这项测试验证目标夹具语义，真实连续 RTT 吞吐仍由在线目标给出。[执行结果](producer-rings.json)

### J-Scope 的稳定与超额请求窗口

ARM 双 TAP 的 IR 导航、指令、BYPASS 与返回 RTI 现合并为一次跨时钟域启动。在同一页的连续多字 JTAG 计划中，最后一次 APACC 在收回上组末字的同时，写入下组 TAR。每包仍由 CTRL/STAT 确认后才发布。单独注入 fence 错误时，未确认的整包和计数均被撤销。100 MHz、8 字、超额请求下由 74,037 提升到 103,355 组/s，物理时钟由 1,018.6 减为 775.7 TCK/组；50 MHz 同负载从 49,155 提升到 67,346 组/s。短窗计数另列暖机与稳定期。[逐档计数](sample-windows.json)

| 线速 / 协议 | 稳定窗 1 × u32，组/s | 稳定窗 8 × u32，组/s | 采样周期 tick，1 / 8 字 | 第 4 个样本至末样本的跳拍 |
|---|---:|---:|---:|---:|
| 50 MHz SWD | 599,996 | 79,999 | 40 / 300 | 0 / 0 |
| 100 MHz SWD | 1,000,040 | 125,001 | 24 / 192 | 0 / 0 |
| 50 MHz JTAG | 187,501 | 41,667 | 128 / 576 | 0 / 0 |
| 100 MHz JTAG | 299,891 | 62,500 | 80 / 384 | 0 / 0 |

每个稳定窗逐一检查所有变量值。单变量启动阶段有 1 或 2 个跳拍，八变量启动阶段为零。这些档位是有成功证据的有限窗口。约 130–250 组的模型窗口与 60 秒真实目标运行测量分别保存。

## USB 帧成本与千兆以太网

对照厂商的口径，SEGGER 公布的 J-Link Pro / Ultra 写入 RAM 上限为 4.0 MB/s，最高调试接口时钟为 50 MHz。这个数可以作为 50 MHz 下载的参考；它没有给出相同 F103、读方向或 RTT 环形缓冲的成绩。上述 100 MHz 吞吐使用了两倍接口时钟。[SEGGER 产品规格](https://www.segger.com/products/debug-probes/j-link/)

复算已交付的 PC、PS 与队列中位数：

```powershell
python -X utf8 tools/selectio_efficiency.py docs/validation/selectio-fusion-20261121/compare100/swd-2.json --legacy-hz 99999999 --legacy-idle 2
python -X utf8 tools/selectio_efficiency.py docs/validation/selectio-fusion-20261121/compare100/jtag-29.json --legacy-hz 99999999 --legacy-idle 29
```

新版分层测速在预填充核对后取计数起点，窗口净字节数必须与 PC 实际校验的载荷一致。报告同时保存 PL 队列 timing、tap、PS 实际参考钟、请求相位、idle 和 JTAG 退避次数。将新结果传给 `selectio_efficiency.py` 即可直接复算。若发生退避，输出的协议上界按初始 idle 计算。旧报告中的 PS 与队列计数包括一笔预填充写和一笔预检读，计算各层时分别使用其自身的字节数。返回包提交至 USB 驱动时，所链接 BSP 的 `XUsbPs_EpQueueRequest` 已执行净载荷缓存清理，候选删除了前台重复的整帧清理。[原生 CLI 用法](../../selectio/README.md)

上版同一设备的 ETM DDR→PC 读回实测 37.50 MB/s，飞行记录 38.23 MB/s；IF4 4 KiB 停等 echo 双向合计 21.48–21.64 MB/s。前者是单向大窗口，后者每个字节收发两次。50 MHz SWD 约 4 MB/s 不会耗尽这条物理 USB 链路，但小请求的软件成本显著。现有 100 MHz 的 4,032 B 请求在 PS 块计时以外有约 68/86 µs 读/写差额，其中还包括固件帧处理与主机载荷准备。[ETM 原始时长](../selectio-fusion-20261121/etm-running.json)

候选保持旧主机默认 4 KiB，新增显式协商 16 KiB 帧、滑动补充请求和两块交替的稳定 OUT 输入缓冲。中断从 dTD 取数后，前台用所有权交接省去第二次整帧复制。专用 ch7 只访问 64 KiB 探针私有 DDR；用与原生 SRAM 相同的头、序号、读写比例和队列深度测传输成本。命令为 `python tools/selectio_transport_bench.py --seconds 10 --out build/usb-isolated`，用 `--schedule grouped` 做对照。SRAM A/B 可用 `tools/selectio_pipeline_bench.py --clock 50000000 --frame 4096|16384 --schedule grouped|sliding`；大载荷使用 `selectio_f103_fixture.py --size 16384` 包住子命令。

1 GbE 的线速折合 125 MB/s。MTU 1500、IPv4/TCP 无选项时，以太网首部、FCS、前导和 IFG 计入后，理想 TCP 单向载荷约 118.7 MB/s，还需计 ACK、拷贝与协议栈。当前 PS 配置中 GEM0/GEM1 均未启用，主机两块有线网卡均显示断开。换 TCP 不会改变 SWD/JTAG 的事务数和目标等待；若 USB 等待完全消除而保留现有 PS 执行时间，100 MHz SWD 主机读/写仍受约 6.89/7.11 MB/s 的当前 PS 服务速率制约。对于 4 线 DDR ETM，64 MHz 满载时为 64 MB/s，超过本机实测 USB 后下载速度，千兆链路对持续在线流更有价值；环形 DDR 窗口仍可独立采集。

## ETM 接收

旧 RAW4 对每个电平要求两个相邻 5 ns 样本，50 MHz 对称方波的半周期仅有两次采样，几乎没有偏斜余量。候选在五根物理线上分别用 200 MHz IDDR 取得相隔 2.5 ns 的采样，确认边沿时取同一时刻的四位数据，沿用 TPIU 全/半同步、尾部和 DDR 捕获。独立源在每个频点给出 8 个初相位、每相位 128 个不同的完整帧和三个已知尾字节。给定模型中旧路径 24–50 MHz 全部通过，52 MHz 起不能覆盖全部相位；新路径 24–80 MHz 的所测点全部通过，88 MHz 和以上不能覆盖全部相位。[逐点计数](etm-rate.json)。复现命令为 `python tools/selectio_etm_sweep.py --out build/etm-sweep-new`。该边界为数字偏斜模型，实际线缆、电平转换、占空比与温度尚未覆盖。F103ZE 的额定 HCLK 上限为 72 MHz，CDC48 现场的真实 TRACECLK 为 24 MHz；实板 >50 MHz 需要合适的真实源或另行标识的实验时钟。[ST 数据手册](https://www.st.com/resource/en/datasheet/stm32f103ze.pdf)


### 占空比和相对延时

另测 TRACECLK 高电平占比 45% / 55%，数据四线延时维持 0.2、0.6、1.0、1.4 ns，时钟线分别延时 0.2 ns 或 1.6 ns。每个频点共 32 组不同相位、占空比和时钟延时，匹配全部 128 帧、三个尾字节且无错误才计通过。

| TRACECLK MHz | 双沿通过 / 总数 | 原接收器通过 / 总数 |
|---|---:|---:|
| 50 | 32 / 32 | 17 / 32 |
| 56 | 32 / 32 | 0 / 32 |
| 64 | 32 / 32 | 0 / 32 |
| 72 | 16 / 32 | 0 / 32 |
| 80 | 28 / 32 | 0 / 32 |
| 88 | 16 / 32 | 0 / 32 |

在这组离散应力样本中，64 MHz 是最高全通过点。72 MHz 起结果依赖板级相对延时，某个更高频点能通过部分相位不足以推断连续频带。复现时分别给 `tools/selectio_etm_sweep.py` 传入 `--mhz 50 56 64 72 80 88 --duty 45 55` 及 `--clock-delay-ps 200` 或 `1600`。已有 24 MHz F103 实板结果与本轮数字裕量分开验收。[192 个用例](etm-margin.json)
