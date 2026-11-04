# ETM离线研究归档：暂不采纳

2026-11-04（Asia/Shanghai）。用户明确要求：有价值文档同步main，删除实验worktree，当前暂不采纳实现。**本次只同步文档、原材料、manifest及成功/失败对照证据，不引入实验源码、工具、新开关或候选EXE，不更新固定bridge程序。相关优化/流式研究暂停，后续需要用户重新提出需求才继续。** 主线已有C++解码/建库和既有硬件验收不受此处候选能力表述替代。

## 保留的资料与结论

| 历史报告 | 有价值的结论 | 为什么没有采纳 |
|---|---|---|
| [架构资料与基本块缓存](../etm-block-cache-20261104/README.md) | 多数分层/C++/范围缓存思路主线已有；OpenCSD内部缓存可减少重复走查。该批H743完整离线API中位缩短约15%–17%。 | 仅固定镜像和有限样本，默认关闭；资料中包头分派、地址解压等伪代码不完整，不能照抄重写协议。 |
| [流式解码与增量统计](../etm-stream-offline-20261104/README.md) | 持久解码器、跨块半包、按范围频次累计及调用路径归约可以处理全流，不必每次重建全部历史索引。部分H74320秒均匀回放能跟上平均输入。 | 存在约479ms积压及其它失败；F103原速溢出；不是真实USB/PL/突发/GUI/长稳验收。 |
| [ETMv3 DLL资料与分页后继缓存](../etmv3-jlink-analysis-20261104/README.md) | 最终F103无节拍“解码＋增量统计”2.497→1.717s，约31%；固定PC缓存、预存后继和组合统计有局部收益。 | 完整API最终中位仅约3%，两组对应配对变慢；关闭新开关有约7%研究入口代价，原速仍溢出；不同阶段/旧程序也有失败，不能选最快轮次推广。 |

上述是各报告当时的历史数据，不是对当前main的本轮重新测速。完整执行流/PC状态/周期/analysis、60张查询表及小前缀旧JSONL对拍的通过范围与失败均保留，不能把对拍一致理解为绝对协议正确或物理采集无损。

## 可复用的设计线索

- 区分引脚采样/传输、有效ETM字节、恢复指令/范围回调、统计、完整历史索引/发布和绘图；150MHz端口规格不能换算成全部软件工作量。
- 不可变代码镜像下，按PC缓存指令固有信息/后继地址，按确定序列批量归约；不能从样本邻接关系拟合needs_addr后把同一份数据当独立golden。
- UI显示窗口与全流累计统计可以分开；保持连续解码状态、提交水位和有界队列，溢出必须失败，不以降低生产速率或悄悄丢弃制造实时通过。
- 继续采用标准协议/指令分类作为语义来源。材料所称“无缓存/Thumb子集/22%”是其etraced原型，不能套到本仓库；P-header format2等真实语义不能按文中伪代码省略。
- 比较固定输入/ELF/输出合同，独立核对原始记录、拼接流、回调/逐条执行摘要和完整查询表；成功、失败、波动、历史源码及程序身份一起保留。

<a id="source"></a>
## 归档源码与程序

完整研究引用：**`archive/etm-offline-research-20261104` → `0732f67a0b7ec14dad956a8854de09c72a44647b`**。原实现提交依次为 `41ec0e2`、`60602de`、`1fbdc7e`；归档提交 `0732f67` 另补存两个manifest曾引用的未跟踪比较EXE，未新增实验。

Tag中的位置：

- `etm-service/native/`、`etm-service/vendor/OpenCSD-1.8.3/`：原实验源码；`tools/bench_etm*` / `tools/check_etm*` 等为当时工具。
- `prebuilt/etm-block-cache-offline-20261104/`、`prebuilt/etm-stream-offline-20261104/`、`prebuilt/etmv3-paged-offline-20261104/`：三个实际测量候选及SHA。
- `prebuilt/etm-offline-research-archive-20261104/`：广域/运行时限制中间比较程序和原build路径映射。它们包含失败，不是正式交付。

当前main不包含上述新增实现/候选目录。原报告中的运行命令需要在取回的归档版本及新输出目录执行；历史绝对worktree路径已经失效。**本次没有重新执行这些命令。** 仅检查文档可先用：

```powershell
git show archive/etm-offline-research-20261104:docs/validation/etmv3-jlink-analysis-20261104/README.md
git ls-tree -r --name-only archive/etm-offline-research-20261104 -- prebuilt/etm-offline-research-archive-20261104
```

Manifest中的源码、程序和工作目录SHA对应当时的实验树/程序，不用于校验当前main的同名文件。raw/reference/原manifest保持归档字节；三份README只补了归档状态及改向本索引的程序链接。原始输入记录在主目录独立保留，删除实验worktree前已逐项核对raw/ELF/sources的SHA。可重建的concat、索引、CMake缓存及临时服务数据没有整体迁入main，令牌未归档。

## 问题编号与状态

- **ZL-006继续部分解决**：main已有能力沿用原验收，当前候选未采纳、研究暂停，不把候选成果冒充主线能力，也不关闭性能问题。
- 实验分支旧 **ETM ZL-132 → main ZL-143**：旧主机程序显式JSON/二进制落盘失败的历史待验证事项。main既有ZL-132（HAL启动USB向量问题）保持原样；raw中的旧编号不重写，不假定两者相关。
- ZL-143只保留旧程序证据及stdout绕过对照，没有根因修复、没有复测当前main，不因本次归档自动启动定位。

文档迁入main后执行文件/归档引用、证据SHA及diff检查，无硬件或性能重测。原实验worktree `E:/zynqlinkPRO-work/etm-block-cache-20261104` 按用户授权删除；其他worktree与main的build/数据保持原样。未推送。

[清理核对记录](cleanup.json)保存归档引用、原始输入独立保留、目标路径/重解析检查及Git worktree移除结果。
