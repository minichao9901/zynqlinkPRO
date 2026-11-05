# 四个历史研究分支的保留价值审查

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

日期：2026-11-03（Asia/Shanghai），对照 main `4111dfa`。用户要求判断是否比当前方案更好。本轮只读检查分支、工作目录和已有证据，并运行离线 RTL 对照；没有上板、加载、改时钟、重新综合或改生产代码，没有删除这些分支/worktree。

结论：没有发现值得直接合入、可替代当前实现的更优方案。需要保留的是部分研究方法、负例与固定基线，不需要把这些旧分支长期当作活跃开发线。

| 分支 | 判断 | 仍有价值的内容 | 后续处置建议 |
|---|---|---|---|
| `codex/etm-lane-calibration` | 已完整并入 main，分支本身冗余 | 24MHz 已验收配对、原始记录；36MHz/ELD1失败现场 | 保留最佳 tag 和报告；归档未匹配的中间产物后可退役 worktree/分支 |
| `codex/fclk-timing` | 已提交内容全在 main；未提交脚本是被 main 覆盖的旧稿 | 未提交补丁作为历史过程证据 | 已保存补丁快照，无须合回；可后续清理 |
| `codex/swd-timing-generator` | 不能作为当前 SWD 实现替代品 | 逐半拍波形等价方法、独立采样/Q16探索及失败资源/时序数据 | 现有 tag 已完整覆盖分支头，建议研究归档后删分支名 |
| `wip/riscv-sba-pipeline` | 当前测试下退化且有协议状态问题，不建议合回 | 首响应同步、sticky SBA错误恢复的研究意图 | 3个独有提交先固定归档tag，再退役；若重新研究，应重新实现/验证，不直接cherry-pick |

## ETM 通道研究

分支头 `1d63086` 可从 main 追溯，无独有提交。交付、24MHz 基线和 ELD1 都已进入主线，详见 [原合并与最佳基线说明](../../ETM主线合并与最佳基线-20261101.md)。`etm-best-24mhz-ddr-usb-20261101` 有长期复测价值；它不是当前主机软件性能的回退建议，也不是已完成36MHz/逐线自动校准的证明。ZL-008/009的暂停与失败边界继续保留。

本地 `build/` 发现107个 `.bit/.elf` 文件，去重后12种内容，其中8种已匹配main已跟踪的 `prebuilt/`。另4种未匹配 `prebuilt/`：早期DDR pilot/USB编译/diagnostic PS中间ELF，以及旧H743记录中的目标ELF。未匹配不等于未在Git其它位置或记录包出现，也不等于更快/可交付；没有新的验收依据可将它们晋升。保留了逐路径SHA清单：产物清单（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/research-branch-review-20261103/raw/etm-build-artifacts.json`）。将来清理此目录时先留存这些唯一中间产物和失败证据，不能把整个 `build/` 当作已验收配对。

## FCLK 时序分支的未提交修改

分支头 `244ab71` 已合入main。工作区修改相对该旧提交看似新增大量检查，但与当前main比较，主线已经具备可选观测寄存器检查、目标FCLK参数、setup/hold/recovery/removal、CDC报告及release拒绝降频发布。

main还额外具备：133333333Hz默认工作点、IDDR Q1/Q2路径报告、DDR/debug/CDMA独立端点报告、参考时钟组及check_timing、禁止高于明确工作点的自动晋级、完整时序摘要签核，以及从当前打开的checkpoint重新生成bit。旧稿仍默认120MHz，允许频率向上探索，缺少这些后续检查，并按文件mtime复用已有bit。按文件时间不能独立确认bit与当前DCP身份，不能用它替换主线实现。

未提交文件保持原样，快照为 原文件（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/research-branch-review-20261103/raw/fclk-uncommitted-verify_routed.tcl.txt`）、相对旧分支的补丁（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/research-branch-review-20261103/raw/fclk-uncommitted.patch`）。没有为了清理而覆盖其工作目录，也没有把快照当作可执行验收入口。

## SWD 时序发生器

7个独有提交由 `swd-timing-generator-rx-events-20261028` 完整保存。Q16半周期/独立采样是可研究方向，逐半拍对照比只看最终读写数据更能发现时序偏移，方法值得保留。但与当时同条件基线比较，记录的LUT从10908升至17882（+63.93%），寄存器15814到22468（+42.08%），BRAM从2到6，新增DSP。

归档构建标记 `candidate_bit_generated_but_timing_failed`，150MHz setup相对当时main恶化4.832ns。后续retimed记录仍未通过当时工作点；分支头再整理ACK/数据RX事件，但未找到其新的已验收route/板测胜出证据。这些数字属于当年的同条件比较，不是当前main全设计资源，也不能用当年150MHz替代当前133MHz约束。仿真等价、生成bit不等于时序和实板通过，不应因灵活参数更多而判定更优。

保留 原始构建记录（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/research-branch-review-20261103/raw/swd-build-comparison.json.txt`） 与 解析摘要（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/research-branch-review-20261103/raw/swd-summary.json`）。原Git对象在JSON结束后含字面量反斜杠n，原字节未改；摘要仅提取首个JSON对象。详细方法可用 `git show codex/swd-timing-generator:docs/SWD时序发生器重构与仿真.md` 及同分支 `SWD时序可配置接口.md` 查看，后续删除分支时使用上述tag仍可读取。

## RISC-V SBA WIP

分支头 `a236da6` 有3个main没有的提交。当前main本身已有单扫描posted流水、读预取白名单、尾部/错误检查；之后的 `2bd88ad`、`36875ef` 又扩展AXI SRAM预取并验收更高频DMI空闲设置，不能把旧WIP称为当前缺失的“新流水线”。

本轮将同一份当前 `tb_riscv_words.sv` 和 `jtag_shift.v` 分别接到不同核心/模型：

| 组合 | 结果 |
|---|---|
| 当前main核心＋当前模型 | 通过；128字读写各136次扫描，响应所有权/轮询/尾部检查通过 |
| WIP核心＋当前模型 | 部分场景通过；一组128字读取用了644次扫描，触发非流水断言 |
| WIP核心＋其原模型 | 部分场景通过；随后posted读取第1项得到0，触发读值断言 |

见 完整输出（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/research-branch-review-20261103/raw/riscv-comparison.json`）。这是当前测试台的集成兼容对照，不是对旧分支原始环境的全面验收，也不是新的板级MB/s测量。644/136约4.74倍扫描，足以否定“直接换上就比main快”，不宜推广到所有输入。

另有确定的静态协议问题：WIP `EVALUATE` 用 `scan_result[1:0]==1` 进入标为“DTM busy”的重试状态，而实际DMI返回BUSY编码是3；规范还要求清除DTMCS的sticky busy状态再重试。参见 [RISC-V官方调试实现说明](https://docs.riscv.org/reference/debug/v1.0/debugger_implementation.html)、[官方0.13.2规范](https://riscv.org/wp-content/uploads/2024/12/riscv-debug-release.pdf)。不能把当前模型中人为注入的非零无效响应当成真实BUSY验证。main在此处对非零状态报错，并没有使用这个错误的BUSY自动重试分支。

首响应同步、SBA W1C错误恢复值得作为需求和负例保存，但DTM恢复与SBA错误恢复是不同层次，不能仅改一个编码便称已修复。当前没有修改或合入WIP代码。登记ZL-128限定历史候选问题，影响不外推为当前main已有相同缺陷。

本轮比较未改变任何bit/ELF或固定EXE；无须为文档审查重新打包或上板。分支头、独有提交数量、覆盖tag见 分支清单（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/research-branch-review-20261103/raw/branches.json`）。
