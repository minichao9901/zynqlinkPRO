# DeepSeek / Ozone 解码资料评估与离线基本块缓存实验

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

> **main归档说明（2026-11-04）：用户暂不采纳，相关研究暂停。** 本目录仅同步历史文档与证据，候选源码、工具和EXE未并入main。原worktree/运行目录为当时路径，已按本次归档流程移除；不可据其描述推断当前main能力或当前板上身份。完整研究树及程序保留在Git tag `archive/etm-offline-research-20261104`（`0732f67`），取回方法与状态见[归档索引](../etm-offline-research-archive-20261104/README.md)。原实验分支的ETM写文件问题号“ZL-132”与main HAL问题重号，main中改用 **ZL-143**；原始JSON、manifest与历史正文保留原编号。

日期：2026-11-04（Asia/Shanghai）。问题：ZL-006；附带发现 ZL-132。独立 worktree `E:/zynqlinkPRO-work/etm-block-cache-20261104`，分支 `codex/etm-block-cache-20261104`，基于 `41e2cee`。全程离线，没有访问板卡，没有修改 PL/PS、目标程序/时钟/Flash/QSPI，没有合入 main 或替换固定 EXE。

结论：**资料适合作为设计检查清单，不能作为可靠的 ETMv4 协议实现；基本块缓存有可测收益，但不是整体 5–10 倍。** 本轮在 OpenCSD 逐指令走查处补做缓存，H743 完整离线处理缩短约 15%–17%，解码准备阶段约 2.2 倍；F103 没有获益。保留默认关闭的实验实现和实测程序，不作为产品验收或商业 Ozone 对照。

## 资料与现有方案

原始资料在 reference（历史目录：`archive/main-before-cleanup-20261105:docs/validation/etm-block-cache-20261104/reference`，按验收索引恢复），逐文件 SHA 见 [manifest.json](manifest.json)。来源是用户指定的 `E:/ozone_disc/etraced/docs/`，只作为评估材料；没有执行其中的操作指令或采用其排期/性能数字作为实测结论。

| 资料建议 | 当前主线 / 判断 |
|---|---|
| C++ 协议/展开/存储核心，Python 做接口 | 主线已经具备，不能再次把 Python→C++ 的收益算成本轮收益。 |
| OpenCSD 对拍 | 主线直接采用固定 OpenCSD 1.8.3 解析协议；本轮保留同一解析器，只缓存确定的代码走查结果。 |
| 静态指令/分支目标预计算、范围缓存 | 主线 `BuildVisitor::range_entries` 已缓存字典指针、地址增量及谓词计数，`ReplayCache` 已去重范围并单次重放；重写整个 L3 价值有限。 |
| 基本块缓存 | OpenCSD ETMv4 的 `traceInstrToWP` 仍对每次出现的范围逐条读代码/分类。此处有尚未覆盖的重复工作，值得做小实验。 |
| 有界队列、背压、多线程流水 | 适合未来连续流设计；无法让已输出且不可暂停的 ETM 引脚因主机背压而停下来，仍需硬件缓冲/明确丢失边界。未改本次离线链路。 |
| 最近 1000 万条环形保存、逐条地址数组 | 与现有保留完整窗口、包/诊断/路径/索引的工作量不同。截短或省略索引再比较会失真，本轮没有采用。 |
| 5–10 倍缓存收益、100 MB/s、480 M inst/s 等 | 材料没有同输入、同输出合同的基准证据，不能推导 Ozone 或当前产品性能。 |

资料中有不能照抄的协议细节：

- `header >> 2` 的 64 项分派并丢弃低两位非零字节，会丢弃合法 ETMv4 包。例如 OpenCSD 明确把 `0xF6/0xF7` 都解析为 Atom F1，短地址还包含 `0x95/0x96`。见仓库 `trc_pkt_proc_etmv4i.cpp::BuildIPacketTable`，也可核对 [OpenCSD 上游实现](https://github.com/Linaro/OpenCSD/blob/master/decoder/source/etmv4/trc_pkt_proc_etmv4i.cpp)。无法由材料所列的无版本二进制地址确认它实际描述的是 raw ETM 还是私有中间格式。
- `new_addr=(payload<<1) XOR last_addr` 不是通用 ETMv4 地址解压规则。实际短地址更新按有效位掩码覆盖低位，IS0/IS1 对齐不同，并存在完整地址、地址历史精确匹配等包型；见 `trc_pkt_elem_etmv4i.h::updateShortAddress` / `extractShortAddr`。
- 单一 `commit_idx` 回滚、通用“五字节 varint”、异常读向量表、时间戳一律周期增量等，不能替代按协议/配置处理投机深度、条件执行、异常和时间包。材料没有完整的协议层与真实流对拍证据。

因此保留 OpenCSD，不按这份伪代码另写协议解码器，也不声称复制了 SEGGER/Ozone 的私有算法。

## 实验实现与边界

两个 OpenCSD 文件增加每个 decoder 独立的 4096 槽直接映射缓存。只缓存普通 `traceInstrToWP` 成功到达 waypoint 的走查；命中后恢复完整末尾指令状态、范围终点和指令计数，后续 atom/异常/投机提交、输出回调全部仍由原代码执行。按地址索引槽，再核对完整输入 `ocsd_instr_info`（含 ISA、IT 状态及保留字段）、memory space、ContextID、VMID；decoder reset 时失效。异常/Q 的地址匹配走查、NACC 和错误不缓存。范围限制不变。

默认关闭，只有环境变量 `ETM_EXPERIMENT_IMMUTABLE_BLOCK_CACHE=1` 启用。**前提是同一 decoder 生命周期内代码镜像固定且内存读取没有副作用**；本机封闭离线解码器把文件读为不可变 buffer，满足此前提。没有为动态代码、自修改代码、实时目标内存或其它 OpenCSD 嵌入方建立失效协议，不能把此实验直接推广到这些场景。完整输入结构的字节比较很保守，padding 或保留字段不同至多导致缓存未命中。

[实测 host 程序](../etm-offline-research-archive-20261104/README.md#source) 与源文件 SHA 见 manifest。编译使用 GCC 16.1.0、CMake Release；程序内 `buildSha` 为配置时 base HEAD，源码当时带两个已记录的修改，**不能把内嵌 base HEAD 当成未修改源码构建的证明**。实测程序字节原样保留，没有用另一轮重建替换证据。

## 同程序开关 A/B

主机 Ryzen 7 PRO 5850U / Windows / Python 3.13。每组一个新服务，按 `0,1,1,0,0,1` 串行执行六轮，每轮新建记录，从保存 raw + ELF + sources 重建完整 store。只串行运行本任务的测速；没有隔离整机其它负载，也没有清 OS 文件缓存，不能称为冷盘测试。首次慢轮全部保留，中位数含首轮。

计时是 API POST decode 至 job done，包含 OpenCSD、重放/分析、60 表完整索引、默认视图、压缩、输入校验、发布和服务端浏览准备。排除硬件采集/下载、上传、服务启动和浏览器绘制/真实首屏。baseline 是**同一实测 EXE 关闭新增缓存**，对应原有算法，不是较早 Python 版本；另外以未修改 main EXE 做 prescan 语义核对。

| 保存输入 | 指令数 | 关闭三轮 (s) | 开启三轮 (s) | 中位关闭→开启 (s) | 中位缩短 |
|---|---:|---|---|---|---:|
| H743 ETMv4 1s | 18,373,686 | 7.459 / 4.501 / 4.401 | 3.919 / 3.818 / 3.801 | **4.501 → 3.818** | **15.17%** |
| H743 ETMv4 2s | 36,022,615 | 8.355 / 8.493 / 8.481 | 7.172 / 7.060 / 6.986 | **8.481 → 7.060** | **16.76%** |
| F103 ETMv3 1s（控制） | 19,565,799 | 6.914 / 8.802 / 6.745 | 7.083 / 7.856 / 6.674 | **6.914 → 7.083** | **−2.44%** |

F103 不走新增缓存，其波动不证明有性能收益或已定位回归。H743 单组各三次的结果支持这两个输入的离线改进，不能证明所有固件/所有机器的固定百分比。

解码准备阶段 `preparedDecode.seconds` 三轮中位数（包括单次 OpenCSD/范围去重/typed cache 准备，并非纯指令分类 CPU）：

| 输入 | 关闭 (s) | 开启 (s) | 关闭/开启 |
|---|---:|---:|---:|
| H743 1s | 1.154920 | 0.528191 | 2.19× |
| H743 2s | 2.194560 | 0.987166 | 2.22× |
| F103 1s | 1.791100 | 1.820530 | 0.98× |

完整输入 prescan 的独立命中诊断：H743 1s 命中 4,300,971 / 未命中 20,415，跳过 18,280,090 条逐条走查；H743 2s 命中 8,569,778 / 未命中 7,493，跳过 35,988,283 条走查（均超过99%命中）。缓存本身有界，但完整建库仍有 facts/index/replay 内存；两组开启缓存的 decode 准备峰值 RSS 约 359 MiB / 744 MiB，**不是低内存流式解码验收**。大部分剩余耗时仍在重放/执行流分析、索引和压缩/写库，因此局部 2.2× 不会成为总体 2.2×。

原始 汇总（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-block-cache-20261104/raw/summary.json`）、H743 1s（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-block-cache-20261104/raw/h743-1s-api.json`）、H743 2s（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-block-cache-20261104/raw/h743-2s-api.json`）、F103（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-block-cache-20261104/raw/f103-1s-api.json`）。输入路径与完整 SHA 均记录其中。

## 一致性、失败及边界

- 18 个 API job 全部 done；每轮 summary 和双方共有 quality 与保存记录相同，所有原始输入前后 SHA 不变。F103 原有 2 gap / 522998 未知执行、H743 1s 1 / 8759、H743 2s 1 / 1139 保留，没有把缓存命中等同采集无损。
- **九组开关配对全部**比较完整执行/静态/字符串/包/导航/检查点块原始字节、完整 analysis、展开诊断、语义查询 meta 和全部60张查询表，全部通过；比较在所有计时结束后运行，逐组证据在 raw 的 `*-equivalence-*.json`，不是首屏抽样。
- 三份真实完整输入及各自尾部减2字节的变体，对未修改 main EXE、新程序关闭/开启共18次 prescan；完整语义计数、唯一范围与输入 SHA 一致，忽略墙钟/RSS。这是额外控制，**prescan 一致本身不是完整地址流相等的证明**；完整流证明范围是上面的9组完整输入配对。截断变体不冒充完整采集。见 prescan-validation.json（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-block-cache-20261104/raw/prescan-validation.json`）。
- 同一 OpenCSD 路径的差分只证明有限输入不改变原有输出，不是独立协议正确性证明，也未覆盖所有 IT/投机/动态镜像组合；未购买/操作 J-Trace/Ozone，没有商业实现同期测试。
- 辅助验证首次使用现有 main `etm_storebuild.exe prescan --json` 时退出7，父目录存在但无法创建 JSON。相对路径、绝对路径及正斜杠均失败；同一程序 stdout 控制通过，新重建程序相同路径可写。根因待定位，**没有声称本次缓存修复了它**。脚本随后改为捕获 stdout 并由 Python 保存，完成上述18次控制。登记 ZL-132，保留 失败（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-block-cache-20261104/raw/main-prescan-json-failure.json`）。首次 CMake 配置仍在运行时曾过早尝试 build，报 cache 不存在；等待配置结束后正常构建，不计作功能/性能结果。
- Python 两个新增工具及修改的 benchmark 通过 py_compile，Git diff whitespace 检查、`verify_dependencies.py --tracked` 的865个依赖输入核对通过；原生 Release 构建成功，保留既有编译警告。没有重跑无关硬件/冻结 EXE 套件。

## 复测

在本 worktree 根目录执行，输出目录必须新建，端口空闲；主机程序默认关闭实验缓存。测试程序只终止自己创建的离线服务，不停止共享服务。全部本任务 benchmark 服务已退出，无本任务硬件进程。

```powershell
cmake -S etm-service -B build/block-cache-native-new -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/gcc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/g++.exe
cmake --build build/block-cache-native-new --target etm_storebuild --parallel 4
python -X utf8 tools/bench_etm_block_cache.py --source-root E:/zynqlinkPRO --out build/block-cache-ab-new --storebuild prebuilt/etm-block-cache-offline-20261104/etm_storebuild.exe --port 8941
python -X utf8 tools/validate_etm_block_cache.py --campaign build/block-cache-ab-new --candidate prebuilt/etm-block-cache-offline-20261104/etm_storebuild.exe --reference E:/zynqlinkPRO/etm-service/build-native/etm_storebuild.exe
```

主线和固定程序保持原样。若后续产品化，优先把“不可变代码镜像”约束变成显式能力/失效接口，补足针对不同 IT/Context/错误重同步的合成用例，再决定启用范围；本轮不扩大到完整解码器重写或持续实时能力。
