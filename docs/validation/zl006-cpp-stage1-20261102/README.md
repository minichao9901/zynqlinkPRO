# ZL-006：C++直接回调原型与第一阶段性能门禁

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

编号协调（2026-11-02）：本文历史ZL-103规范编号为ZL-109。原文结论与原始证据保留；分支历史别名见[编号映射](../../问题编号别名-20261102.md)。

日期：2026-11-02（Asia/Shanghai）。独立 worktree：`E:/zynqlinkPRO-work/etm-cpp-stage1-20261102`，分支 `codex/etm-cpp-stage1`，基于 `e6f26cc`。本轮仅离线主机处理，没有连接、加载或改变板卡，没有修改PL/PS/目标固件，没有更新主工作区或固定bridge EXE。

**第一阶段的≤10秒完整离线API目标尚未达到。** 最终源码/原生程序的三次结果为 **12.745 / 12.654 / 12.546秒，中位12.654秒**。ZL-006继续“部分解决”，不能把本次提交或C++回调接通当作性能验收通过。

## 已实现

- 将OpenCSD字段视图和sink接口抽到`decoder_sink.hpp`，decoder可作为独立程序或链接进builder。新路径的element/packet直接送到C++ builder visitor，不生成native.bin或逐指令JSONL。
- 保留binary参考路径；`ETM_DIRECT_DECODE=0`可用于明确的离线差分，默认原生decode_stream路径启用direct。能力握手要求`direct-opencsd-v1`，旧builder明确拒绝，不静默回退。
- 输入采用原始ETM/ELF/config/镜像SHA及构建前后变化检查。direct结果绑定`etmSha256`，binary路径继续绑定`nativeSha256`；保留原始ETM和按需包重放能力。
- 指令ordinal→逻辑seq改为按事件插入位置的一次搜索，保留开头和中间连续事件的映射。叶节点首次出现采用线性归约。大型诊断JSON改用快速压缩，保留全部条目及CRC/SHA检查。
- 避免C++调用跟踪热路径反复复制旧函数名、销毁再分配previous函数字符串，并删除无消费者的path字符串副本。
- 新增完整store差分工具和离线双路径重放工具；原生EXE与源码一起纳入本分支，准确文件SHA见[构建manifest](build-manifest.json)。原生程序内嵌buildSha是基线提交，不冒充包含本轮修改的源码身份；实际构建输入以逐文件SHA为准。manifest另记Git blob SHA；C++与EXE原字节一致，6个Python文件仅存在Git LF/工作副本CRLF差异，已独立逐字节归一化核对。

当前仍保留一次OpenCSD唯一范围预扫描，准备静态字典后再进行直接解码/build。因此它尚不是只解码一次的全流程；索引与发布仍有Python/NumPy参与。低层直接调用`trace_store_write.decode_to_native`继续提供binary参考能力，不能据本原型宣称所有入口均已全C++化。`directPrescan`只计预扫描，第二次OpenCSD包含在nativeBuild内；不将其误报成OpenCSD全部耗时。

## 固定大输入与计时

本轮固定F103输入为5,892,279字节、19,565,799条路径指令记录，ELF SHA `e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f`。原始输入SHA `3b54995365d440cb154c8249b2fc2a0319d9ccb42c2460b3ca861550c421ea78`。来源为11月1日审计使用的`capture-e61a64f34d0047e4a9c1c617b87099e1`；本轮将最小可重放输入保存在[f103-large-input](f103-large-input/)，[输入manifest](input-manifest.json)绑定文件身份。

沿用`bench_etm_native_offline.py`，每次创建全新记录，复制raw/ELF/源码/会话元数据，不复制native/store/索引。执行实际Web后端API，计到解码、建库、默认查询准备、任务完成，不含输入复制、硬件采集、浏览器绘制。硬件路由禁用。本轮没有清空OS文件缓存，不称冷盘测试，也不与真实Web E2E混算。

| 最终源码轮次 | 完整API秒 | 结果 |
|---|---:|---|
| 1 | 12.745 | summary、共有quality字段一致，无native.bin/大JSONL |
| 2 | 12.654 | 同上，另作全量store对照 |
| 3 | 12.546 | 同上 |

中位轮次：nativeBuild6.008秒、queryIndex2.435秒、诊断构造0.340秒、块复制/JSON压缩1.186秒、最终assemble0.118秒；这些阶段之外还有预扫描、任务准备等，不能把部分分项之和当作完整API时间。完整结果（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/zl006-cpp-stage1-20261102/raw/f103-api-results.json`）保留全部原始数值和阶段。

[11月1日审计](../zl006-decode-audit-20261101/README.md)的同一输入API中位22.031秒是历史参照，未在本轮用原提交再做同时期A/B，因此不宣称严格同条件提速百分比。早期探索结果也保留在`raw/exploratory-*`：不同版本曾有16～19秒结果；`stage1-fast`计时期间有另外的验证进程，不能用作正式性能结论。最终三次串行运行，没有并行基准或硬件测试。提交后的单次`OPENCSD_MEMACC_CACHE_OFF=1`对照为14.146秒，未取得明确收益，未采用缓存策略变更；记录（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/zl006-cpp-stage1-20261102/raw/exploratory-cache-off.json`）单独保留。

## 正确性与范围

- 最终F103大记录：完整静态表、字符串表、全部执行序列块、全部包、导航和检查点按解压后字节相等；全量诊断条目和**60张查询表**逐项相等，包含默认window/timeline数据。证据（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/zl006-cpp-stage1-20261102/raw/f103-equivalence.json`）。保留2个gap和522998条未知执行，不把重建一致说成完整执行流全部已知。
- H743/ETMv4完整1秒大记录：binary与direct串行完整重放，summary/quality、上述全量语义块、诊断和60张查询表相等。证据（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/zl006-cpp-stage1-20261102/raw/h743-differential.json`）。这是离线处理，不能当作新的CLI硬件或GUI E2E验收。
- 旧F103小输入，以及末尾截去17字节的输入：binary/direct完整差分通过。小输入（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/zl006-cpp-stage1-20261102/raw/small-differential.json`）、截断输入（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/zl006-cpp-stage1-20261102/raw/truncated-differential.json`）。截断输入的质量结果保持两条路径一致，不用重试或归零掩盖尾部状态。
- 4项单元测试覆盖随机事件布置、连续事件、64位序号及诊断块有限上限；C++ SHA自检通过。`project run test.cli`的55项通过，日志（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/zl006-cpp-stage1-20261102/raw/cli-tests.log`）保留已有临时文件ResourceWarning，未将警告描述成测试失败或在本轮定位其来源。
- 未验证冻结EXE、真实浏览器交互或当前硬件状态；未关闭ZL-006。没有本任务后台服务留存。

## ZL-103：原有大记录诊断块超过统一解压上限

完整诊断比较首次发现：原记录BLK_ISSUES声明解压后85,603,690字节，原读取器统一64MiB限制使`issues_list`拒绝载入。该缺陷在旧记录和本轮新记录均存在，summary相等并未覆盖它；不是direct丢失诊断。

现为诊断块设置单独的**128MiB有限上限**，其它块继续64MiB；保留长度、CRC、完整zlib流和尾部检查。写入端也检查JSON解压后长度，超限明确失败，避免生成自身读不回的块。针对边界测试及完整F103诊断相等验证通过。关闭限定本次85.6MB诊断拒读问题；更大记录仍受显式128MiB限制，后续应考虑分页/分块，而非继续无界提升上限。

## 复测与未完成工作

```powershell
python -X utf8 tools/bench_etm_native_offline.py --record docs/validation/zl006-cpp-stage1-20261102/f103-large-input --out build/stage1-repeat-new --port 8897 --repeat 3
python -X utf8 tools/validate_etm_direct_offline.py --record docs/validation/zl006-cpp-stage1-20261102/f103-large-input --out build/stage1-diff-new
python -X utf8 -m unittest discover -s tools/tests -p test_etm_direct_index.py
```

API基准工具成功后保持本机离线服务运行供检查；完成后仅结束本任务工具进程。复测不能与另一个性能任务并行。完整输入的双路径差分会临时重建约1.3GB参考native.bin，属于验证参考输出，direct路径仍不生成该文件。

下一步应处理预扫描与第二次解码的重复工作，以及约6秒的nativeBuild；再推进C++索引/发布融合。尚需约2.65秒稳定缩短才能跨过当前≤10秒门槛，不能用缩窗、降频、跳过诊断或提前返回预览完成来实现。当前分支保留可审查原型及失败门禁证据，未合并main、未推送、未发布bridge更新。
