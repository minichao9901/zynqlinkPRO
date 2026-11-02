# ZL-006：执行状态合并、单次解码与紧凑诊断

日期：2026-11-02（Asia/Shanghai）。分支`codex/etm-cpp-stage1`，继续使用独立worktree；基线为`1c83d8b`。本轮没有操作硬件、改目标时钟/Flash/QSPI或PL/PS，没有替换主工作区的固定EXE。

最终源码提交`77bf1c2`、配套原生程序的完整离线API为**9.290 / 8.877 / 8.848秒，中位8.877秒**，三次均<10秒，达到本阶段固定输入三次重建门禁。没有清空OS缓存，不宣称冷盘或所有负载均≤10秒。[构建与原字节身份](build-manifest.json)、[最终结果](raw/final-api-3.json)、[第1](raw/final-equivalence-r1.json)/[第2](raw/final-equivalence-r2.json)/[第3轮全量对照](raw/final-equivalence-r3.json)分别保留。先前初测10.387/9.553/9.720秒、首轮超10的事实仍保留于下文，不能与最终源码轮次混算。固定输入和计时边界沿用[上一阶段](../zl006-cpp-stage1-20261102/README.md)。冻结候选验收后补充结果。

## 算法与数据表示

1. **一套调用/异常状态。** `Tracker`作为在线facts的状态来源，`PathTracker`通过observer接收状态变化，仅维护数字路径节点。帧保存路径节点、火焰图节点和函数统计ID；调用边用数字函数ID对索引，减少字符串复制和重复树查询。旧独立状态机保留作oracle，`ETM_SHARED_TRACKER=0`可明确对照。5万步合成状态转换覆盖未知执行、条件未成立、嵌套异常、返回地址检查及重启，与独立状态机逐步对照。
2. **OpenCSD只解码一次。** 同一C++ worker先生成有界的临时RAM记录及唯一范围表，Python准备静态字典后由同一进程重放至builder，避免再次运行协议解码。常见范围只保存计划ID、偏移和必要状态；包和稀有事件保留原始visitor字段。F103大输入缓存205259423B，初测worker峰值约442.9MB。缓存编码负载上限1GiB，非整个进程内存上限；超限明确失败，可显式设置`ETM_BUFFERED_DECODE=0`使用双遍低内存模式，不静默降级或丢数据。这仍是有限窗口离线处理，并非持续实时流式架构。
3. **诊断共享原因、保存数值区间。** 约85.6MB的重复诊断JSON改为原因表、谓词区间三元组、边界事件三元组和少量完整packet诊断。写入时复用C++返回的区间，不逐条生成重复字典/文本；浏览时恢复原JSON条目、顺序和计数。构造阶段从约0.34秒降到初测约0.003秒；不是删除诊断。`ETM_COMPACT_ISSUES=0`保留原JSON参考表示。
4. **建库同步记录入口索引。** 从完整facts记录首条指令PC；静态表仅包含已恢复的指令。入口回读使用该索引回答首PC与入口是否出现，避免为查第一条指令解压整个执行块。旧记录保留原查询路径。初测`captureStartAndMetadata`约0.056秒，结果与原路径相同。

函数名等展示字符串仍保留，静态字典准备和NumPy查询索引仍在Python侧；没有宣称全流程已全部C++化。内部RAM缓存不是新的持久化native文件，raw/config/ELF/镜像SHA、构建前后变化检查、输出CRC和整库SHA均保留。

## 新诊断格式的兼容边界

store头`required_features=0x00000002`声明紧凑诊断，`optional_features=0x00000001`继续声明查询索引。旧读取器必须拒绝新强制位，不能把紧凑数据当旧列表显示。配套Python读取器和`etm_export.exe`已支持，旧记录继续可读；固定旧bridge EXE未替换。

BLK_ISSUES仍为有界zlib JSON，主要内容如下：

```json
{"format":"etm-issue-runs/1","reasons":["IT reason","boundary reason"],
 "predicates":[[2,3,100]],"boundaries":[[0,0,1]],"extra":[],"total":2}
```

谓词行为`[startSeq,endSeq,offset]`，原因使用reasons[0]；边界行为`[seq,offset,reasonId]`。恢复时保持原稳定排序，再附加packet诊断。读取器检查版本、类型、范围和总数，保留128MiB诊断解压上限；其它块仍64MiB。索引重编码/重建必须保留强制位。早期开发的六列rows表示也由读取器明确支持，未作为独立产品格式发布。

## 验证与证据

- [交错状态机A/B](raw/tracker-ab.json)：独立/共享各三次，builder中位6.394/5.650秒，完整API中位13.622/13.242秒；单独状态合并不足以达到10秒。
- 最终三个全新记录均完整重建，未复制native/store/索引；全部summary/共有quality相同，无native.bin/逐指令JSONL，三轮完整执行块、诊断、analysis及60表逐项相等。最终原生builder内嵌源码提交77bf1c2，逐文件构建输入/Git blob双SHA及三份EXE哈希见manifest，避免Git换行差异冒充源码身份。
- [初测三轮](raw/initial-api-3.json)保留全部时间与真实质量；[完整对照](raw/initial-equivalence.json)包含所有静态/字符串/执行/包/导航/检查点块、全部诊断、完整analysis及60张查询表，不是抽样。保留F103原有2个gap、522998条未知执行。
- [H743单次/双遍差分](raw/h743-buffered-differential.json)、[H743完整2秒差分](raw/h743-2s-differential.json)、[截断尾部差分](raw/truncated-differential.json)全部通过；两秒只是已有输入离线重放，不是新硬件验收。
- C++合成检查：5万步状态oracle、7万唯一范围（覆盖16/32位计划ID）、超过8MiB块边界的包、稀有事件/64位字段、payload变体、缓存超限、CRC已知向量。13项新增/关联Python测试通过；[最终55项CLI](raw/final-cli-tests.log)通过，日志保留原有ResourceWarning。
- [实际C++父进程退出](raw/owner-exit.json)及[静态准备失败/KeyboardInterrupt](raw/preparation-faults.json)验证worker退出且不发布manifest。Python自身的握手超时、非法字典与取消另有真实子进程测试。
- [索引重编码](raw/reindex.json)验证新特性位及完整语义保留；原生CSV区间导出通过。编码器RLE策略[独立对照](raw/index-codec-ab.json)无明确收益且体积更大，未采用。
- 所有探索轮次继续保留于`raw/exploratory-*`；它们属于不同开发版本，不能挑选单次最短值冒充最终版本结果。

## ZL-104：离线基准可能错投旧服务

工具完成后原本保持服务供检查；重用同端口时，曾向旧runtime投递新record ID，得到旧目录缺session的HTTP400。该轮失败保留于[证据](raw/failed-stale-port.json)，未计入成功性能轮次。

现增加启动前端口占用拒绝，以及投递任何decode前的随机runtime身份核对；HTTP错误保留响应原因。真实占用端口测试证明拒绝前不创建记录、不发送HTTP请求；不会停止占用服务。只关闭本任务服务后重测。问题表同步更新，登记/修复范围仅为本离线工具。

## 复测

```powershell
python -X utf8 tools/bench_etm_native_offline.py --record docs/validation/zl006-cpp-stage1-20261102/f103-large-input --out build/algorithm-api-new --port 8897 --repeat 3
python -X utf8 tools/validate_etm_direct_offline.py --record docs/validation/zl006-cpp-stage1-20261102/f103-large-input --buffered-diff --out build/algorithm-diff-new
python -X utf8 -m unittest discover -s tools/tests -p test_etm_algorithm_pipeline.py
python -X utf8 -m unittest discover -s tools/tests -p test_etm_benchmark_guard.py
etm-service/build-native/etm_storebuild.exe --self-test-shared-tracker
etm-service/build-native/etm_storebuild.exe --self-test-replay-cache
```

API基准仍保留其服务供检查；用完仅关闭该工具进程，再启动下一组。禁止并行性能任务。中位≤10秒、全部轮次≤10秒、冻结EXE耗时与真实硬件Web E2E是不同门禁；后两项不能由本轮源码API时间代替。实时分析及更大的窗口/输入仍需后续工作。
