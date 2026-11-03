# ZL-006：C++ 完整索引与最终建库迁移

日期：2026-11-03（Asia/Shanghai）。按用户要求完成默认解码构建链的完整索引和最终 store 迁移，在独立 worktree `E:/zynqlinkPRO-work/etm-cpp-stage1-20261102`、分支 `codex/etm-cpp-stage1` 验证。没有访问硬件或改变 PL/PS、MCU 时钟/Flash/QSPI，没有替换固定 `dist/zynq-etm-bridge/`。main 只同步报告和问题索引，生产实现尚未合并。

实现源码 **d39965b**，配套 `etm_storebuild.exe` 及构建身份 **48e4d3d**，冻结包构建/许可证收录提交 **5b75131**。同批三轮离线 API，中位时间 F103 **10.507 → 6.809s（减少35.2%）**、H743 1s **5.673 → 5.003s（11.8%）**、H743 2s **11.487 → 9.665s（15.9%）**。九轮新输出全部逐块/逐表对照一致。H743 2s 新首轮 **12.002s**，不能宣称每轮都低于10s或获得持续实时能力。[源码/原生程序/冻结包身份](build-manifest.json)、[性能汇总](raw/performance-summary.json)、[全部九轮对照](raw/api-equivalence-all.json)。

## 实现与数据边界

默认链路为：`raw ETM → C++单次OpenCSD/缓存 → Python唯一代码静态字典 → 同一C++进程重放/完整索引/诊断/最终store → Python输入绑定和manifest原子发布`。

- `native/full_index.hpp` 在内存中的 ExecutionFacts 上生成全部 **60张语义表**及 `meta_json`，包含 cell/hotspot、函数/路径区间、事件、PC/源码行导航、调用配对、未知/未成立序号、周期锚点、节点 include/self 及周期聚合。查询字符串池、函数ID、dtype、shape、顺序保持既有合同。
- 全段默认窗口和函数时间线也在 C++ 生成，保留两张默认 JSON 表的原字节表示、UTF-8、字段顺序、分隔符和浮点格式。索引容器继续为 `ETMQIDX2`，四线程分表 zlib level1，逐表 CRC；没有换成不等价的简化视图或删除查询表。
- `native/complete_store.hpp` 生成质量计数、summary、紧凑诊断和最终 meta/sources 块。谓词诊断直接写数值三元组，避免构建/复制大量 JSON 对象。大规模诊断数组保存在最终库，不再重复返回 Python；仍可完整展开查询。本轮控制结果约 F103 **61.8KB**、H743 1s **100.3KB**、H743 2s **279.0KB**，没有跨语言传输执行 facts/查询数组。
- C++ 一次写出包含核心执行块、诊断和完整索引的最终 `store.bin`，执行块/JSON压缩、header/index/块 CRC 和整库 SHA 保留，写临时文件后 flush/`_commit`（POSIX为fsync）再 rename。既有 `required_features=2`（紧凑诊断）和 `optional_features=1`（索引）保持不变。
- `tools/native_complete.py` 只准备静态上下文、校验最终文件 SHA/特性位/meta、核对实际输入绑定、写记录元数据及原子发布 manifest。默认路径不调用 Python facts 读取、NumPy 完整索引或 `_BlockSink.assemble`，不产生 facts.bin/index-facts.bin/publish.payload，也不先写核心 store 再由 Python 重封装。验证工具实际把这些 Python 数据函数替换为抛错来检查。
- Python 当前继续承担 ELF/DWARF/静态字典、Web/CLI 调度、记录身份与发布；查询读取/既有 reindex 等路径仍保留。研发显式 `ETM_COMPLETE_INDEX=0` 使用旧 facts/NumPy 索引对照，缺少 `complete-index-v1` 的程序明确拒绝默认新路径，不静默回退。本阶段完成的是默认解码建库链，不是整个产品所有组件的 C++ 迁移。

原有单次解码 RAM 编码缓存上限1GiB，仍非整个进程内存上限；完整索引和执行 facts 需要额外内存。这仍是有限窗口离线处理。完整索引对总执行序号做 int32 范围检查，超限明确失败。

## 同期性能对照

旧版本固定为独立只读 worktree `E:/zynqlinkPRO-work/etm-index-reference-20261103` 的 **b03275a**，未改动其应用代码/原生程序。新版本测速时为 **48e4d3d**，使用源码 d39965b 对应程序；后续5b75131只把新增JSON库的许可证加入冻结包，不改运行中的解码算法。两边生产源文件/EXE指纹由 manifest 及 Git 身份绑定。

每个输入、每个实现单独启动新服务进程，连续三轮，每轮新建记录，从 raw+同一目标ELF重建，输入复制在计时之外。六组均串行，不与本任务编译或其它测速并行；旧F103首轮记录创建时间晚于最终编译完成时间。操作系统文件缓存未清，首轮应用ELF/地址缓存未命中，后两轮命中，不是冷盘保证。主机仍为 AMD Ryzen 7 PRO 5850U / Windows / Python3.13，环境未施加CPU/磁盘隔离，不把波动归为已定位根因。

计时为 POST decode 到 job done，包含任务准备、解码、完整建库/索引、输入校验、发布和服务端浏览准备；不含硬件采集/下载、上传、服务启动、浏览器绘制或实际首屏。完成重建不等于原始trace无gap或质量全绿。

| 固定输入 | 指令数 | 旧版本三轮(s) | C++完整建库三轮(s) | 中位数旧→新(s) | 中位减少 |
|---|---:|---|---|---|---:|
| F103 ETMv3 / 1s | 19,565,799 | 10.507 / 9.687 / 11.829 | 6.809 / 6.819 / 6.515 | **10.507 → 6.809** | 35.2% |
| H743 ETMv4 / CDC持续负载1s | 18,373,686 | 6.081 / 5.673 / 5.640 | 5.293 / 4.849 / 5.003 | **5.673 → 5.003** | 11.8% |
| H743 ETMv4 / 初始化及单次回显2s | 36,022,615 | 11.737 / 11.487 / 11.379 | 12.002 / 9.329 / 9.665 | **11.487 → 9.665** | 15.9% |

原始结果：[旧F103](raw/api-reference-f103.json)、[新F103](raw/api-cpp-f103.json)、[旧H743 1s](raw/api-reference-h743-1s.json)、[新H743 1s](raw/api-cpp-h743-1s.json)、[旧H743 2s](raw/api-reference-h743-2s.json)、[新H743 2s](raw/api-cpp-h743-2s.json)。完整输入 SHA 在这些文件及汇总中；F103 raw为 `3b549953…ea78`，H743 1s为 `974e5c2c…f2b9`，H743 2s为 `3bb82c46…50b6`，与此前已保存记录一致。

索引内部计时（分别取三轮中位数，不含最终store写入，不把嵌套计时重复相加）：

| 项目 | F103 旧→新(s) | H743 1s 旧→新(s) | H743 2s 旧→新(s) |
|---|---|---|---|
| 完整索引总计 | **2.378 → 1.018** | **1.631 → 0.991** | **4.128 → 2.298** |
| 表构造/归约及布局 | 0.878 → 0.486 | 0.665 → 0.483 | 1.530 → 0.965 |
| 默认窗口/时间线JSON | 0.766 → 0.053 | 0.410 → 0.061 | 1.245 → 0.121 |
| 索引编码/压缩 | 0.804 → 0.488 | 0.553 → 0.443 | 1.312 → 1.229 |

F103还减少了诊断数组回传和重复封装。H743 2s的新首轮协议/缓存准备2.517s、重放/finish3.821s、索引总计2.498s，后两轮对应阶段更快；保留12.002s而不删除。C++索引之后，重放/写库及大输入压缩仍明显耗时；全C++迁移本身不是5s或J-Trace/Ozone同等E2E的证明。

## 正确性与失败路径

- **全部18个API任务完成**；旧/新每个对应轮次 summary 和共有 quality 完全一致，原始输入前后SHA不变。**全部九个新结果**对对应旧结果的静态/字符串/完整执行流/包/导航/聚合/检查点块逐字节比较，完整 analysis、展开诊断、全部60表逐项一致。默认视图JSON也按字节比较。查询字符串池、函数映射、导航合同、覆盖范围和默认视图SHA等语义meta一致，仅忽略明确不同的producer标签 `source`。逐轮证据在 [汇总](raw/api-equivalence-all.json)及同目录 `api-equivalence-*-r*.json`，不是抽样首屏检查。
- F103原有 **2 gap / 522998未知执行**，H743 1s为 **1 / 8759**，H743 2s为 **1 / 1139** 均保留。有限输入对照共用OpenCSD，不能给出绝对正确率或证明物理采集完整；目标时钟沿用记录的历史身份，本轮没有核查当前板上状态。
- [F103尾部截断2字节](raw/truncated-f103.json)与[H743尾部截断2字节](raw/truncated-h743.json)均在相同变体输入上通过完整差分，不把变体当原始完整采集；这些功能对照与冻结构建可并行，内部seconds不计入上述正式串行API性能表。
- F103与H743都先用未迁移的main生成真实旧记录，再做同目录升级、binary/direct/rescan切换、重复重建、五类真输入变更（ETM/ELF/config/image/已消费native）注入及未消费native变更。实际输入变更均拒绝发布并保持旧manifest/decoded；旧native原字节保留。每协议11个控制场景，源码和5个成功重建场景的完整数据比较见 [F103](raw/upgrade-f103/result.json)、[H743](raw/upgrade-h743/result.json)；各子JSON保留拒绝原因/变更已施加/旧发布未变的证据。
- **23项针对性测试 + 55项CLI（共78项）通过**：[针对性](raw/targeted-tests.log)、[CLI](raw/cli-tests.log)。新增六项包括禁止Python数据写入、manifest失败恢复、发布后清理失败保留已提交代、同长度最终库损坏拒绝、10008个浮点/Unicode JSON格式对照、仅native输入记录的正确processed字节数。保留既有ResourceWarning；没有为文档重跑硬件。
- 原生 [SHA/共享状态5万步/7万唯一范围缓存自检](raw/native-self-tests.json)通过。新浮点格式测试开发期首轮失败 `115336699991782588416.0` 对 `1.1533669999178259e+20`，已改为最短科学形式加Python格式阈值，最终10008值通过；[原失败](raw/dev-json-format-failure.json)保留，不冒充从未失败。
- 区间CSV导出在F103大记录/H743 2s的新旧库间逐字节一致；冻结程序的两协议CSV也与源码CLI一致：[CSV证据](raw/csv-equivalence.json)。

## 冻结程序与交付身份

候选目录 `build/etm-complete-index-bridge/`，`sourceRevision=5b75131`、`sourceDirty=false`。builder内嵌源码d39965b，SHA与Git中交付程序相同；decoder/exporter保留77bf1c2对应的原字节。本轮只重建主机builder和冻结应用，不涉及bit/PS ELF。[精确EXE/包清单SHA](build-manifest.json)。新增固定版本 nlohmann-json 3.11.3（MIT）源码/许可证及上游发布SHA已纳入Git，冻结包也含许可证；494项依赖离线指纹核对通过。

- [冻结包标准验收](raw/frozen-standard-verification.json)：PATH无系统Python/Node，两协议导入/重建、Web/CLI查询与HTML导出、SVG、重复启动复用通过；硬件接口禁用，服务已退出。该报告package路径是发布前临时候选路径，实际发布候选由同一EXE/包清单SHA绑定，不把已清理的临时目录当作运行中服务。
- 实际冻结Web入口对main旧[F103](raw/frozen-upgrade-f103.json)/[H743](raw/frozen-upgrade-h743.json)原地重建通过，旧native保留、全量语义与60表一致。标准F103为5467740指令/H743为210497指令；额外旧记录升级为F103550478指令/H74318373686指令，不能把它们计作上述大输入性能轮次。
- [冻结默认链核对](raw/frozen-pipeline-check.json)直接检查两份新manifest均为 `native-complete-index`、不写scratch facts、单次最终store写出，许可证存在。冻结CLI导出验证见CSV证据。

## 保留的问题与范围

ZL-006继续**部分解决**：本阶段完整索引/最终建库迁移及固定记录正确性验证完成，Python静态准备/查询读取等后续迁移、冷盘、持续实时、真实硬件Web E2E及每轮≤10s均未由本报告证明。没有修改目标时钟或缩小执行/诊断信息来换时间。

新增 **ZL-117 / P3待修复** 为本轮审计发现的既有问题：旧原生 `meta.record.protocol` 固定ETMv4，即使F103的实际config/decoded为ETMv3，错误包说明可能用ETMv4名字。本迁移为保持差分合同保留该标签/诊断命名行为，真实协议解码继续按实际配置；本轮正常输入包错误均0。[旧/新实测标签](raw/legacy-protocol-label.json)保留，需另做双协议错误包标签修正，不能称其已关闭。ZL-107原输入身份修复在新发布路径及冻结包中继续通过。

## 复测入口

固定输入路径与[分阶段测速报告](../etm-phase-profile-20261103/README.md)相同。在优化worktree执行：

```powershell
python -X utf8 tools/validate_etm_complete_index.py --record docs/validation/zl006-cpp-stage1-20261102/f103-large-input --out build/full-index-f103-new
python -X utf8 tools/validate_etm_complete_index.py --record docs/validation/h743-comprehensive-20261101/raw/etm20-4ms-matrix/1000ms-1 --out build/full-index-h743-new
python -X utf8 tools/validate_etm_complete_index.py --record docs/validation/h743-flame-20261102/raw/corrected/record --out build/full-index-h743-2s-new
python -X utf8 tools/bench_etm_native_offline.py --record docs/validation/zl006-cpp-stage1-20261102/f103-large-input --out build/full-index-api-new --port 8904 --repeat 3 --complete-index 1
python -X utf8 docs/validation/etm-complete-index-20261103/summarize.py
```

单次差分在同一进程先旧后新，第二次应用缓存可能命中，其seconds只用于功能检查；正式A/B使用分开的b03275a/48e4d3d服务进程与三轮API结果。基准出现 `OFFLINE_BENCH_READY` 后停止自己的进程再测下一组；Ctrl+C退出码不等于decode任务失败。复测输出目录必须新建，端口须空闲，不能借用其它运行服务。

工作输出 `build/cpp-full-index-20261103/` 和两个main下的升级夹具目录保留，未批量纳入Git；运行时令牌/URL不归档。[最终检查](raw/validation.json)记录进程退出和身份核对。所有本任务服务/worker均已结束，未合并生产代码至main、未替换固定EXE、未推送。
