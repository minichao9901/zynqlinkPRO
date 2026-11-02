# ETM 优化独立代码审查：main 与 codex/etm-cpp-stage1

日期：2026-11-02（Asia/Shanghai）。结论：**优化方向合理，已测执行语义一致、性能改善可复现；先修复 ZL-107，再合并交付。** 本轮审查没有修改候选实现，没有操作硬件、目标时钟、Flash/QSPI，也没有更新固定 EXE。

## 比较身份与范围

- 候选 worktree：`E:/zynqlinkPRO-work/etm-cpp-stage1-20261102`，提交 `c38b6a8943154e274c7fd1334d8990d3e2dd6330`。算法源码提交 `77bf1c2`，交付原生程序提交 `9e4318a`。
- 起始 main：`e6f26cc`。审查过程中另一会话提交了 `5966fa3`，只涉及 Web 评审文档及问题表；已核对 `git diff e6f26cc 5966fa3 -- etm-service tools` 为空，四组对照使用的 main 实现不变。
- 对比全部新增/修改的生产 C++、Python、构建配置、测试和验收工具；读取两阶段报告、产物 manifest 与原始结果。主关注点是 direct 输入的语义、状态机共享、缓存重放、诊断格式、输入身份、发布失败及升级兼容性。
- 独立核对构建 manifest 中 16 份源码和 3 份 EXE：当前原字节 SHA 全匹配，源码 Git blob SHA 及内容匹配；见 [provenance.json](raw/provenance.json)。没有重新编译 native 程序，也没有重新验收冻结候选。

## 需要修改：ZL-107 / P1，旧记录重新解码必然失败

位置：候选 `etm-service/tools/native_pipeline.py:128` 及 `:284-287`；入口是 `decode_stream.py:146-176` 新启用的 direct 分支。

新分支将 `native_sha` 赋为 `etm.bin` 的 SHA，但发布前仍无条件用它校验记录目录中已有的 `native.bin`。main 的正常解码会保留 native.bin；因此升级后重新解码旧记录、导入带 native.bin 的旧记录包后重新解码，或者 binary/direct 切换复测，都会在完成建库后报 `输入在构建期间变化：native.bin`。

这不是输入真的发生变化。独立复现步骤：

1. 使用 main 对保留的 F103 100ms 输入在全新目录执行原生 `decode_stream`，成功恢复 550478 条指令。
2. 保持相同输入、ELF、目录，改用候选代码的默认 native profile 执行同一调用，稳定抛出上述异常。
3. 再次复现前后计算 native.bin、etm.bin、firmware.elf 和旧 store manifest 的 SHA：四者全部未变。新一代没有发布，旧 manifest 保留。
4. 同一输入在候选的全新目录成功，并与 main 完整结果一致。

证据：[upgrade-failure.json](raw/upgrade-failure.json)。其中保留实际堆栈和前后 SHA。现有差分/基准工具每轮创建新目录，未覆盖升级重解码。

建议把原始 ETM SHA 与 native SHA 分开命名、校验和绑定；direct 路径仅将其实际消费的原始 ETM 指纹作为构建结果身份，明确处理旧 native 派生文件。不能通过关闭 hash_inputs 或自动删除用户记录绕过。补充“main 生成旧记录 → 新版本重解码”和 binary→direct→binary 的回归，并继续验证真正被修改的输入会拒绝发布。**本轮仅审查，未修复。**

## 独立执行结果

不是只重跑候选内部的两个模式：本轮分别启动 main 与候选 Python/EXE，对相同原始输入重新解码至不同新目录，然后用候选读取器比较两份输出。使用候选读取器是为了能读取 main 大输入的 85.6MB 诊断块（候选已有 ZL-103 修正），并不重算或替换 main 的执行结果。

| 输入 | 指令记录 | main 秒 | 候选秒 | 完整语义对照 |
|---|---:|---:|---:|---|
| F103 100ms 保留记录 | 550478 | 1.641 | 0.903 | 通过 |
| F103 固定大输入 | 19565799 | 21.303 | 9.534 | 通过 |
| H743 ETMv4 固定夹具 | 210497 | 0.870 | 1.013 | 通过 |
| H743 初始化/echo 两秒输入 | 36022615 | 23.297 | 11.908 | 通过 |

每组只计一次直接 `decode_stream` 调用，含图像准备、解码、建库、索引、发布和清理，不含输入复制、HTTP/任务调度、硬件采集和浏览器绘制；没有清 OS 缓存。不能把这些数值当成 API 三轮稳定门禁，也不能宣称所有输入均小于 10 秒。小 H743 夹具本轮没有变快。

每组检查：summary/quality 完全相等；静态、字符串、执行序列、包、导航、聚合及检查点块（1/2/3/4/5/6/11）解压后逐字节相等；完整 analysis、全部展开诊断、60 张查询数组逐项相等。元数据中的 generation、路径、构建计时和诊断编码形式不要求字节一致。

- [F103 小输入](raw/main-candidate-small.json)、[F103 大输入](raw/main-candidate-large.json)、[H743 夹具](raw/main-candidate-h743.json)、[H743 两秒](raw/main-candidate-h743-2s.json)。
- [输入 SHA、计时及完整 summary/quality](raw/replay-results.json)。H743 两秒源输入取自候选已有 `build/stage2-h743-2s/direct/etm.bin`，SHA 为 `3bb82c465d926c43f857c47dcaa7afae0dc3976dd25b781dc492eb7d133650b6`，与候选已归档两秒报告相同；只读取 raw/ELF/配置/源码，不复制派生 store。
- F103 大输入原有 2 个 gap、522998 条未知执行未消失；H743 两秒保留 1 个 gap、1139 条未知执行、429343 个周期元素。结果一致不意味着执行流完整或周期精度获得了新的硬件证明。
- Python 13 项针对性测试、55 项 CLI 测试通过；C++ 5 万步共享状态 oracle 和 7 万唯一范围 replay 自检通过。已有 ResourceWarning、Flask/pkgutil 弃用警告仍存在。[检查摘要](raw/checks.json)。

## 代码判断与证据边界

1. Direct 回调复用了相同 ElemView 字段规则及 builder visitor，减少大 native.bin 序列化/读回；单次解码缓存避免重复 OpenCSD 工作，是实质优化。没有修改 OpenCSD 协议算法、目标时钟或采集窗口。
2. Tracker/PathTracker 合并保留独立路径状态 oracle；帧缓存路径/火焰图节点、调用边使用数值 ID，降低热路径字符串和树查询开销。本轮四组真实输入没有发现调用、异常、谓词状态、返回、checkpoint 或周期聚合漂移；不将有限输入覆盖说成形式证明。
3. 紧凑诊断仍能还原全部条目、稳定顺序和计数；强制特性位 0x2、配套 Python/native export 和重建索引的位保留有对应实现。旧读取器拒绝新格式是显式兼容边界；交付时仍需配套更新读取器。
4. 原报告的 binary/direct、shared/independent、buffered/rescan 对照有价值，但都不自动等于未修改 main 的 A/B。本轮补足四组 main A/B；原先三次 API 小于 10 秒是作者已有证据，本轮没有重跑该门禁。
5. 1GiB 限制针对 RAM replay 编码负载，raw、镜像、唯一范围映射、facts 和索引仍占额外内存；超限要显式改用 `ETM_BUFFERED_DECODE=0`。这是有限窗口的离线处理，不能称为总内存 1GiB 或持续实时流式能力。
6. Python 静态字典、NumPy 查询索引、JSON/发布仍在路径内；“全部 C++ 化”、硬件 Web E2E、冷盘保证和更大窗口均未由此次审查证明。冻结候选只核读已有报告，未重复执行。

## 集成注意：ZL-108 / P3，独立分支问题编号冲突

候选 ETM 分支使用 ZL-103（大诊断块拒读）、ZL-104（离线基准错投旧 runtime）；`codex/web-ui-compact` 同时把 ZL-103 用于 WebUSB/工程生成能力收敛、ZL-104 用于验收驱动旧 ELF 路径。两组不是同一问题。合并问题表及报告前需要建立唯一规范编号，并保留“分支 + 原编号”的历史别名映射，不能以同编号合并状态或覆盖证据。本轮登记冲突，未批量改写另一会话的历史报告。

## 复现与交接

同目录 [replay.py](replay.py) 是本轮实际使用的离线驱动；参数依次为代码仓库根、含 decoded.json/原始 ETM/ELF 的源记录目录、输出目录。它为保留失败证据捕获异常并写 result JSON，因此 shell 退出 0 不代表解码成功，必须检查 JSON 的 `ok`。

```powershell
python -X utf8 docs/validation/etm-optimization-review-20261102/replay.py E:/zynqlinkPRO E:/zynqlinkPRO/etm-service/records/capture-2579cfda576445a3a7e9b12d8cf76627 E:/zynqlinkPRO/build/etm-review-upgrade-new
python -X utf8 docs/validation/etm-optimization-review-20261102/replay.py E:/zynqlinkPRO-work/etm-cpp-stage1-20261102 E:/zynqlinkPRO/etm-service/records/capture-2579cfda576445a3a7e9b12d8cf76627 E:/zynqlinkPRO/build/etm-review-upgrade-new
```

第一步应在未合并优化的 main 运行；第二步对同一输出目录运行候选。不要对用户原始记录目录运行这个复现。

审查只新增文档、证据与问题索引；候选分支未修改、未合并、未推送。未启动硬件服务，没有本任务后台进程。优先修复 ZL-107 并复验，再协调 ZL-108 后合并；ZL-006 继续保持部分解决。
