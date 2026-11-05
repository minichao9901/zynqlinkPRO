# ZL-006：原生静态字典与查询读取迁移

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

日期：2026-11-03（Asia/Shanghai）。候选分支 `codex/etm-cpp-stage1` 完成离线验收；未合入 main，固定 EXE 未替换，未推送，未操作硬件。

## 实现与交付

默认 TraceStore 数据面由 C++ 完成：ARM ELF32/DWARF 解析、Thumb/IT/控制流静态字典、OpenCSD 单次解码与有界重放、完整索引、最终建库，以及分页、过滤、窗口、时间线、导航、源文件和诊断读取。批量执行数据不再交给 Python/NumPy 解包或建表；查询通过私有常驻进程 `etm-query/1` 返回页面 DTO。Python 保留任务/HTTP、输入身份核对、记录文件及原子 manifest 发布。

源码 `194aa67` 实现主体，`48f3851` 修正重复展开导航表；交付 `d6f8fd3` 的 builder 内报源码 `48f38519bb90`。冻结包从干净源码 `6b9732c` 构建。准确工作文件/Git blob、EXE/DLL 哈希见 [build-manifest.json](build-manifest.json)，历史来源指纹仍保留，不能把导入源码号当作本轮构建号。

独立程序目录：`E:/zynqlinkPRO-work/etm-cpp-stage1-20261102/build/etm-native-static-query-bridge/`，入口 `zynq-etm-bridge.exe`，需保留整个目录。Capstone 5.0.7 只构建 ARM，与 Python 参考版本一致；libdwarf 2.3.3 以可替换 DLL 动态链接，源码、来源归档 SHA、许可及重建说明已纳入仓库/包。DLL 仅依赖系统 KERNEL32/msvcrt，冻结验收不依赖 PATH 上的 Python/Node。

旧实现保留用于明确的研发对照：`ETM_NATIVE_STATIC=0`、`ETM_NATIVE_QUERY=0`、`ETM_COMPLETE_INDEX=0`。旧 JSONL 记录后端及显式索引容器 reencode 兼容工具仍有 Python 实现；正常 TraceStore 读写、v1/v2 索引读取、缺失索引的内存重建和重新建索引已由 C++ 接管。这里的“全 C++”限定默认 TraceStore 数据处理链路，不表示删除仓库内全部 Python 代码。

当前目标是 ARM32 小端、内部 Flash 执行镜像及现有 4096 指令索引单元。非零起始序号旧库可读，原地索引重建拒绝其重定位；自定义索引单元及其它架构未验收。重放缓冲有 1 GiB 载荷上限，不代表整个进程内存有相同上限。

## 正确性

- F103 的 221 个函数/3028 个 DWARF 行区间、H743 的 320/4921，连同全部 ELF segment 和完整 Web ELF DTO，逐项与原 Python 实现一致：native-images.json（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/native-images.json`）。
- F103 大记录、H743 1 秒和 2 秒各三轮：完整执行块、静态字典、诊断、analysis、默认视图、语义查询元信息及全部 60 张数组的 dtype/shape/每个值相等：九轮对照（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/full-store-comparisons.json`）。全局协议标签的有意修正另按 ZL-117 验证。
- 每种记录 182 个场景，共 546 次深度 DTO 对照：边界/随机序号、分页/过滤、任意窗口、时间线、各类导航/PC/回绕、诊断和源码。见 F103（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/queries-f103.json`）、H743 1s（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/queries-h743-1s.json`）、H743 2s（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/queries-h743-2s.json`）。
- 32 项原生专项、55 项 CLI 回归通过；含禁止 Python ELF/字典/库解析、旧 NPZ、缺失索引、CRC 损坏、索引换代隔离、v1/v2 重建、发布失败回滚、508 个 Unicode 小写样本及双协议 2050 个包类型名称。865 个依赖文件身份通过。见 验收汇总（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/validation.json`） 和保留的日志。
- 双协议均从 main 真实生成的旧记录升级，binary/direct/rescan 切换、重复解码、5 类真实输入变更拒绝、未消费 native.bin 原字节保留和完整 60 表对照通过：F103（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/source-upgrade-f103.json`）、H743（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/source-upgrade-h743.json`）。ZL-107 未回归。
- 独立冻结包通过双协议导入、查询、火焰图 HTML/SVG、CLI/Web 一致性、重复启动复用；再次升级旧记录并逐项比较完整库，两个服务已退出。冻结 CSV 各输出 900–1700 共 801 条连续记录。见 离线验收（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/frozen-offline.json`）、F103 升级（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/frozen-upgrade-f103.json`）、H743 升级（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/frozen-upgrade-h743.json`）、CSV（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/frozen-csv.json`）。

ZL-117 限定候选关闭：新库协议标签取实际配置，错误包名称按实际协议生成。除枚举全覆盖外，在真实记录派生的 native 容器注入 BAD_SEQUENCE/BAD_TRACEMODE，ETMv3/ETMv4 的存储诊断均与原类型码字典一致：故障注入（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/protocol-fault-injection.json`）。此项是 native 包型注入，不能冒充硬件或损坏 raw 流的容错验收。旧库不会被自动改写，需重解码才能修正历史标签。

## 耗时与边界

对照版本为独立干净 worktree 的 `d022623`（上一阶段 C++ 完整索引/建库，Python 静态准备/读取）。三个原始输入及 ELF/Sources 指纹固定，所有原始输入核对未改。每组各三轮，按记录复制完后计时，首轮应用缓存为空，未清 OS 缓存；均为离线完整 API 处理，排除硬件采集/USB/上传及浏览器绘制。没有用离线秒数冒充真实 Web E2E。

| 记录 | 首组旧 → 新中位(s) | 最终重复组旧 → 新中位(s) | 最终新三次(s) |
|---|---:|---:|---|
| F103 1957 万指令 | 7.621 → 6.860 | 13.663 → 8.584 | 8.868 / 8.584 / 8.187 |
| H743 1s，1837 万指令 | 4.779 → 4.764 | 5.133 → 7.384 | 7.658 / 7.384 / 5.165 |
| H743 2s，3602 万指令 | 9.191 → 9.944 | 12.705 → 9.476 | 9.476 / 9.185 / 9.908 |

两组波动大且存在变慢项，不能据此归因出稳定的整体加速比例。首组新 H743 2s 的 11.683s 仍保留；最终三次低于 10 秒不构成稳定保证。所有逐轮性能、summary、quality 和输入 SHA 见 首组（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/initial-performance.json`）、最终重复组（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/performance-summary.json`）。静态处理显著缩短，但完整处理仍主要受解码/重放、索引编码、写盘与验证影响，不能仅靠更换语言保证达到 Ozone/J-Trace Pro 的水平。

同一完整库的独立读取测试，C++ 包含子进程启动、通信及 DTO 转换；查询为五次中位，打开为单次，未清 OS 缓存。单位 ms：

| 操作 | F103 Python → C++ | H743 1s Python → C++ | H743 2s Python → C++ |
|---|---:|---:|---:|
| 打开/验证 | 323.24 → 137.77 | 285.17 → 112.89 | 369.58 → 260.87 |
| 普通分页 | 3.13 → 4.57 | 5.77 → 4.89 | 2.08 → 5.87 |
| 过滤分页 | 841.80 → 264.17 | 698.28 → 278.15 | 1480.57 → 471.12 |
| 局部窗口 | 54.42 → 11.25 | 51.89 → 11.70 | 72.86 → 14.84 |
| 默认时间线 | 11.19 → 9.14 | 14.79 → 11.43 | 22.33 → 14.53 |
| 调用导航，热会话 | 0.004 → 0.169 | 0.004 → 0.252 | 0.005 → 0.136 |

轻量请求有 IPC 固定开销；Web 现有代缓存仍有效。首轮发现 C++ 导航重复解包（F103 约 12ms），`48f3851` 改为不可变会话缓存后约 0.17ms，原始测量也保留。三种记录所有计时 DTO 的摘要均相等，详见 F103（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/final-query-latency-f103.json`）、H743 1s（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/final-query-latency-h743-1s.json`）、H743 2s（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/final-query-latency-h743-2s.json`）。这些是读库接口时间，不是浏览器首屏。

## 复测与交接

用 `tools/validate_etm_native_images.py` 对双 ELF 检查全表/Web DTO；`tools/validate_etm_native_queries.py --record <记录> --out <新目录>` 复测 182 场景；`tools/bench_etm_native_queries.py` 复测读取延迟。完整 API 用 `tools/bench_etm_native_offline.py --record <记录> --out <新目录> --port <空闲端口> --repeat 3`，需要在基准和候选各自 worktree 运行，完成后只停止本任务服务。`tools/compare_etm_stores.py` 对照全部执行块/60表；原地升级与冻结验证用 `validate_etm_redecode.py`、`verify_etm_redecode_package.py`。故障包型可用 `validate_etm_protocol_faults.py` 复测。

开发期不通过和中断保留在 development-observations.json（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-native-static-query-20261103/raw/development-observations.json`）：首次静态合同缺参、查询 codec 原型错误、全局线程 mock 导致通信超时、raw 故障实验未覆盖所需包型、用户中断后的重新验收均未算作通过。CLI TemporaryFile 警告经分配跟踪定位到 Werkzeug 测试 multipart 临时文件，未据此声称原生 worker 泄漏。

本轮没有下载 bit/ELF、改时钟、复位、刷写或重新采集。F103/H743 的输入来自上述归档记录，历史配对/时钟仅为快照；本报告不声明当前板上状态。全部本任务服务退出，固定 `dist/zynq-etm-bridge/` 和 main 生产代码保持原状态。ZL-006 仍为部分解决，后续真实硬件 E2E 和与 Ozone 的同条件对照仍未完成。
