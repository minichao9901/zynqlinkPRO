# ZL-006：ETM 离线处理分阶段耗时

日期：2026-11-03（Asia/Shanghai）。按用户要求先测量，再决定迁移范围；本轮没有修改生产算法、增加热路径计时、重建原生程序或替换固定 EXE，没有硬件访问。测量代码为优化分支 `codex/etm-cpp-stage1` 的 `a1d805d`，C++ 程序仍为 `77bf1c2` 源码构建的已交付字节。主机 AMD Ryzen 7 PRO 5850U，软件和文件 SHA 见 [provenance.json](raw/provenance.json)。

结论：**优先优化完整查询索引，其次继续分析 C++ 重放/建库；目前不值得先整体迁移静态字典。** Python 并非仅剩接口，但 Python 静态准备不是主要瓶颈。没有在本轮据此启动重构。

## 方法与计时范围

使用现有 `tools/bench_etm_native_offline.py`，三组真实保存记录分别启动一个新的离线服务进程，每组连续三次、每次新建记录，从 raw + ELF 重建，保留默认单次 OpenCSD + typed replay、完整索引、全部诊断、输入 SHA/变化检查、输出 CRC/SHA。只串行测速，结束后停止本任务服务；完整语义比较在计时全部结束后运行。

API 总时间为 POST decode 到任务 done，包含任务准备、解码/建库/索引、发布及服务端浏览准备，排除测试输入复制、服务启动、硬件采集/下载、上传、浏览器绘制及实际首屏。原始输入已经是 ETM BIN，不包含 LA 波形提取或 TPIU 解复用。每组首轮 ELF/地址应用缓存未命中，后两轮命中；没有清 OS 文件缓存，不能叫冷盘测试。未施加 CPU/磁盘隔离，因此保留调度及运行时波动。

输入保持固定，三个协议配置与 ELF 不混用：

| 输入 | 协议 / 原记录窗口 | ETM 字节 | 恢复指令 | 唯一 PC | 原有 gap / 未知执行 |
|---|---|---:|---:|---:|---:|
| F103 大输入 | ETMv3 / 1s | 5,892,279 | 19,565,799 | 642 | 2 / 522,998 |
| H743 CDC 持续负载 | ETMv4 / 1s | 2,176,688 | 18,373,686 | 1,403 | 1 / 8,759 |
| H743 初始化及单次回显 | ETMv4 / 2s | 4,847,851 | 36,022,615 | 4,042 | 1 / 1,139 |

F103 输入为 `docs/validation/zl006-cpp-stage1-20261102/f103-large-input`；H743 1s 为 `docs/validation/h743-comprehensive-20261101/raw/etm20-4ms-matrix/1000ms-1`。H743 2s 实际使用已有 `build/stage2-h743-2s/direct` 的 raw/ELF/配置/源码复制成仅输入 seed（未复制 store/native）；其 capture、ELF、sources SHA 与版本管理的 `docs/validation/h743-flame-20261102/raw/corrected/record` 逐项一致，后者可用于复测。实际路径及完整输入 SHA 均保留在原始结果中。H743 两组负载不同，不能只按窗口倍数推断线性扩展。

## API 总耗时

单位：秒。三轮全部成功，未筛选较快轮次。

| 输入 | 第 1 轮 | 第 2 轮 | 第 3 轮 | 三轮中位数 |
|---|---:|---:|---:|---:|
| F103 大输入 | 9.725 | 8.762 | 9.745 | **9.725** |
| H743 1s | 5.884 | 5.507 | 5.667 | **5.667** |
| H743 2s | 12.444 | 11.861 | 11.623 | **11.861** |

F103 第 3 轮缓存命中仍较慢：C++ 解码/缓存准备为 2.011s，而前两轮为 1.673/1.635s；未归因为已定位的代码回归。本轮 F103 中位数高于上轮的 8.880s，两轮没有同期隔离 A/B，不能据此断言固定幅度退化或把不同轮次混算。历史首轮超过 10s 的证据仍有效，且 H743 2s 本轮三次均超过 10s，ZL-006 继续部分解决。

## 分阶段耗时

下表为**各阶段分别取三轮中位数**，因此各列相加不必等于 API 中位数。每一轮的分区均可准确加回该轮 API 总时间；公式与逐轮明细见 [summary.json](raw/summary.json) 和 [summarize.py](summarize.py)。这是墙钟耗时分区，不是按语言独占 CPU 采样。

| 阶段 | 实现及范围 | F103 大输入 | H743 1s | H743 2s |
|---|---|---:|---:|---:|
| ELF/源码映射准备 | Python 调用层及底层库，包含缓存读取/哈希 | 0.012 | 0.011 | 0.013 |
| 协议解码和 RAM 缓存准备 | C++ OpenCSD、范围去重、缓存写入及其输入校验 | 1.673 | 1.109 | 2.297 |
| 静态指令字典准备 | Python，调用 Capstone 原生反汇编 | 0.051 | 0.110 | 0.413 |
| 原生建库及包装层 | C++ 重放、执行流/栈/路径、facts、核心 store 写出，含 Python 等待/结果检查 | 3.471 | 2.051 | 3.807 |
| 完整查询索引 | Python + NumPy、facts 读取、完整查询表、默认视图、索引编码 | **2.308** | **1.710** | **4.520** |
| 最终封装与发布 | Python 调用层：summary、诊断、复制块、组装、输入绑定、发布、清理 | 0.873 | 0.309 | 0.546 |
| 其他及未归属 | import、进程启动/退出、握手、任务/API 调度及未单独计时工作等残差 | 0.720 | 0.289 | 0.389 |

首次 ELF 准备为 0.165 / 0.184 / 0.200s；首次静态字典为 0.125 / 0.195 / 0.456s。缓存后的静态准备仍需反汇编/机器码和源码位置交叉核对，未跳过验证。原生建库包装阶段不是“全部为 C++ CPU”，其他残差也不能直接当作 Python 算法耗时。

索引的进一步拆分同样按各子阶段分别取中位数：

| 查询索引子阶段 | F103 大输入 | H743 1s | H743 2s |
|---|---:|---:|---:|
| 查询表构建/归约与布局（tablesSeconds） | 0.788 | 0.630 | 1.593 |
| 默认窗口/时间线视图及 JSON | 0.708 | 0.403 | 1.267 |
| 索引编码/压缩 | 0.667 | 0.550 | 1.322 |
| facts 读取、core 打开及其他索引工作 | 0.145 | 0.124 | 0.299 |

C++ 内部非独占计时：重放与 visitor.finish (`readNative`) 中位约 2.109 / 1.259 / 2.554s；核心 store 写出 (`writeBlocks`) 约 0.834 / 0.596 / 0.742s；原生索引 facts 归约及输出 (`queryIndex`) 约 0.159 / 0.136 / 0.420s。`readNative=assemble`、`writeBlocks=assembleFile` 是同一计时的别名；buildBlocks 在 readNative 内，当前 online facts 输出在原生 queryIndex 内，不能全部相加。`hashFile=0` 表示没有独立该计时段，不代表输出哈希被关闭。C++ 本轮未开启逐记录 `--profile`，避免热路径每条计时干扰；不能据此精确分配 tracker、运行编码与内存访问的比例。

## 对后续优化的判断

1. 查询索引约占三组 API 中位耗时的 24% / 30% / 38%，是剩余 Python 数据路径中最值得优先处理的部分。表构建、默认视图和编码都明显耗时，不能只把 NumPy 循环改写成 C++ 就假定全部消失。应评估让 C++ producer 直接产出最终表、减少 facts 中间传输/重复遍历，并对默认视图及压缩分别做保真 A/B。
2. 原生解码/缓存加建库包装约 5.14 / 3.16 / 6.10s，C++ 仍占较大部分。要把 F103 进一步压向 5s，仅迁移静态准备或只减少 Web 调度明显不够；还需要分析 C++ 重放/执行流处理及写库成本。这些数值含包装层，不能声称全部都是 C++ 的可优化 CPU 时间。
3. 静态字典热缓存仅约 0.05 / 0.11 / 0.41s；即使假设整段耗时降为零，节省也有此上限，真实迁移收益会更小。整体迁移 ELF/DWARF/反汇编可用于接口简化或部署目标，现有测速不支持把它排在性能优化首位。
4. 最终封装在 F103 约 0.87s，其中复制/重新压缩块约 0.52s、最终 assemble 约 0.12s；H743 两组较小。可作为索引之后的优化项，但输入哈希、CRC、故障诊断和发布原子性必须保留。`inputBindings` 约 0.014～0.022s 只代表最终输入绑定段，不是全链路完整性校验总成本。

以上是范围选择建议，没有给出未测的迁移加速承诺，也没有与 J-Trace/Ozone 做同期同条件对比。

## 一致性与证据范围

- 九次 API job 均 done，逐轮完整 summary 及双方共有 quality 字段与输入记录一致，无逐指令 JSONL，默认 direct/replay 路径未生成 native.bin。
- 每组选择 API 墙钟中位数的实际轮次，在测速结束后对全部执行/静态/包/导航/检查点块逐字节比较，完整 analysis、展开诊断及 60 张查询表全部相等；没有声称其余六轮也逐块完成同一验证。见 [F103](raw/f103-api-equivalence.json)、[H743 1s](raw/h743-api-equivalence.json)、[H743 2s](raw/h743-2s-api-equivalence.json)。F103 对照上轮已验证候选，H743 1s 对照上轮 main 原生建库，H743 2s 对照已验证的 stage2 direct 库；本轮未重新建立 main 性能 A/B。
- 首次尝试对照 H743 综合报告中的 store，其 manifest 引用的 generation 文件缺失，比较工具退出失败。发生于计时之外，未作为一次解码性能失败或产品执行流差异；改用上轮 ZL-107 套件保留的完整 main 库，核对 raw/ELF SHA 后完成全量比较。[原失败与替代路径](raw/reference-resolution.json)保留，不冒充缺失基准已恢复。
- 原有 gap、未知执行及周期能力边界保留，结果一致不等于证明物理采集无损或绝对解码正确。CPU/HCLK/TRACECLK 沿用保存记录的历史身份，本轮没有核查当前板上状态。
- [validation.json](raw/validation.json)记录输入不变、默认处理策略、完整性绑定、原生程序身份及服务退出。本轮仅测量和归档，不重跑无关硬件/冻结包验收，不更新用户固定程序。

原始三轮：[F103](raw/f103-api.json)、[H743 1s](raw/h743-api.json)、[H743 2s](raw/h743-2s-api.json)。原始工作目录 `build/phase-profile-20261103/` 保留，不纳入整体提交；令牌/runtime 文件未归档。

## 复测

在上述优化提交的 worktree 内串行运行，三个输出目录必须新建，端口须空闲；每组出现 `OFFLINE_BENCH_READY` 后用 Ctrl+C 停止本任务进程，再运行下一组。Ctrl+C 的退出码不是 decode job 的结果，具体以 results JSON 为准。

```powershell
python -X utf8 tools/bench_etm_native_offline.py --record docs/validation/zl006-cpp-stage1-20261102/f103-large-input --out build/phase-f103-new --port 8903 --repeat 3
python -X utf8 tools/bench_etm_native_offline.py --record docs/validation/h743-comprehensive-20261101/raw/etm20-4ms-matrix/1000ms-1 --out build/phase-h743-new --port 8903 --repeat 3
python -X utf8 tools/bench_etm_native_offline.py --record docs/validation/h743-flame-20261102/raw/corrected/record --out build/phase-h743-2s-new --port 8903 --repeat 3
python -X utf8 docs/validation/etm-phase-profile-20261103/summarize.py --input f103=docs/validation/etm-phase-profile-20261103/raw/f103-api.json --input h743-1s=docs/validation/etm-phase-profile-20261103/raw/h743-api.json --input h743-2s=docs/validation/etm-phase-profile-20261103/raw/h743-2s-api.json --out build/phase-summary-new.json
```

三组测量服务均已退出，无本任务后台 worker；源码优化分支及固定 EXE 的集成范围保持不变，未推送。
