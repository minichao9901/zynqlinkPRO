# AI 交接：SWD / JTAG 分支状态与合并分析

核对日期：2026-10-28（Asia/Shanghai）。本文是本地 Git、现存产物和测试记录的快照，不表示已完成合并或已经验收各分支最新 HEAD。后续工作先刷新引用与工作区状态，再按下文决策。

附件：[Git 分支快照](AI交接-20261028-SWD与JTAG分支及合并分析/branch-snapshot.json)、[本会话 JTAG 复测证据说明](AI交接-20261028-SWD与JTAG分支及合并分析/jtag-retest-evidence/README.md)、[复测文件哈希及配对身份](AI交接-20261028-SWD与JTAG分支及合并分析/jtag-retest-evidence/provenance.json)。

## 1. 用户目标和优先事项

- 用户后续计划把 SWD 与 JTAG 部分工作合到 main；本轮仅整理交接，没有执行功能合并、综合或新的板测。
- 用户明确要求 **bitstream 与 Zynq ELF 纳入 Git**。交付时必须保存实际测试的配对、SHA-256、源码身份、构建选项、时序和验收记录，不能只有源码。
- 用户关注 base JTAG 加 IDELAY 的路线；这是候选方案，尚未实现 TDO IDELAY，也没有证明它一定能稳定运行 50/60 MHz。
- 不把“编译通过”“setup/IDCODE 通过”“吞吐数字”“长块数据正确”“HEAD 与产物完全对应”混为一谈。
- `codex/main-lowfreq-sample` 按此前用户要求处于 PAUSED。读取其成果不等于恢复该任务；本次没有继续它的构建、测板或修改。

## 2. 分支和 worktree 总表

`main_only / branch_only` 是相对本地 main 的提交差异数；不是文件差异，也没有执行 fetch 来确认服务器最新状态。

| 分支 / 引用 | 当前 HEAD | worktree | main_only / branch_only | 定位 |
| --- | --- | --- | --- | --- |
| main | `d42b601` | `E:/zynqlinkPRO` | 0 / 0 | 已合 RTT/HSS PL→DDR 的集成基线，未合 JTAG 后端 |
| codex/probe-rtt-hss | `c26936c` | 无独立 worktree | 1 / 0 | 已被 main 包含；不必重复合入 |
| detached baseline | `902e228` | `C:/Users/Administrator/.codex/worktrees/probe-rtt-hss/zynqlink-baseline` | 0 / 8 | 原整数分频 JTAG PHY 基线，不是 main |
| codex/probe-jtag | `23db4a8` | `C:/Users/Administrator/.codex/worktrees/probe-rtt-hss/zynqlinkPRO` | 0 / 28 | 完整 JTAG 后端及后续 Q16/校准/限频，已归档二进制 |
| codex/swd-timing-generator | `1b55cf8` | `C:/Users/Administrator/.codex/worktrees/swd-timing-generator/zynqlinkPRO` | 0 / 7 | 可配置 SWD 时序事件架构；近期实现记录时序失败 |
| codex/main-lowfreq-sample | `9fdb1f5` | `C:/Users/Administrator/.codex/worktrees/main-lowfreq-sample/zynqlinkPRO` | 0 / 1 | 原架构上的低频 RX 修复及板级 profile；暂停的实验检查点 |
| codex/banked-packet-pipeline | `35f7cf6` | `E:/zynqlinkPRO_batch` | 11 / 0 | 已被 main 包含的历史优化；worktree 还有未提交实验 |
| codex/main-continuous-scheduler | `35f7cf6` | 无独立 worktree | 11 / 0 | 与上一引用同提交，不是另一套待合功能 |
| feature/swclk-sampling-delay | `9362797` | 无独立 worktree | 38 / 0 | 已被 main 包含的历史 SWD 采样阶段 |
| feature/swdio-idelay | `3013a5f` | `E:/zynqlinkPRO_idelay` | 47 / 5 | 分叉较早的 SWDIO IDELAY 实验，宜移植小补丁 |
| hflink-psusb | `324e4e1` | `E:/zynqlinkPRO_hflink` | 71 / 7 | 另一套 HFLink PL/PS USB 实现，参考或独立对照 |

本表中的 JTAG HEAD 是产物归档提交，本文提交后它会再前进一个文档提交；功能基线仍为 `9dacb44`。精确快照见同名目录下 `branch-snapshot.json`。

### 工作区未提交内容

- main：本会话此前修改的 `.gitignore`、新增 `AGENTS.md`；已有 `docs/dsh-session-20261027-review.md` 未跟踪。开放 build/releases 中 bit/ELF 后，`git status` 出现相应未跟踪目录是正常的，不能直接 `git add .`。
- JTAG：整理前干净；`23db4a8` 已提交归档及规则，未 push。
- SWD timing、lowfreq、IDELAY：本次核对时干净。
- baseline：`tools/baseline_matrix.py` 未跟踪，其 `setup()` 的 speed 传参单位需要审查，不能直接拿来当本轮正确测试脚本。
- batch：`build_dma.tcl`、`build_incremental.tcl`、`swd_batch_engine.v`、`swd_controller.v` 以及三份仿真文件有未提交修改。
- HFLink：多个固件/RTL/仿真文件已修改，另有 NA、reference 和新仿真脚本未跟踪。分支 HEAD 不代表这些工作区改动。

不要 reset、clean、覆盖这些目录，也不要把它们意外混入合并。

## 3. 三条最相关开发线

### 3.1 JTAG：baseline 与当前分支是两种 PHY 版本

共同祖先为 main `d42b601`。JTAG 后端从 `145fbf3` 开始，接入 CMSIS-DAP、PL DP/AP、posted read、TAP/IR 缓存以及 RTT/HSS 共用的数据路径。

重要节点：

| 提交 | 含义 |
| --- | --- |
| `145fbf3` | 完整 PL JTAG 后端入口 |
| `902e228` | 删除 45 MHz 硬钳位；保留旧整数 PHY、动态 FCLK 和相位闭环降频 |
| `7e68cec`、`17c73ed` | 新 Q16 发生器及 JTAG PHY 接入 |
| `ed7f4de`、`9d929c9` | 曾固定 FCLK，随后恢复按请求调整 FCLK；不能只信 fixed-FCLK 注释 |
| `a30ebc2` | 校准增加连续 CPUID block probe 与失败回退 |
| `9da4934` | 当前可靠频率上限及 idle 相关处理 |
| `3371cfd`、`4bab491` | 粗 sample offset、绕过限频/校准的诊断设频入口 |
| `02c655c`、`9dacb44` | 更正实际频率与 RTT/HSS 单位造成的旧结论 |
| `23db4a8` | 保存 8 个 bit、10 个 ELF、清单及已知指纹不一致限制 |

**如果选 base + IDELAY，起点是 `902e228`，不是整个 `codex/probe-jtag`。** 但 base 仍有短校准漏过长块错误的问题，不能原样视为发布就绪。若选完整 JTAG 分支，则会带入 Q16 PHY、粗采样 offset、诊断接口和保守频率上限，需要审查它们与 SWD 发生器的冲突。

JTAG 完整分支和 SWD timing 分支的共同祖先仍是 `d42b601`；二者没有互相集成。main 不包含 `902e228`，当前 JTAG 分支包含它。

### 3.2 SWD timing：仿真成果充分，物理实现尚不能当作通过

最新 HEAD `1b55cf8`：把 ACK/data 采样组合为 RX 事件。前序包括：

- `5a92f51`：抽出时序事件，与固定 main 做默认波形/周期对照。
- `d773dec`：vendor 0x90、原子配置提交、ACK/data 独立消费位置、Q16/阶段周期。
- `2d20baa`：事务边界重定时配置。
- `d5fc744`：更新实现测量；`0d2cd0b` 是低频测量文档，不是低频修复分支。

已记录第一阶段约 3652 万半拍对照、58 项运行；扩展阶段 80 项回归符合预期、180 点窗口扫描保留失败点。这些是相应阶段的证据，不能自动代表后续每个 HEAD 都完成了同规模验收。

`docs/measurements/20261028-swd-timing-build-compare.json` 记录：retimed candidate 在 150 MHz setup -4.684 ns，在 100 MHz 仍 -1.350 ns；生成了 `system_wrapper_unverified_retimed.bit`，但没有上板。当前 HEAD 又在该阶段后修改了 `swd_core.v`，本轮没有找到它已闭合时序/上板的证明。

资源报告显示配置/发生器带来明显面积和 carry 链增长；JSON 的 `resource_delta` 部分数值与最终 retimed candidate 数值不完全一致，不要据此给出一个“最终精确增幅”。保留原始阶段和整机 BD 范围再比较。

本分支 `prebuilt/zynqlink_probe.*` 仍是旧 main 配对，不能当成新 SWD timing 的已验收发布。最新方案若要合并，必须先解决组合 carry/mux 到 FSM 的长路径，再重新实现、封装配对并测板。

### 3.3 main-lowfreq：不依赖 Q16 的另一条 SWD 路线

`9fdb1f5` 直接基于 main，保持原状态机，新增 CFG bit18 RX boundary，修正 ACK/read 边界并保留完整 turnaround。固件按实际 PLL 频率选 profile：

- 实际 SWCLK ≤30 MHz：short boundary / Q2。
- 30..45 MHz：legacy boundary / Q1。
- >45 MHz：legacy boundary / Q2。

当前板 SWCLK 使用 SLOW/4 mA，SWDIO 仍 FAST/8 mA；并有 16 拍内部数字采样诊断。

这条线已经有提交到 Git 的测试配对 `prebuilt/zynqlink_lowfreq_checkpoint.bit/.elf`：FCLK120 MHz setup +0.278 ns、hold +0.034 ns；28 个 250 kHz..60 MHz SRAM 频率点和 7 个低频长测点通过；高速 SRAM/RTT 大致持平。

仍未解决一次早期 USB 掉线的唯一原因，以及最终 8变量100 kHz/60 MHz 一次窗口约 0.094% HSS 跳点；不能描述为全场景零跳点。SLOW/4 mA、30/45 MHz 分界是当前 F103/接线下的板级结果，不是所有目标通用参数。

优先阅读本分支 `docs/main-lowfreq-progress.md`，其次是 `main-lowfreq-board-20261028.md`、`main-lowfreq-rx-fix.md`。早期阶段文档的 35 MHz 策略已由最终的实际频率 30/45 MHz 策略修订。

**近期若以可靠落地为目标，这条线更适合选择性移植通用修复；若以任意可配置时序为目标，SWD timing 才是对应研究路线。二者不是同一个分支的不同名字。** 暂停状态仍需尊重。

## 4. JTAG 本会话实测与结论修正

### 已明确加载配对后的数据

F103 双 TAP 链默认 IR 长度 4、5；吞吐单位均为十进制 MB/s。流水参数：256 word/block、64 loops、depth8，每档 3 次，表中为中位数。

| 配对/请求 | FCLK / 稳态名义 TCK | 流水读 | 流水写 | 4 KiB 随机数据验收 |
| --- | --- | ---: | ---: | --- |
| baseline 30 MHz | 60 / 30 MHz | 2.233 | 2.173 | 通过 |
| baseline 40 MHz | 66.667 / 33.333 MHz | 2.525 | 2.509 | 通过 |
| baseline 45 MHz | 66.667 / 33.333 MHz | 2.493 | 2.495 | 通过 |
| baseline 50 MHz | 100 / 50 MHz | 2.430 | 3.093 | **失败** |
| baseline 60 MHz | 120 / 60 MHz | 2.314 | 2.200 | **失败** |
| JTAG 构建快照，30 MHz复测 | 60 / 30 MHz | 2.280 | 2.244 | 通过，恢复 SRAM |

base 验收 40/45 MHz 被校准降到 33.333 MHz。50/60 MHz 的短寄存器矩阵虽然每项5/5，长块仍失败。不能把这些高频吞吐当有效数据性能。

注意原 `test_jtag_board.py` 依次跑频率，50 MHz assert 失败会中止，因此 60 MHz 另开测试。失败 JSON 没有成功行，并不等于“未测”；失败位置和此次解释见同目录 `jtag-retest-evidence/README.md`。60 MHz 那次原脚本在高速连接后才备份 SRAM，备份自身未先低速交叉验证，故其 restore_match 仅证明与那份备份相等，不是原始状态完好性的独立证明。

### 不能延续的旧说法

1. 本会话最早只在两个 worktree 运行脚本，没有换板上配对；当时所谓两个架构对照实际仍是同一套已加载固件，不能用于架构归因。后续显式下载配对后的同30 MHz结果才可比较。
2. 早先“优化版固定62 MHz FCLK”的回答不准确：当前代码实际也按请求调整 FCLK，再计算 half_q。32 MHz 请求/上限量化到31.034 MHz，不代表所有速率一直用同一 FCLK。
3. 早先把低写速直接归为“主机 USB 调度抖动”证据不足。本次配对重载后的30 MHz复测未重现大差距，但加载身份、会话状态和主机负载等因素未单独隔离，不能宣布唯一根因已找到。
4. 不能说“base 请求50必然滑到33”：`902e228` 已删除旧45 MHz clamp，本次请求50实际50并读错。更老版本可能先50→45，再因四相位校准失败降低 FCLK 至66.667，得到33.333；`902e228` 的40/45请求也可因相位校准回退到同一频点。
5. base 与当前 JTAG 的 RTT 同30 MHz/512 B块历史复测约2.030/2.029 MB/s；旧的“RTT -15%、HSS -50%”结论已被工具Hz/kHz误用推翻。历史表标题有33.33/31.03与正文30 MHz不一致，复用时查原始条件，不能抄表头当元数据。
6. 相同30 MHz的读写差距很小，不能用33.333对31.034的不同频率对照证明整个架构优劣。

### 工具限制

- `jtag_block_bench.py --speed`、`jtag_speed_matrix.py --speeds`、`setup()`：**kHz**。
- `test_jtag_board.py --speeds`、`benchmark_rtt_forward.py --speeds`、`benchmark_hss_dynamic.py --speeds`：**Hz**。以各工具 help/代码为最终依据。
- 流水读主要验长度；流水写只验命令echo，没完整检查 ACK/count/payload。吞吐与正确性必须分项记录。
- `measure_jtag_tck.py` 仍用旧vendor0x89偏移，曾输出荒谬的数万MHz，不能引用。当前响应计数为 `[3:7]` cycles、`[7:11]` bits、`[11:15]` scans；用 `measure_jtag_scan.py` 并解释统计含义。
- FCLK/2 只适合half_q一拍的稳态DR；小数配置、raw/TAP导航段、含USB空闲的有效边沿率不能都叫实际线频。
- `measure_jtag_scan.py` 中把scans/word打印成“TCK per word”的标签也不准确。应分开报告扫描次数、位数、等待周期。
- LA探头可能改变边沿和采样窗口；测量须记录是否接探头，不能把不同负载当同条件。

## 5. 产物身份与可恢复性

### JTAG：已经纳入 Git，但不是 HEAD 完全匹配发布版

`23db4a8` 的入口是 `prebuilt/jtag/README.md`、`manifest.json`、`SHA256SUMS`。

| 文件 | SHA-256 |
| --- | --- |
| JTAG `build/fpga_dma_global/system_wrapper_verified.bit` | `019307d5d03f8f6467f465395ac231ceb98ea9bfb574efe15cfe897bc1e80b53` |
| JTAG `build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf` | `4c63a9ad645f24524ef4ec7f029f72b969a61d4631c2d6a95ee814106305c834` |
| baseline `build/fpga_dma_global/system_wrapper_verified.bit` | `9c11fbdca443f8e18f8295bb0da4ba7925a28a24955a577a1f63e2c8b2a7617f` |
| baseline `build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf` | `257dbb1adea96c5b42bb43666058e8e0c8ccb75e32fdcbdc1c1dbf2cf434068e` |

JTAG ELF与构建manifest及当前固件源文件吻合；bitstream综合stamp与 `9dacb44` 源码的 `jtag_core.v`、`jtag_shift.v`、`swd_controller.v` 不一致。已记录三项差异，不得把它重命名后称为最新HEAD构建。

baseline的上述bit/ELF本次核对仍只在本地build，未纳入 `23db4a8`；且没有同样的RTL综合stamp。它们与 `902e228` 的对应来自既有构建/会话记录，不是本次对完整源列表做了密码学验证。未来若要使用这条路线，先保存并补齐证据，避免被下一次构建覆盖。

18个归档文件里包括历史实验，以及F103目标端HSS/RTT producer、GPIO ELF，不能全部当Zynq固件，也不能任意按目录名拼配对。

顶层 `prebuilt/zynqlink_probe.bit/.elf` 是旧SWD/RTT/HSS产物。曾误把它搭给baseline ELF，读到 `LOADED_SWD_FEATURES=0x44500007`，于是JTAG Connect返回 `02 00`；换真正JTAG bit后是 `0x4450000F`。这次失败是产物错配，不是base不支持JTAG。

SWD timing的unverified retimed bit只供诊断；lowfreq checkpoint有独立prebuilt及manifest，不能覆盖旧main发布对。新的规则已提交在JTAG分支 `AGENTS.md`/`.gitignore`，main工作区也有同样修改但尚未提交。

## 6. 合并时最容易出错的接口

### 同名发生器并不兼容

| 项目 | JTAG 分支 `swj_clk_gen.v` | SWD timing 分支 `swj_clk_gen.v` |
| --- | --- | --- |
| half_q | 40 bit端口 | 32 bit端口 |
| sample参数 | `sample_off` | `sample_at_end`、`sample_offset` |
| edge事件 | 寄存后的edge_tick，消费者有对应启动补偿 | 同拍组合事件，用于保持main逐拍等价 |
| 输出 | 包括 `clk_out` | 无 `clk_out`，协议状态机决定管脚动作 |
| 使用方 | jtag_shift | swd_core |

不能在add/add冲突中直接选ours/theirs。建议先分别命名并保留消费者语义；等两协议都验收后再考虑共用实现。不要为了复用名字提前改变SWD或JTAG边沿时刻。

### CSR / vendor / CFG 实际冲突

| 位置 | 冲突 |
| --- | --- |
| CSR `0xD0` | JTAG_IDLE vs SWD_TIMING_CONTROL |
| CSR `0xD4` | JTAG_SAMPLE vs SWD_TIMING_XFER_HALF_Q |
| CSR `0xCC` | 当前JTAG half_q；base原PHY无此扩展 |
| vendor `0x89` | JTAG phase + scan统计 vs lowfreq RX boundary |
| vendor `0x88` | 原forensic记录、lowfreq增加action2；合并需能力识别 |
| CFG bit18 | lowfreq RX boundary vs IDELAY实验 `CFG[22:18]` 延迟值 |
| vendor `0x82` | IDELAY分支延迟tap；其他分支可能空槽，不能直接假设ABI已统一 |

SWD timing的D0..F8已占连续区域，控制器地址窗口要求8 bit。JTAG也新增高地址，合并必须同时审查AXI地址宽度、地址截断/别名、byte strobe、签名、busy检查、reset和旧bit兼容行为。

### 其他共有修改点

- `DAP_config.h`、`DAP.c`：调频、GPIO复用、实际频率、JTAG分派和CFG位。必须按debug_port区分策略。
- `DAP_vendor.c`：上表接口和错误响应布局。
- `probe_target.c`、`probe_stream.c/.h`：RTT/HSS接管、暂停、停止、时钟/配置/AP上下文恢复。保留两协议完整状态，不只保存一个CFG word。
- `swd_controller.v`：PHY选择、三态、IDDR输入、寄存器解码、引擎busy和链式返回。
- build Tcl、仿真源列表和host测试：不能丢掉任一新增模块，也不能保留一个同名却接口不匹配的模块。

## 7. 必须保留的数据路径语义

- JTAG posted-read/IR cache/WAIT重试/包尾错误检查以及 `fenced_result_valid` 缓存；不能把JTAG RDBUFF当普通无副作用寄存器。包尾检查消耗的未决AP结果必须正确归还。
- RTT：完整包搬入DDR、DMA提交确认后才能推进目标RdOff；失败可重试，USB reset后旧会话不得发布数据。
- HSS：包不可变、bank所有权、序号/时间洞/跳点统计，不能靠丢掉坏帧伪造零错误。
- SWD：compact ACK、完整turnaround、WAIT/FAULT/parity路径、零idle实验边界及连续请求握手。
- I/O三态和声明次序：JTAG分支修过Vivado generate局部隐式未驱动网导致GPIO失效的问题，不能在手工拼接控制器时引回。

## 8. IDELAY 路线：可借鉴实现，不能照搬结论

`feature/swdio-idelay` 有 `IOBUF.O → IDELAYE2(VAR_LOAD) → IDDR.D`、200 MHz参考及runtime tap接口。历史记录给出约78 ps/tap、31级增量约2.4 ns；不是对当前板所有I/O/频率的重新规格验收。

该分支实测SWD60 MHz保留可用；64.3/69.2 MHz仍未找到DP/AP读共同通过的窗口，75 MHz全部失败。它证明延迟单元起作用，不证明加上它就能升频成功。

移植到TDO时需要独立寄存器、匹配管脚可用延迟资源、IDELAYCTRL参考/复位/ready、tap读回及忙时修改保护。原代码 `RDY()` 和 `CNTVALUEOUT()` 未接出，移植版宜补可观测性，不要直接复制后宣布就绪。

还需纠正“输入延迟=更晚采样”的直觉：固定采样沿S、数据延迟D时，采到的是外部信号在S-D的值。增加输入延迟与把采样时钟沿后移不是同一方向。可以结合Q1/Q2、前一bit窗口和延迟移动数据眼，但应先画清位对应关系，再扫相位×tap并选连续通过窗口中央；若确实需要更晚捕获，评估独立采样时钟相移等方案。

## 9. 建议的集成顺序（未执行）

1. 刷新Git快照，保全所有dirty worktree；从main另建集成分支，不直接在生产main尝试冲突解决。本轮不预先创建该分支。
2. 先决定SWD路线。近期交付可优先审查lowfreq通用修复：PLL返回值/实际频率、默认关闭RX边界、完整turnaround及测试。SLOW/4 mA和分档做板级profile；已暂停工作不得默认为恢复。
3. 决定JTAG路线。base+IDELAY选择 `902e228` 的后端/PHY，再补长块校准与可靠限频；完整Q16路线选择 `23db4a8` 以前的功能状态，但接受发生器兼容性、时序及产物不匹配待解决事项。不要只摘 `902e228` 单个commit到main：它只是删clamp，不含前序完整JTAG后端。
4. 先设计统一CSR/vendor能力表及迁移策略，再改代码。保留独立发生器或明确适配器，避免静默改变事件延迟。
5. SWD timing全功能扩展作为后续独立阶段，先关闭长组合路径并通过相同BD/时钟约束的整机实现，不能把unverified bit当待发布产物。
6. 跑相应host、RTL、真实目标模型回归，再构建**同一源码状态**的bit/ELF。记录源码hash、STA、DRC、feature签名、加载日志。
7. 同板分协议验收：SWD低频/高频及切换；JTAG实际频率/随机长块；RTT/HSS动态源、计数/字节精确性、跨1 KiB/环回、并发接管与reset恢复。吞吐必须带ACK/count/payload校验及内存/寄存器/RCC恢复。
8. 最后把配对二进制和证据提交到集成分支，再评估合main。单个频率PASS不扩大为全板、温压、线缆、所有目标的保证。

## 10. 后续 AI 的入口和操作提醒

先执行：

```powershell
git worktree list --porcelain
git branch -avv
git status --short --branch
git merge-base main codex/probe-jtag
git merge-base main codex/swd-timing-generator
git log --oneline main..codex/probe-jtag
```

主要入口按所属worktree读取：

- JTAG：`prebuilt/jtag/README.md`、`docs/JTAG-IDDR时序修正.md`、`tools/test_jtag_rtl.py`、`tools/test_probe_host.py`、`tools/test_jtag_board.py`。
- SWD timing：`docs/SWD时序发生器重构与仿真.md`、`docs/SWD时序可配置接口.md`、build-compare JSON、`tools/swd_timing_sim.py`、`tools/swd_timing_extended_sim.py`。文档分阶段有历史状态，不用早期“只仿真”覆盖后来失败的实现记录。
- lowfreq：`docs/main-lowfreq-progress.md`、配对manifest、`tools/run_swd_rx_regress.py`、`tools/run_swd_rx_wire.py`、`tools/test_swd_lowfreq_board.py`。
- IDELAY：`E:/zynqlinkPRO_idelay/docs/SWCLK上限与采样实验.md`、`tools/idelay_sweep.py`。
- main已有 `docs/dsh-session-20261027-review.md` 是另一个本地未提交会话审阅来源，不能假定新clone能读到它。

下载示例（需要明确选择配对；不是本轮再次执行的命令）：

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl <ZYNQ_ELF> <BITSTREAM>
```

切换worktree不会切换板上固件。上一轮本聊天最后显式加载的是JTAG快照，但随后存在其他低频工作记录，**本文没有查询当前板状态，不能保证此刻板上仍是哪一版**。共享硬件测试前先确认占用，尤其不要在其他会话运行时重配FPGA。

本轮仅整理文档和既有证据，不新增性能承诺；没有push、执行功能merge或恢复暂停任务。
