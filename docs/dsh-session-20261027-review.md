# DSH JTAG 会话阅读笔记（2026-10-27）

这份笔记供后续工作接续，记录实验、结论的变化和证据边界，不代表新的实现方案。

来源：`C:/Users/Administrator/Desktop/dsh-session-session-70f13b7d-632b-4f83-93a5-69f9b15a18f8.zip`，其中 `session.v4.jsonl` 共 20 轮，最后事件为 seq 2952，时间为北京时间 **2026-10-27 20:33:56**。会话末尾正在等待相位修复版 Vivado 构建，没有该构建后完整上板验收的返回结果。

实际代码位于 `C:/Users/Administrator/.codex/worktrees/probe-rtt-hss/zynqlinkPRO`，分支 `codex/probe-jtag`；核对时 HEAD 为 `2c9e63b`，相对 main 的 `d42b601` 有 14 个提交。会话中包含 DS 自己的实验，也包含 DS 接手、读取并提交的前一段 Codex 工作，不能全部归为 DS 独立实现。

## 工作经过与结论变化

| 阶段 | 实际工作与结果 | 证据 |
| --- | --- | --- |
| 第 1 轮 | 接手未提交的 JTAG 后端；发现 ELF 比源码旧，重编译；低速正常，50 MHz 的 IDCODE、ACK、块数据表现不一致；增加诊断与延迟仿真 | seq 139–214、538、658–814 |
| 第 2 轮 | 中途 Codex 已完成 IDDR 双相、位窗口、posted-read/fence 等修正；DS 补齐上板验收，改善校准降频步进并提交整套工作 | seq 873、932、964、1000；`145fbf3` |
| 第 2–3 轮 | 分离 HSS 丢弃/回复模式，测 RTT、流水块访问，修正“只有 1.2 MB/s / HSS 只有 40 kHz”的印象 | seq 1008、1049、1071、1087、1095；`e35bfda`、`f77a6f4` |
| 第 4–7 轮 | 从怀疑 PS 回落、RTL 气泡、TCK 半速，逐步用 profiling、仿真、扫描计数定位高速多一次扫描 | seq 1165、1193、1304、1678、1738；`bb1df43`、`e8185af`、`81767d9` |
| 第 8–9 轮 | LA 测 TCK/TMS；正常速率下外部脉冲与内部计数吻合；接探头后高速校准上限下降，无法直接抓到 60 MHz 的重试工况 | seq 2005–2039；`8f9abed` |
| 第 10–13 轮 | 解释 PLL/FCLK 分频与校准回落的区别；讨论共用发生器；查看 HFLink；去掉效果不佳的 45 MHz 钳位，留下重构前 tag | seq 2054、2062、2149、2203、2211；`902e228` |
| 第 14 轮 | 完成 Q16 小数半周期发生器及积分频率检查 | seq 2320；`7e68cec` |
| 第 16 轮 | 新发生器直接接入 JTAG；core/pipeline 与若干延迟模型通过；修正了扫频参数未真正传入的问题 | seq 2441、2449、2485；`17c73ed` |
| 第 17–18 轮 | 固件改用固定 FCLK 120 MHz；补新 RTL 的 Vivado source list；新 bit 上板后发现部分小数比例失败 | seq 2640、2729、2791、2815；`ed7f4de`、`f171beb` |
| 第 19 轮 | 扩大频率扫描；改回按请求 TCK 调整 FCLK；IDCODE 能通过的高频仍出现随机块数据失败 | seq 2842–2866；`9d929c9` |
| 第 20 轮 | 解释 IDDR 仍有效；比较旧、新 shifter 的段起始相位，修复两拍偏差，仿真回归通过；启动构建 | seq 2913、2933–2952；`2c9e63b` |

## 已建立的架构与协议语义

JTAG 是现有 PL 数据通路的另一个后端。`jtag_core` 处理 TAP、IR 缓存、DP/AP、WAIT、posted-read 和 fence；`probe_sample_engine`、`probe_rtt_engine`、`probe_stream_engine` 继续承担自主采样、RTT 环形缓冲处理、1 KiB 拆分、组包和包发布。AXI CDMA 把包搬到 DDR，PS 配置会话、管理 DMA/USB 队列。稳态不通过 PS 逐字访问 AP 或逐点组包。连接时的软件校准与稳态热路径应分开理解。

目标为 F103CB，扫描链有 ARM DAP IR4 和边界 TAP IR5，存在一个 DR bypass 位。高速普通访问把 DR 导航、有效数据、保护位、退出及 idle 合并为一段连续扫描；相关测量约为每段 43 TCK。这个 43 不是所有操作、链配置、idle 设置的固定常数。

TDO 已固定经过 OPPOSITE_EDGE IDDR，两相均在用：

| `JTAG_TIMING` 模式 | 输入相位 | DR 位窗口 |
| --- | --- | --- |
| 0 | Q2，FCLK 下降沿 | 当前位 |
| 1 | Q1，FCLK 上升沿 | 当前位 |
| 16 | Q2 | 前一位 |
| 17 | Q1 | 前一位 |

四种模式是“输入相位 × 位窗口”两个维度，不是四个任意连续相位。TDI/TMS/TCK 仍由 fabric 寄存器输出，不因新增发生器就变成 ODDR。IDDR 与时钟事件发生器作用不同，重构后仍需要 IDDR。

DR 请求前有两个填充位，以便延迟的最后一个响应位能在目标撤销 TDO 输出前被收齐，并保证 UPDATE 时请求内容正确。raw JTAG Sequence 不擅自增加用户要求的 TCK 数，而采用较慢时钟和相应捕获位置。

尤其要保留 **包边界 fence 消耗未决 AP 结果时的缓存**。会话中修正了曾误用 SWD 缓存语义的 JTAG RDBUFF 模型；当前 `jtag_dp_model.sv` 中 JTAG RDBUFF 为读零语义，扫描带出先前结果。CTRL/STAT 检查可能带走未决样本，`jtag_core` 用 `fenced_result/fenced_result_valid` 保存并在下一次前端访问归还。遗漏它会在 HSS 中插入零。现有全链路回归还覆盖 sticky-error 时不发布包、包不可变，以及 DDR 提交后才更新 RTT RdOff。

校准先低速保存 CSW/TAR、SELECT 软件影子和 CPUID 基准，再扫四种模式，检查多组 TAR/CSW 图案及只读 CPUID，最后恢复上下文。历史临时版本曾把 DRW 访问误称为 CSW 访问，已修正；早期 speed matrix 还曾多插入一个 CMSIS-DAP 头字节。因此旧诊断矩阵不能直接作为根因证据。

## 性能测量应如何继承

### 块读写与 WAIT

`test_jtag_board.py` 是随机数据正确性验收：每档核对 107940 字节，同时备份/恢复 SRAM。它每个 1 KiB 块都会重新设置地址并串行等待 USB，约 1.2 MB/s 不能代表流水吞吐上限。

`jtag_block_bench.py` 使用自增 TAR 和多请求流水，历史同板结果为：

| 传输 | 请求 TCK | 流水读 | 流水写 |
| --- | --- | ---: | ---: |
| JTAG | 30 MHz | 2.17 MB/s | 2.01 MB/s |
| JTAG | 60 MHz | 2.19 MB/s | 2.20 MB/s |
| SWD | 30 MHz | 2.27 MB/s | 2.15 MB/s |
| SWD | 60 MHz | 4.13 MB/s | 2.98 MB/s |

这个 benchmark 主要检查返回长度/基本格式，没有完整比较随机读回数据。因此吞吐成绩与随机数据正确性要分别记录，不能由前者推导后者。也不要把不同 bit、固件、采样模式的结果合成同一个稳定包络。

定位过程中的最终直接观测（seq 1738）是：

| 请求 TCK | scans/word | bits/scan | 块读 |
| --- | ---: | ---: | ---: |
| 30 MHz | 1.04 | 42.8 | 2.26 MB/s |
| 40 MHz | 1.04 | 42.8 | 2.42 MB/s |
| 45 MHz | 1.04 | 42.8 | 2.53 MB/s |
| 50 MHz | 1.04 | 42.8 | 2.50 MB/s |
| 55 MHz 请求档 | 2.04 | 43.4 | 2.07 MB/s |
| 60 MHz | 2.04 | 43.4 | 2.30 MB/s |

支持的结论是：高速时多出的扫描抵消了提频收益，DS 将其定位为 WAIT 重试。目标 AP 周转约 0.81–0.86 µs 是根据交叉点估算，不是独立精密测定的物理常数；“45 MHz 最优”也只适用于当时目标与配置。core 独立仿真为每字约 92–94 FCLK/43 TCK，不能据此宣称整个系统不存在其它优化空间。

已被后续证据取代的判断：PS 逐字回落、TCK 实际半速、约 1.1 µs 必然来自 RTL 固定气泡。`dbg_pkt_taken/fallback=5262/0`、FCLK 回读和扫描统计是关键区分证据。

最初“TCK 计数器坏了”的说法也已撤回：主机响应解析错了一字节，应该从 `r[3:7]` 等位置读取，当时用了 `r[4:8]`。改成新计数器不等于证明旧计数器硬件失效。

### LA 与采样余量

500 MS/s、5 ms、CH0=TCK/CH1=TMS 时，工作工况测得 141957 个上升沿，扫描内周期中位数 28 ns（约 35.7 MHz），估算每字约 44.8 脉冲，与 `43 × 1.04` 对上。

**这次 LA 没有直接拍到 60 MHz 下每字约 88 脉冲的工况。** 后者来自内部扫描计数；LA 在正常工况验证了计数方法的可信度。DS 的标题/总结有时把这两个证据层级说得过近。

接探头后校准上限落到约 33–36 MHz，换旧 bit 也出现。它强烈提示电气负载/时序余量问题；“探头电容使 TCK 延迟，继而 TDO 延迟”是合理解释，但没有模拟波形直接量化该链路。不能把这个观察等同于已测出精确 TDO 往返延迟。

45 MHz 钳位随后被删除：请求 45 MHz 对应的 FCLK/相位可能过不了校准，进一步降到 33.3 MHz，实际效果反而不好。不能直接恢复这个钳位作为既定优化。

### RTT 与 HSS

历史 RTT 主机吞吐 **2.3935 MB/s**，probe 侧 2.3915 MB/s；约 2 秒窗口，`sequence_exact=true`、`all_published_received=true`、errors=0。它属于旧 IDDR 配对的记录，不是新发生器的验收成绩。

HSS 不能概括为“上限 40 kHz”。回复模式历史结果包括：

| 请求/周期 | 有效率 | 跳点 |
| --- | ---: | ---: |
| 250 kHz / 96 ticks | 250.0 kHz | 0% |
| 500 kHz / 48 ticks | 496.0 kHz | 约 0.79% |
| 600 kHz / 40 ticks，一次细扫 | 595.2 kHz | 约 0.79% |
| 约 632 kHz / 38 ticks | 626.6 kHz | 约 0.79% |
| 约 667 kHz / 36 ticks | 633.9 kHz | 约 4.9% |
| 750 kHz / 32 ticks | 约 39.5 kHz | 约 94.7% |

500 kHz 做过 6 秒长测。41、39 ticks 的相邻频点异常；同一个 40 ticks 在另一轮也出现约 65.7% 跳点。因此“约 630 kHz”表示若干点取得过该成绩，不表示整个范围已经稳定验收。奇偶/会话残留是 DS 的待验证怀疑，尚无根因闭环。

约 0.79% 有包边界相关规律，**仍然是真实跳点**。原文“设计底噪，不是损失”不宜继承为无损结论。错误计数为零、样本有序与没有跳点是不同指标。

丢弃输出实验把 PL 访问预算与回复/提交路径区分开：750 kHz 时丢弃模式约 375 kHz，回复模式约 39.5 kHz；回复包从约百个样本退化到约一个样本/提交，提交约 40.4k 次/秒。包聚合退化与 PL 每样本预算是两个问题。退化触发条件和相邻 tick 坏点仍未修复，不能假定这次时钟重构已解决它们。

## 新发生器的目标、实现与实测边界

HFLink 提供了“输出事件与采样事件分开配置”的参考，但本身用整数 DIV。DS 据此实现了 `swj_clk_gen`：Q16 半周期，整数计数器加小数累加器决定何时多等一拍，输出 `clk_out/edge_tick/sample_tick`。原先承诺固定 FCLK 即可得到恒定采样余量，后续实板表明还需要处理完整输入路径与位窗口，不能仅由频率生成正确推导出来。

截至 `2c9e63b`：

- JTAG 已使用 `edge_tick`，`sample_off` 固定为 0，`sample_tick` 未连接；TDO 捕获仍在 `jtag_shift` 翻转 TCK 的事件里。
- SWD 尚未接这个发生器；现有 SWD compact ACK、turnaround、ack_delay 等仍是原有路径。
- CSR `0xCC` 编程 half_q；普通 DR 使用基准半周期，导航/部分 raw 捕获段乘 2 或 4。
- 固件已经从固定 FCLK 120 MHz 改回目标 `min(2 × 请求TCK, 120 MHz)`，再根据**实际** FCLK 计算 half_q。PS 整数分频仍会量化 FCLK，不能假定所有请求都能获得半周期恰好 1 拍。
- 多处注释仍写着 fixed FCLK；应以函数执行逻辑及实验版本为准。历史校准逐级降频已在固定 FCLK 阶段删除，恢复随速率改变 FCLK 后未一并恢复。

### “整数或半整数”应怎样记录

半周期拍数 `H = FCLK / (2 × TCK)`；H 为整数或半整数等价于完整周期 `FCLK/TCK` 为整数。固定 120 MHz 下，H=1、1.5、2 分别对应 60、40、30 MHz。

seq 2815：5/15/20/30/60 MHz 以及 **25 MHz（H=2.4）**、40 MHz（H=1.5）通过；45/50/55 MHz 失败。seq 2842 进一步看到 33/36/38/39 和 41–44 MHz 失败，于是 DS 归纳“只有整数或半整数”。

**25 MHz 是该普遍化表述在同一会话中的反例。** 稳妥结论为：在当时高频测试点，规则周期比部分小数周期更容易通过；30–60 MHz 区间的扫描支持这条经验。尚不能把它当作一切频率、相位、返回延迟下的必要/充分条件，也不能认为发生器数学上无法产生 50 MHz。

这些 PASS/FAIL 的包装来自 `jtag_timing_probe.py` 中 `setup()` 是否成功，不是每一档都运行随机 SRAM 块数据比较。固定 100 MHz 后请求 50 MHz 能通过 setup；请求 55/60 MHz 也通过，因为 half_q 被钳在至少一拍，实际最多只有 50 MHz，不能把那两行当成真实 55/60 MHz 成功。

`jtag_timing_probe.py`、块 benchmark 和板级验收里仍有 `TCK=FCLK/2` 的显示假定；小数 half_q 场景不成立。扫频脚本虽然已传 `--halfq`，表头/JSON 的 TCK 计算仍按旧公式，报告中出现所有档都显示 60 MHz 的问题。未来复用时应同时保存实际 FCLK、half_q、模式和有效位时钟测量。

### 末尾相位修复的证据边界

seq 2913 的旧/新测试为：旧 first/last/done=10/94/96，新为 12/96/96；seq 2933 修复后两边均为 10/94/96、43 个上升沿。修改是发生器 enable 从仅 busy 改成 `busy || (start && count != 0)`。

这证明该测试条件下的段起始相位对齐。`tb_shift_phase.sv` 两边均关闭 capture、TDO 固定为 1；“same capture”不构成真实数据采样验证。它只比较上升沿数量、首末/完成计数，未逐拍比较全部波形，且相位不同的分支只打印 NOTE。DS 把现象解释为末半周期被压缩并导致高速回归，这仍需要更多波形/板级数据支持。

重构前已有真正 60 MHz 随机数据通过的旧配对，但 baseline tag `probe-jtag-baseline-20261027` 最终指向 `902e228`，其紧邻的 seq 2203 在 50 MHz 就停止验收。不能把“留了 baseline tag”误读为“该 tag 所有频点均通过”。新发生器上板后的 seq 2858/2866 则明确记录 50/60 MHz 随机数据失败。

会话截止时最新修复的 core 和三种 pipeline 回归通过，构建尚无完成结果。另查导出后的本地文件：`phase_fix_acceptance.json` 只含 1/10/30 MHz 成功行，`acc50b.json`、`acc60b.json` 的 rows 为空；这些文件没有完整失败栈，也没有新增高速完整成功证据，不能仅凭文件存在判断通过。

## 后续工作可直接使用的入口

| 目的 | 工作树内相对路径 |
| --- | --- |
| 高速数据正确性与 SRAM 恢复 | `tools/test_jtag_board.py` |
| 流水吞吐对比 | `tools/jtag_block_bench.py` |
| FCLK/setup 诊断 | `tools/jtag_timing_probe.py`、`tools/check_probe_state.tcl` |
| cycles/bits/scans 统计 | `tools/measure_jtag_scan.py`；CSR `0xC0/0xC4/0xC8`，vendor `0x89` |
| 发生器与起始相位 | `fpga/sim/tb_swj_clk_gen.sv`、`fpga/sim/tb_shift_phase.sv` |
| core、posted/fence、完整 RTT/HSS | `tools/test_jtag_rtl.py` |
| FCLK/TDO 延迟/模式/half_q 扫描 | `tools/run_jtag_timing_sweep.py` |
| 生产 C 校准与上下文恢复 | `tools/test_probe_host.py` |
| 外部 TCK/TMS | `tools/la/la_jtag_scans.py`；主仓 `tools/la/la_capture_export.py` |
| 历史结果与工件身份 | `results/jtag/`、`build/jtag_reply_checked/` |

`results/` 被 gitignore，旧结果并不随 commit/tag 自动保存；部分 JSON 记录了 bit/ELF SHA-256，部分仅有请求频率。后续比较要使用配对工件及其身份，不能把仍留在 build 中的旧 bit 当作刚生成的结果。会话已遇到新模块未加入 Vivado source list、构建外层返回 0 但内部失败、旧 bit 留存，以及增量布局 DRC 后自动重跑 fresh placement等情况。判断构建成功应核对 `VERIFIED_BITSTREAM_READY`、新工件和对应时序结果。

后续仍待解决的事项是：高速随机数据闭环、部分小数周期失败的准确机制、采样事件是否及如何接入、校准遗漏边缘错误、HSS 坏点及包聚合退化。上述事项不能由现有低速/理想延迟仿真 PASS 自动推导为已解决。
