# ZL-006：历史“1秒接近10秒解码”核实

**历史快成绩确实存在，当前代码重跑同一旧输入仍接近10秒。** 本次三次离线完整API处理中位：旧输入8.238秒，当前大输入22.031秒。不能把“同样录1秒”当成同等处理规模：旧547万条路径、当前1957万条，约3.58倍。此次没有发现将同一旧输入从约7秒拖到20～30秒的迁移回退；当前大记录的处理性能仍未达到10秒，不关闭ZL-006。

本次只读取历史/当前输入、superlinkPRO及本项目代码/二进制，并在新目录离线重建；未接触板卡、PLL、Flash/QSPI、RTL或PS固件，未实施性能优化。

## 历史记录核对

1. [统一验收文档“C++原生默认链路与同一份1s数据离线复测”](../../F103ZE-Web-CLI-ETM统一验收-20261031.md)：同一6MHz TRACECLK旧输入，三次完整API处理7.955/7.208/6.832秒，中位**7.208秒**；服务解码/建库中位6.457秒，完整任务7.149秒；浏览器首屏另221.5ms。原文8.43秒是串行相加估算，不是实板E2E。
2. [冻结EXE原始验收](../etm-ddr-usb-bridge-exe-20261101/offline-result.json)：相同F103旧输入，5,467,740条路径，解码/建库**5.898秒**；没有逐指令JSONL。它不是最新24MHz大记录。
3. superlinkPRO的`docs/etm-1s-hardware-checklist.md`中“1秒完整处理≤10秒、争取5秒”是门禁目标；`docs/etm-1s-release-20261023.md`及对应真机报告实际记录H743约1836万条、**14.109～14.350秒完整处理**，不含采集/回传/保存；同报告请求到任务完成约24.7～24.9秒。不能把该门禁目标或14秒处理说成全流程≤10秒。

因此“接近10秒”有本项目旧F103数据的实际证据，也与原生链路目标有关；不能统一解释为任意芯片/时钟/负载的1秒新输入都已达标。当前5.89MB记录与旧1.36MB夹具也不能直接作迁移性能对照。

## 真正不同的输入规模

| 项目 | 历史旧1秒夹具 | 本轮选取的当前1秒记录 |
|---|---:|---:|
| 输入ID | `capture-1419738de1e7417bb0d8a34346823242`的Git固定夹具 | `capture-e61a64f34d0047e4a9c1c617b87099e1` |
| 目标配置 | SYSCLK48MHz、AHB/4 → **HCLK12MHz** | SYSCLK48MHz、AHB/1 → **HCLK48MHz** |
| TRACECLK | 6MHz | 24MHz |
| ETM输入字节 | 1,363,722 | 5,892,279（4.32倍） |
| 路径/指令记录数 | 5,467,740 | 19,565,799（3.58倍） |
| 原生中间件`native.bin` | 360,776,440字节 | 1,305,247,716字节（3.62倍） |
| 完整API处理，本次3次中位 | **8.238秒** | **22.031秒** |
| 服务内解码/建库，本次3次中位 | 7.321秒 | 19.879秒 |

目标Flash ELF相同，SHA-256 `e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f`，但运行分频和业务负载不同。旧输入保存的`RCC_CFGR=5308570`、`hclkDiv=4`；当前为5309450。用仓库`completeClocks()`按HSE8MHz重算，分别得到12/48MHz HCLK与6/24MHz物理TRACECLK；不是本轮重新设置目标时钟。

旧ETM SHA-256：`2cb5838887188cbdebf554967281ad44f03eca9aab2867cde82e548ca9873199`；当前为`3b54995365d440cb154c8249b2fc2a0319d9ccb42c2460b3ca861550c421ea78`。旧窗口按历史host monotonic计量，当前DDR窗口按硬件ticks计量；规模比较使用确定的输入字节和完整路径记录数，不靠“1秒”标签推断相同负载。

## 本次离线复测方法与完整结果

复用`tools/prepare_etm_offline_fixture.py`恢复Git内旧输入，并用`tools/bench_etm_native_offline.py`对两份输入各建3个全新记录。每次复制raw/ELF/源码/元数据，**不复制原native.bin或派生store/索引**，执行真实后端decode API，计到建库、默认查询/浏览准备和任务完成；不包含硬件采集、复制输入或浏览器绘制。

| 输入 | 三次API完整处理 / 秒 | 三次服务解码/建库 / 秒 |
|---|---|---|
| 历史旧夹具 | 8.667 / 8.238 / 6.559 | 7.321 / 7.480 / 5.909 |
| 当前大记录 | 22.749 / 21.712 / 22.031 | 20.444 / 19.565 / 19.879 |

六次均`engine=native / fallback=false`、无大JSONL中间件；全部summary与原结果相同，共有quality字段相同，原输入SHA不变。旧输入保留2个gap、89591条未知执行，当前保留2个gap、522998条未知执行；没有为计时将这些状态归零。此处验证重建一致，不冒充全执行流无未知或严格质量门禁全绿。

两个性能服务串行运行并在完成后关闭。OS磁盘缓存未清空，ELF准备缓存可能命中，不称三次冷启动，也不按比例外推成某个保证时间。旧输入本次API8.238秒与历史7.208秒有波动，但仍在近10秒量级；不能由此推出所有输入均无任何回退。

## 慢在哪里：不是OpenCSD单项花了24秒

新记录复测的中位分项：

| 阶段 | 旧输入 / 秒 | 当前大记录 / 秒 |
|---|---:|---:|
| OpenCSD | 0.884 | **1.888** |
| Store构建及索引整体 | 6.248 | **17.976** |
| 其中C++ nativeBuild | 1.911 | 6.356 |
| 其中queryIndex/default views | 1.752 | 4.711 |
| 其中assemble/publication组装 | 0.516 | 2.351 |
| 其中输入bindings/hash | 0.539 | 1.229 |

“其中”是嵌套阶段，不能与整体重复相加；不同分项的中位也未必属于同一轮。原12轮1/10MHz板测中，OpenCSD中位2.451秒、storeBuildAndIndex22.175秒，才构成约24秒的`decodeSeconds`。这个指标包含整个解码/建库过程，并非只运行ETM解码器。

当前5.89MB ETM展开为约**1.305GB原生二进制中间件**，随后建库、索引/默认视图、组装和完整性绑定会处理这些数据。最终store约84MB不能当全过程数据量。源码定位：`etm-service/tools/native_pipeline.py`第116行先核对native SHA，第142行执行builder，第173行构建索引，第228行组装store，第231～244行绑定/校验输入；这是现有流水线的实际工作，不能只用OpenCSD约2秒代表完整解码。

当前完整E2E约32.6秒还包含目标准备/恢复、固定1秒采集、采后USB/解复用及首屏等；这些不在本次22.031秒离线处理计时内。不能将32秒直接与旧7秒处理比较，也不能拿本轮较快的离线时间冒充E2E提速。

## 迁移实现与二进制核对

本机`E:/superlinkPRO/etm/build-native/`与本项目五个共有原生工具逐一SHA-256相等：`etm_decode`、`etm_storebuild`、`etm_index`、`etm_frontend`、`etm_export`。完整哈希在`audit.json`。新增FRM1工具不属于此五个共有文件。

核心`native_pipeline.py`、`native_facts_index.py`、`trace_store_index.py`、`trace_store_write.py`、`decode_stream.py`、`decode_trace.py`字节相等。`native_storebuild.py`的差异仅将临时JSON输出放到可写记录/工作目录，解决Windows临时路径问题；差异原文一并保存。这证明本次核对的核心执行文件相同，且没有旧JSON路径回退；不构成对所有历史版本、所有机器或所有输入的性能等效证明。

## 对ZL-006的修正与后续定位边界

- 问题保留：24MHz TRACECLK的大输入仍需约20～24秒完整处理，总E2E约32秒，尚不能承诺≤10秒或持续实时显示。
- 归因修正：现有证据优先支持**输入/路径规模增大+建库/索引主导**，不是“同一旧1秒输入迁移后退化到30秒”，也不是SWD线速或OpenCSD单项30秒。
- 如果继续优化，固定当前5.89MB/1957万条输入和质量语义，优先分析builder、数值索引/默认视图、组装和大中间件重复读取/hash；不能通过降目标/TRACECLK、缩窗、少算路径或关闭完整性检查来制造原来的10秒成绩。本轮未实施这些优化。

## 证据与复测

`audit.json`保留逐轮统计、规模、引擎/源码指纹和历史分项；`raw/legacy-results.json`、`raw/current-results.json`为完整结果，其他原始摘要/manifest与工具快照见`evidence.json`。本机大中间件在`build/zl006-audit-20261101/`，原记录和superlinkPRO工作区未修改。

```powershell
python -X utf8 tools/prepare_etm_offline_fixture.py --out build/zl006-repeat-new/legacy-input
python -X utf8 tools/bench_etm_native_offline.py --record build/zl006-repeat-new/legacy-input --out build/zl006-repeat-new/legacy-bench --port 8897 --repeat 3
```

此工具启动禁用硬件路由的本机离线服务，看到`OFFLINE_BENCH_READY`且3轮结果完整后关闭本任务服务，再对当前记录用另一新目录串行复测；不得覆盖原输入或并行跑两份性能测试。
