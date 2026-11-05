# 1秒ETM端到端时间：SWD 1 MHz / 10 MHz

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

结论：12轮正式对照均通过，但没有测出稳定的E2E缩短。每档6次合并中位为32.578/32.734秒，10MHz反而多0.156秒（0.48%，远小于本次运行波动）。控制交换累计时间中位从2.758降至2.274秒，减少0.484秒/17.6%。不能把控制段收益等同于整个采集/解码流程的收益。

按用户要求，ETM网页、Trace CLI、直接采集入口及本地采集服务的默认SWD已统一为10MHz，并在USB交接和恢复连接时保留所选频率。仍可显式选择1MHz。未修改RTL、Zynq固件、CPU/TRACECLK或目标Flash/QSPI。

## 文档历史数据核对

[统一验收文档](../../F103ZE-Web-CLI-ETM统一验收-20261031.md)中的时间有不同边界：

- “采集长度与处理时间”：1秒全流程268.11秒，是旧JSON链路、F103 48MHz/AHB /4、TRACECLK6MHz；后续已明确更换原生默认链路，不能当作当前1MHz对照。
- “C++原生默认链路与同一份1s数据离线复测”：7.208秒为同一旧1秒记录的离线处理；8.43秒是相加估算，不是实板E2E。
- 最新寄存器批量A/B的中位7.275秒，对应100ms采集，而非1秒；当时实测SWD约1MHz。

因此本轮在当前同一配对上重新测1秒的1/10MHz。没有以268.11秒或离线处理时间计算提频收益。

## 配对与方法

本轮明确重新加载`prebuilt/fclk133-release-20261101/`并独立读回OCM可执行段匹配。bit SHA-256 `af1031d3caa0d7bd3b6adffa911d26efdab9e0bfb5223fb18f70dabb70ebeeed`；ELF SHA-256 `2137f7d0f507c08574f36223130103c0710645cbfdefb5c1d8c8efb0cfb990a0`。这是此前Git中的已验收配对，本轮没有重建PL/PS。来源/构建选项/既有STA见其manifest及[上一轮报告](../performance-limits-20261101/README.md)。

F103ZE Golden CDC48 ELF，SHA `e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f`。目标Flash逐段只读核对；HCLK48MHz、TRACECLK24MHz、HSE8MHz，入口统一cdc_poll，64字节CDC持续刺激。每轮有约5.89MB有效ETM，硬件窗口1秒，默认DDR采后USB下载、OpenCSD binary、C++ TraceStore/索引，无逐指令JSONL。

普通DAP策略在这两档均使用实读FCLK119999998Hz；配置阶段精确SWD回读约999999.983/9999999.833Hz。接管后的采集质量字段分别报告999/9999kHz（固件整数截断）。全部轮次都核对前端回读频率与采集服务频率，没有暗降档。

计时复用既有`stress_etm_web.py`：从点击“联动采集”到完整解码、首屏显示、目标恢复和控件重新可用，再做原始结果检查；包括开始按钮内部的ELF校验、入口准备、时钟核对与ETM配置。初次连接、预先添加断点、文件上传和最终断开单列，不在E2E计时内。控制交换累计时间包含HTTP/USB/命令执行，不是纯SWD线速时间。

先做1/10MHz交错三对，再因明显波动追加同条件三对。两批没有改源程序/原生引擎或删除异常值；追加测量是时间重复性检查，不是失败重试。各档均6次，12轮loss=false、packetIssues=0、RCC恢复、清理无错误；每轮硬件窗口内至少59次完整精确CDC回显。

## 时间结果

| 批次 | 1MHz E2E中位 | 10MHz E2E中位 | 观察到的减少量（1M−10M） |
|---|---:|---:|---:|
| 第一批，各3次 | 49.968 s | 44.084 s | +5.884 s |
| 追加对照，各3次 | 30.759 s | 32.473 s | −1.714 s |
| 全部，各6次 | **32.578 s** | **32.734 s** | **−0.156 s** |

1MHz全部范围30.324～51.521秒；10MHz31.677～53.219秒。第一批看似省5.88秒，追加对照没有重复这个方向，不能据此宣称SWD提频让E2E稳定提升11.8%。

| 全部轮次的分项中位 | 1MHz | 10MHz | 解释 |
|---|---:|---:|---|
| HTTP/USB控制交换累计 | 2.758 s | 2.274 s | 少0.484 s，17.6% |
| 原生完整解码/建库/索引 | 24.393 s | 24.661 s | 主要耗时，范围约21.85～42.05 s |
| 固定硬件采集窗口 | 1 s | 1 s | 不因配置SWD提频而缩短 |

各分项中位来自不同轮次，不能相加冒充一个真实E2E。当前没有证据把原生处理波动归因于SWD；提高配置时钟不改变OpenCSD/TraceStore算法。默认10MHz的依据是本板功能验收和配置段耗时降低，不能承诺整个流程因此减少固定秒数。

## 默认值与交接修正

原页面连接与恢复、Trace CLI、直接采集和Zynq Session中分别存在1MHz默认值。仅修改页面时，本地服务接管USB仍会用1MHz，最初探索性`ab/`的6轮正是这种混合状态，未纳入上述正式比较。

当前页面把所选`swdHz`传给采集任务，server/Vis/Session按该频率建立连接，恢复连接保持原选择。配置默认10MHz，显式1MHz对照仍保留；CLI发现已有连接频率不同会明确拒绝，要求先断开，避免把当前频率冒充请求频率。

第一次接管修正测试在采集前发现内嵌`dap_pipeline_bench.py`缺少新精确Hz接口，导致启动失败；错误记录在`ab-full-clock/`。同步支持精确Hz和时钟ACK核对后，才进行了两批正式对照。压力工具同时修正了无transport元数据时清理错误覆盖原始异常的问题。失败现场均保留，没有作为通过轮数。

主机验证：81项Web测试、10项相关Python测试、10份共享驱动一致性检查通过。新增检查覆盖默认10MHz、显式1MHz跨USB交接保留、非法时钟拒绝、内嵌DAP精确Hz接口/拒绝ACK，以及CLI已有连接时钟不匹配。

## 本地程序交付和收尾

默认值代码提交`22c92f3385cee779f416df2723f222091430d6e2`。本地程序已重新构建到`E:\zynqlinkPRO\dist\zynq-etm-bridge\`，构建时sourceDirty=false，1794份文件指纹及F103/H743原生离线处理、查询/导出/重复启动等发布前检查通过。旧程序保留在`build/bridge-archive/20261101-200843-f6ece4bd/previous`，没有覆盖或打包用户业务记录。

新EXE SHA-256：`ea74f6f52923b382c2553b5cecf14e7caeb196fd6e1c430d9190e56f19138057`。启动该真实EXE，在新数据目录中不传任何时钟覆盖参数，再做1次1秒Web采集：capture quality回读9999kHz、ETM5892469字节、packetIssues=0、loss=false、RCC/配置恢复、完整CDC回显通过。该单次E2E为29.173秒，仅证明可运行与默认值生效，不混入前面的同条件时钟A/B。

测试服务和临时网页均已关闭，没有后台采集；板上仍为上述release配对，目标运行、采集/DDR/DMA空闲。最终明确设置并回读SWCLK9999999.833Hz、FCLK119999998Hz，目标RCC/ETM/锁状态核对见`raw/final-board.json`；未写QSPI或目标Flash。未推送。

## 复测入口与证据

重新加载并核对上述配对后，启动本机原生探针工作台、在浏览器打开其鉴权URL，使用新的runtime和输出目录：

```powershell
python tools/stress_etm_web.py --runtime <runtime目录> --artifacts <新目录> --rounds 1 --capture-rounds 6 --milliseconds 1000 --functions cdc_poll,cdc_poll --echo --cdc-port COM34 --case-timeout 180 --profile-control --native-exchange on --packed-memory on --register-batch on --control-clocks-khz 1000,10000
```

`comparison.json`保留12轮结果、实际时钟、记录ID/SHA、原生分项与分批/合并统计。`raw/`保留原命令动作、计数、CDC证据、失败和配对身份；本机完整记录位于`etm-service/records/<record-id>`，包括FRM1、ETM、匹配ELF/源码和原生数据库。大原生数据库与payload没有批量提交。没有把本轮F103验收扩展成H743真机验收。
