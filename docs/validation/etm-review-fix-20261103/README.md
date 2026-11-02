# ETM独立review处理：ZL-107、ZL-108

日期：2026-11-03（Asia/Shanghai）。在`codex/etm-cpp-stage1`处理[独立审查](../etm-optimization-review-20261102/README.md)，未操作硬件、目标时钟、Flash/QSPI或PL/PS。main仅提交本任务编号协调/观察文档，尚未集成优化代码或替换固定EXE。

## ZL-107：分离消费输入身份，保留旧派生文件

审查属实：旧代码把ETM SHA赋给native_sha，发布前又比较旧native.bin，导致同目录升级必然失败。现分别维护etm_sha/native_sha，私有facts使用明确的source_sha传递实际生产者校验和。

- direct校验原始ETM、ELF、配置和镜像快照，并核对builder的etmSha256；旧native.bin保留，不读取为事件源、不删除、不冒充已校验输入。
- binary校验实际消费的native文件及builder的nativeSha256；发布前检查其真实路径，不能被无关同名文件替代。
- manifest增加sourceInput（kind、recordFile、sha256）；只有实际消费记录根native.bin时才将其列入inputs。未消费派生文件显式标为unconsumedDerivedInputs。
- 读取验证仅在存在相符的ETM绑定/生产者身份、且native未绑定时，才把旧native.bin列为excluded。显式native绑定仍优先校验，raw/ELF/配置/镜像检查不关闭；hash_inputs未禁用。

回归使用**未修改main实现**先生成记录，再由候选在同目录解码，不只比较候选自身两种模式。F103真实100ms记录550478条，H743真实1秒18373686条：main→direct、binary→direct→binary、低内存rescan、重复direct均通过。旧native、原始ETM和ELF保持原字节；与main的执行块、包、导航、检查点、完整analysis、展开诊断及60表相等。

两组均注入同长度、恢复原mtime的实际输入修改：ETM、ELF、native-config、image-0及binary实际消费的native，全部拒绝新发布，旧manifest/decoded字节不变。故意修改**未消费**native的direct则成功发布，结果相等；测试结束恢复测试副本。没有对用户原始记录注入。

证据：[F103结果](raw/f103-result.json)、[H743结果](raw/h743-result.json)及同目录逐例JSON。4项绑定验证单测、13项既有算法测试、55项CLI通过；[CLI日志](raw/cli-tests.log)保留既有ResourceWarning。

## ZL-108：规范编号与历史别名

main已预留ETM规范ZL-109（历史ETM:103）和ZL-110（历史ETM:104）；Web:103/104保留其原有规范号。候选问题表已迁移且行编号唯一，日期列/处理列核对；新交接使用规范号。两个旧报告仅加别名说明，原结论与原始JSON不改写。规范表见[编号映射](../../问题编号别名-20261102.md)。另一Web工作树未被修改。

## 性能及范围

同一F103大输入的本轮完整离线API三次 **10.173 / 8.823 / 8.880秒，中位8.880秒**；包含建库、索引、发布及任务准备，不含硬件/浏览器绘制，未清OS缓存。[原始结果](raw/performance.json)、[全量对照](raw/large-equivalence.json)。首轮超10秒，不宣称稳定所有轮次<10秒，也不将旧快速轮次覆盖本次结果。

原始gap/未知执行仍保留。ZL-006维持部分解决；≤5秒、冷盘、持续实时及实际硬件Web E2E未由本修复证明。C++、RTL和Zynq固件没有修改，本轮不重建/替换它们；修复位于Python身份校验/绑定层。

## 复测与待收尾

在候选worktree执行，输出为全新任务目录：

```powershell
python -X utf8 tools/validate_etm_redecode.py --main-root E:/zynqlinkPRO --record E:/zynqlinkPRO/etm-service/records/capture-2579cfda576445a3a7e9b12d8cf76627 --out E:/zynqlinkPRO/build/r107-new
python -X utf8 -m unittest discover -s tools/tests -p test_etm_source_bindings.py
```

新增的工具明确检查子进程退出及JSON ok，不把失败JSON的shell退出0当作解码通过。main旧decoder在候选工作树输出Cannot write的另一个现象已登记[ZL-116](../etm-legacy-path-20261103/README.md)；根因未定。使用main/build新目录完成升级回归不算修复该路径边界，旧失败未删除。

冻结候选的旧记录实际Web入口重解码、最终源码/文件身份绑定及交接状态在收尾后追加；此前不将其标为已验收。
