# ETM 流式解码与增量统计：离线持续输入实验

> **main归档说明（2026-11-04）：用户暂不采纳，相关研究暂停。** 本目录仅同步历史文档与证据，候选源码、工具和EXE未并入main。原worktree/运行目录为当时路径，已按本次归档流程移除；不可据其描述推断当前main能力或当前板上身份。完整研究树及程序保留在Git tag `archive/etm-offline-research-20261104`（`0732f67`），取回方法与状态见[归档索引](../etm-offline-research-archive-20261104/README.md)。原实验分支的ETM写文件问题号“ZL-132”与main HAL问题重号，main中改用 **ZL-143**；原始JSON、manifest与历史正文保留原编号。

2026-11-04（Asia/Shanghai）。问题 **ZL-006，仍为部分解决**。在既有 worktree `E:/zynqlinkPRO-work/etm-block-cache-20261104`、分支 `codex/etm-block-cache-20261104`，基于 `41ec0e2` 继续实验。全程未访问硬件，没有加载/修改 bit、PS ELF、MCU、时钟或 Flash/QSPI，没有修改 main 或固定 bridge EXE。

**结论：H743 两种保存负载在 1 倍平均输入速率下，持续 20 秒可以完整消费并持续累计统计；F103 的 1 倍速未通过。H743 有短时积压，尚不能承诺稳定的 1ms/10ms 响应。** 这里实现的是解码和统计的在线路径，没有让完整历史查询库在每次更新时重建。

用户提出的“小窗口显示”与“后台只解码小窗口”是不同问题：本实验每个字节都进入同一个解码器，累计统计覆盖全部输入，界面可以另选窗口显示。该结果支持这条实现路线，但不能据此确定 Ozone 的内部算法或刷新窗口。

## 实现

`固定 raw fixture → 独立定时生产者 → 1MiB 有界队列 → 持久 OpenCSD → 增量统计 → 周期性累计快照`

- 新增 `etm_decode::StreamSource` / `decode_stream`。整个输入只创建一个 OpenCSD tree，跨块保留半包、地址、上下文和投机状态；重复 fixture 接缝不插入 reset/EOT，最后只发一次 EOT。原完整文件入口保留。
- `native/stream_experiment.hpp` 新增纯离线原型。生产者按计划投递，队列满就明确失败，不等消费者腾空间来伪造实时能力，也不静默丢弃后继续报成功。
- 代码字典按第一次出现的范围从不可变 ELF/DWARF/Capstone 解析，缓存代码信息，不预先扫描未来 Trace。`NativeImage::prepare_addresses` 增加一次性初始化保护，避免每个新范围重扫 ELF 函数。
- PC 计数先按重复范围累计，汇总时再展开到 PC；调用、异常、返回和原有未知执行语义保留。`Tracker::feed_linear_span` 只在同一函数/源码位置、已验证的同栈帧片段中批量更新；需要调用栈状态转换时先走原逐条逻辑。原型不累积完整指令 facts、包列表和60张历史查询表。
- 在线统计包括完整指令记录数、成立/未成立/未知执行、每PC计数/周期、函数/源码热点、调用边和累计火焰图；定义与现有完整分析一致，**指令记录数仍包含未成立及未知状态，不被当成真实耗时**。
- 普通配置每100ms生成完整 analysis JSON（函数、热点、火焰图等），计算SHA并保留轻量快照日志；另测每10ms生成一次。这里包括生成和hash的工作，不包括网络传输、浏览器绘图或GUI首屏。未强行在块边界结束待定范围，快照是当时已提交统计的水位。

原型沿用上一轮默认关闭的 `ETM_EXPERIMENT_IMMUTABLE_BLOCK_CACHE=1` 研究开关；仅用于固定代码镜像离线输入。文件输入和代码均先就绪后启动回放；首次新PC的字典解析包含在在线处理时间内。没有实现 USB/TPIU/PL 接收通路。

## 输入与持续输入模型

使用上一轮相同的三份 raw ETM + ELF；路径与完整SHA见 [campaign-summary.json](raw/campaign-summary.json)。它们已经是解复用后的 ETM 字节，不包含 LA/FRM1/TPIU 前端工作。

| 原输入 | 原窗口 | ETM字节 | 指令记录 | 范围回调 |
|---|---:|---:|---:|---:|
| H743 CDC持续负载 | 1s | 2,176,688 | 18,373,686 | 4,322,285 |
| H743初始化及单次回显 | 2s | 4,847,851 | 36,022,615 | 8,578,894 |
| F103大输入 | 1s | 5,892,279 | 19,565,799 | 19,565,799 |

将原文件重复20/10/20次，模拟20秒输入。生产者按原窗口的**平均字节率均匀投递**，分别约1ms或10ms的数据量一块；不是恢复原始引脚的真实突发时间分布。生产者在独立线程中使用定时器，测量相对于计划释放时间的延迟，因此不会因消费者慢而自动降低长期投递速率。

拼接流与逐个窗口独立结束不是同一输入语义。H743连续20秒的指令数分别为 **367,473,739 / 360,226,195**，不直接用原窗口乘次数当golden；F103为 **391,315,980**。所有接缝都交给完整连续输入基准处理。

## 1倍速结果

主机 Windows / Ryzen 7 PRO 5850U / Python3.13 / GCC16.1.0。每个组合串行跑一次长回放，未隔离整机负载或锁定CPU频率，不称为硬实时或任意负载保证。输入生产者的最大调度迟到约0.6–2.7ms，明细保留于原始结果。

“处理预算比”为 `decodeBusySeconds + snapshotSeconds` 除以已消费输入对应的模拟时长，是工作墙钟分区，**不是CPU利用率**；不包含所有外层队列/拷贝开销。是否积压还要看队列、排空和延迟，不能仅凭这个比值下结论。延迟从该块计划到达时刻算至本次处理/快照完成。

| 输入 / 数据块 | 完整消费 | 处理预算比 | P99延迟 | 最大延迟 | 最后排空 | 队列峰值 |
|---|---|---:|---:|---:|---:|---:|
| H743 1s / 1ms块，持续20s | 是，对拍一致 | 88.9% | 25.9ms | 35.6ms | 2.8ms | 74.4KiB |
| H743 1s / 10ms块，持续20s | 是，对拍一致 | 92.6% | 464.8ms | 479.1ms | 8.7ms | 999.1KiB |
| H743 2s / 1ms块，持续20s | 是，对拍一致 | 90.8% | 277.4ms | 292.3ms | 292.2ms | 646.2KiB |
| H743 2s / 10ms块，持续20s | 是，对拍一致 | 87.7% | 117.2ms | 131.9ms | 15.4ms | 307.7KiB |
| F103 / 1ms块 | **否，队列溢出** | 232.9%（已消费部分） | 不作全流指标 | 约407ms | 未完成 | 约1018.6KiB |
| F103 / 10ms块 | **否，队列溢出** | 237.9%（已消费部分） | 不作全流指标 | 约410ms | 未完成 | 约978.2KiB |

F103两次在约0.74–0.75秒程序时间内失败，分别只消费约0.303/0.290秒的原始输入，不能当作完成20秒。它的范围回调数显著高于H743相近指令规模；这是可观察的工作量差异，还没有用CPU采样定位唯一热点，不能只按MB/s或“已经C++化”推导吞吐。

H743四组没有队列溢出、全部字节消费完毕，累计结果一致；但10ms块的某组接近1MiB队列上限，另有末尾约292ms积压，**这些慢点保留，不筛选成全低延迟**。本轮只证明这些均匀回放负载的有限时长平均吞吐，不证明稳定毫秒级响应或真实板端持续采集。

快照工作集采样：H743 1s两组约17.8–18.8MiB，H743 2s两组约20.8–23.9MiB。Windows这里采样的是WorkingSetSize，不冒充进程峰值；原始fixture、范围字典、累计调用路径和测量数组需要额外内存，1MiB只是输入队列上限，**不是整个进程的内存上限**。

## 快照压力和低速控制

- **H743每10ms生成完整累计analysis JSON**：约1ms输入块，持续20秒，生成1999份快照；处理预算比 **96.1%**，快照生成/hash合计1.295s，P99约50.5ms、最大63.2ms、最后排空2.5ms，队列峰值约131.8KiB。完整消费并与同一个20秒基准一致。相较普通10Hz快照，100Hz已非常接近预算；不包括GUI绘图，不能据此承诺100FPS界面。
- **F103三分之一输入速率**：同样20份1秒fixture，60秒持续投递，599份快照，处理预算比88.7%，P99约122.2ms、最大177.8ms、最后排空5.4ms，完整消费391,315,980条记录，全部累计统计与完整连续输入基准一致。说明流式状态/统计逻辑可工作，1倍速吞吐仍不足。

见 [extra-summary.json](raw/extra-summary.json) 和 [逐次轻量快照](raw/snapshots/)。快照日志含累计指令数、已消费字节、队列/工作集和完整analysis的SHA，统计不断累积，绝非只保留最后1ms/10ms的计数。

## 对拍分层与范围

1. **三份原始记录：独立完整旧算法基准。** 使用原 `BuildVisitor`、原逐条 `Tracker::feed_instruction` 和完整ExecutionFacts恢复PC/状态/周期，再与新增量统计器比较。原完整分析与此前保存的 `decoded.json.analysis` 相同。三组普通流式、两组16KiB真实前缀逐字节投递，均比较完整函数/热点/火焰图/边/周期、每PC累计状态及周期、规范化回调SHA和逐条PC/执行状态/周期SHA，全部相等。状态返回也与此前完整记录相同，lastErrorCode=0。
2. **四秒拼接：独立完整旧算法覆盖接缝。** 三组负载（ETMv3/ETMv4）各自拼成4秒，继续使用完整BuildVisitor/ExecutionFacts基准，与不插入EOT/reset的分块流逐项及两种顺序SHA对拍，覆盖跨原记录接缝的状态。（结果见 `join-oracle-summary.json`。）
3. **二十秒拼接：完整连续字节输入基准。** 将整个拼接文件一次提交OpenCSD，使用已在第1/2层核对的紧凑统计器；避免完整facts/历史store使基准内存与时间膨胀。对三组20秒不规则分块流做完整规范化回调及逐条执行SHA、每PC统计和analysis比较，全部相等。此层验证长流分块/接缝，不冒充独立的20秒完整历史索引对拍。原正常建库会消费的范围/周期/事件/包字段进入回调SHA，不声称对比OpenCSD所有未使用字段。
4. **定时回放：** 四组H74320秒、100Hz压力及F103低速控制的完整累计analysis、全部每PC记录数/成立/未成立/未知/周期、范围/run/event计数与连续基准完全相同。性能组关闭昂贵的逐条调试SHA，顺序SHA在上述独立无节拍回放中核对；没有把不完整的F103过载结果写成一致通过。
5. **原普通建库回归：** 最终源码重新编译的程序，在三个原记录上通过普通离线API各完整建库一次；执行/静态/字符串/包/导航/检查点块原字节、诊断、analysis、语义meta和全部60表与上一轮已验证库一致。见 [default-regression-summary.json](raw/default-regression-summary.json)。这验证旧路径未变，不表示流式阶段生成了60张在线历史查询表。

全套主实验22个进程场景中有两个明确的F103吞吐失败，均保留；输入文件SHA前后不变。用户报告断电/重连后，又核对了证据完整性、原输入SHA和进程状态，没有用重连当作硬件验收。所有本任务服务和原生进程已退出。

## 保留的开发失败与未采用方案

- 初始逐条增量版：H7435秒回放结束仍约66ms积压，处理预算接近100%；首个批量版本10秒测试在消费约7.37秒时填满1MiB队列。随后用范围频次归约、同栈帧批量更新及精确保留首条状态转换，得到上述最终结果。原结果及源码快照在 [pilots](raw/pilots/) / [development-source.tar.gz](raw/development-source.tar.gz)。
- 另试ETMv3单指令缓存：短记录约98%命中，所有短记录对拍字段一致，但1倍速仍约193%的处理预算并溢出。该补丁已撤回最终源码，保留 [补丁](raw/etmv3-cache-experiment.patch)、[控制结果](raw/etmv3-cache-experiment-summary.json) 和试跑JSON；没有把高命中率当成实时能力。
- 首次编译因把系统头放在匿名namespace内失败，修正include位置后构建通过，原日志保留于 [build](raw/build/)。最终两项原生目标构建成功，保留既有编译警告；865个依赖输入核对、三个Python工具py_compile及diff whitespace检查通过。

## 仍未完成

- 真实USB、DDR环形排空、TPIU/FRM1流式前端、实际突发负载、长稳与浏览器绘制未测；没有上板，历史配对/时钟不当作当前板上身份。
- 新原型不保存无限的完整指令历史，不构建在线全量60表，不含滑动时间窗口火焰图UI。累计统计与小窗口显示可以分开，不能将其与离线完整历史数据库的工作量混算为同功能加速。
- 不可变代码镜像是缓存前提；动态代码/目标实时内存没有失效协议。原型单worker/decoder，单次流显式限制4GiB输入；fixture上限256MiB，范围/静态站点有显式上限。已测试重复控制流的工作集稳定，不代表任意新调用路径下全进程内存有固定上限。
- F103 1倍速尚未达到，H743低延迟余量仍小。ZL-006不关闭、不替换固定程序，不宣称Ozone同条件性能。

## 程序身份与复测

实测程序在 [prebuilt/etm-stream-offline-20261104](../etm-offline-research-archive-20261104/README.md#source)，完整SHA及源码/证据身份见 [manifest.json](manifest.json)。逐案大JSON、构建日志和开发源码快照已无损压缩；[archive-index.json](raw/archive-index.json)记录解压后的SHA/大小，轻量汇总和快照日志保持可直接阅读。内嵌buildSha是旧build目录配置时HEAD `41e2cee`，本次源码为 `41ec0e2` 加列明的stream改动；不能用内嵌值冒充源码无修改。保留实测原字节；提交前重新编译的另一组字节用于普通建库回归，身份另记，未替换实测证据。

在本worktree根目录执行，输出目录必须新建。`--source-root`指向仍保留上述原始输入的主目录。默认实验缓存关闭，工具仅在各自离线子进程中开启。

```powershell
python -X utf8 tools/bench_etm_streaming.py --help
python -X utf8 tools/bench_etm_streaming.py --source-root E:/zynqlinkPRO --binary prebuilt/etm-stream-offline-20261104/etm_storebuild.exe --out build/stream-new --duration 20
python -X utf8 tools/check_etm_streaming_scenarios.py --source-root E:/zynqlinkPRO --binary prebuilt/etm-stream-offline-20261104/etm_storebuild.exe --campaign build/stream-new --out build/stream-extra-new
python -X utf8 tools/check_etm_streaming_scenarios.py --source-root E:/zynqlinkPRO --binary prebuilt/etm-stream-offline-20261104/etm_storebuild.exe --campaign build/stream-new --out build/stream-joins-new --joins-only
cmake --build build/block-cache-native --target etm_decode etm_storebuild --parallel 4
python -X utf8 tools/check_etm_streaming_default.py --source-root E:/zynqlinkPRO --binary build/block-cache-native/etm_storebuild.exe --previous-campaign build/block-cache-ab --out build/stream-default-new
```

源码重新构建的CMake配置参数沿用[上一轮报告](../etm-block-cache-20261104/README.md)。原始工作目录 `build/stream-*` 保留；未整体提交build、运行令牌或服务日志中的鉴权URL。未推送。
