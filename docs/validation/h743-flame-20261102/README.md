# H743 CDC初始化与单次echo：执行顺序SVG

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

按用户要求使用Web共用的原生区间SVG导出实现，`--flame-mode timeline`。没有聚合、分桶或删除调用深度，也没有对SVG内容做自定义渲染改写。横轴是原始执行序号，表示先后顺序，不是逐指令精确时间。

- CDC初始化：执行顺序火焰图（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/h743-flame-20261102/CDC初始化-执行顺序火焰图.svg`）：seq **7～42571**，925个连续调用段、14层；从 `cdc_acm_init` 首指令至其return，下一条回到main，覆盖该函数及内部USB控制器初始化。
- 一次echo：执行顺序火焰图（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/h743-flame-20261102/单次echo-执行顺序火焰图.svg`）：seq **7782088～7784098**，60个调用段、10层；USB OUT接收中断→main数据复制/`cdc_write`→`handle_command`及原有日志→USB IN完成中断返回。包含真实日志开销、未知祖先/未知函数和中断间隙。

两个文件与对应英文原生导出文件逐字节一致，SHA和尺寸见 `svg-manifest.json`。原生导出为保留完整函数名会生成宽图：初始化4086272px、echo约59022.674px；保留ZL-012所述超宽边界，需下载后缩放或横向查看。

## 新记录与边界证明

已有性能记录不含初始化。本次不写Flash/QSPI，先核对已加载release探针OCM与目标ELF，再保存FPB/DEMCR，通过SYSRESETREQ与复位向量捕获停在 `trace_hook_entry`（CDC初始化之前），移除临时断点，调用现有连续capture入口。这个诊断准备脚本不是把生产H743 CLI entry/reset参数标为已支持。

目标为H743 Golden CPU/HCLK60MHz、TRACECLK20MHz，SWD10MHz，GPIO速度2、ETMv4 CONFIGR0x1011。硬件窗口2秒完整，parser/frameDrops/readyLoss/writer错误0，OpenCSD packetIssues0。主机在枚举后只发送一次 `H743_SINGLE_ECHO_20261102_001\r\n` 并收到逐字节匹配回显；时间戳位于硬件窗口内。整份记录内 `cdc_acm_init`、CDC bulk-out回调、`handle_command` 各只有一次入口，见single-call-checks。

初始化入口地址0x08000b7c；目标ELF SHA `246640bf79c8b1e568441a286812326dfb0ae68a0df061a0c023262c07cf221b`。完整调用深度按trace重建，未知祖先标记原样保留，不伪造复位前调用栈。

```powershell
python -X utf8 toolbox.py trace export --record build/h743-flame-20261102/corrected/init-single-echo --format flame-svg --from-seq 7 --to-seq 42571 --flame-mode timeline --out build/cdc-init-timeline-new.svg
python -X utf8 toolbox.py trace export --record build/h743-flame-20261102/corrected/init-single-echo --format flame-svg --from-seq 7782088 --to-seq 7784098 --flame-mode timeline --out build/echo-timeline-new.svg
```

Web `server.py` 的flame-svg下载和Trace CLI均直接调用 `flame_svg.export_svg`。本次执行的是上述CLI共用实现，不声称通过浏览器按钮导出。

## 修复与恢复

首轮硬件数据及echo正确，但恢复断言把RCC_CR.D2CKRDY（只读bit15）从0变1误判为改频。已修复ZL-071：仅在配置比较中排除D1/D2只读就绪位，保留原始寄存器、所有PLL/振荡器控制及其ready位和分频的严格检查。2项针对性测试与5项H743采集清理测试通过，独立重做初始化采集成功；首轮失败不删除。

采集脚本收尾核对FPB与DEMCR恢复、目标运行、ready=1。随后00:16:42上海时间只读复核时设备已不可达。用户随后明确板卡不再供本会话使用；已停止一切板卡访问，不将这次不可达计为项目新增故障复现，也不再尝试复核或恢复。已落盘记录与SVG不受此后链路丢失影响。没有遗留本任务采集/串口刺激进程。

`raw/`保留失败/成功原始formatter、ETM、匹配ELF、解码摘要、序号边界、单次echo与恢复证据；派生native.bin/store缓存留在build，不重复提交。`metadata.json`与`evidence.json`记录身份、范围及哈希。问题表同步更新；本地提交，不推送。
