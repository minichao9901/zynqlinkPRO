# 日志查找、过滤与高亮

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

2026-11-02（Asia/Shanghai），codex/web-ui-compact，基于f659909。关联ZL-102、ZL-105。

## 行为与边界

- 串口助手、RTT Viewer、RTT转发共用“查找”入口，Ctrl+F可打开；关闭或Esc回到原接收显示。搜索栏仅按需占用空间，保留单行顶栏与设置收起布局。
- 支持字面匹配、大小写选项、只看匹配行、上下处/Enter/Shift+Enter定位；标记用DOM textContent构建，不执行日志中的HTML。
- 检索最近128 KiB保留字节，跨USB包拼接后UTF-8流式解码，再过滤整行；文本模式忽略ANSI控制序列与显示时间戳，HEX模式按字节展示。不是xterm终端画面的逐像素搜索，也不是完整磁盘记录检索。
- 默认检索快照，显式标记“快照”；可手动刷新或开启500ms实时更新。不可见页面不刷新，原高速停显保护生效时暂停实时检索，仍允许用户手动刷新；没有新数据不重复重建DOM。
- 最多高亮1000处，数量超出时明确提示；原始缓冲、导出、持续记录和接收状态不受过滤影响。窗口截断处可能缺少完整行/多字节字符上下文。

## 验证

- 新增4项核心测试：跨包UTF-8/关键词、字面字符与大小写/行过滤、ANSI与OSC/窗口/HEX、1000处高亮上限及Unicode位置。检查原字节不变。
- 全部Web自测98/98通过；CLI55/55通过；web.check共享驱动10份一致、145模块语法通过。
- 浏览器内置串口演示：心跳匹配、过滤后上下处1/19→2/19、实时更新与接收计数继续增长；实际“导出缓冲”文件仍含被过滤的设备说明与心跳（未修改保存路径）。
- 用模拟串口发送`<b>ERROR_LITERAL</b>`，检索`<b>`结果显示字面文本，检索结果中的b元素数量为0，无HTML执行。

本轮只使用内置演示/模拟数据及离线验证，没有访问真实板卡。后续完整文件索引、正则、命名规则与跨页目标/ELF上下文复用不在本批范围。

## 浏览器补充与程序交付

串口实时匹配从171处增长至254处；RTT转发通过共享模拟串口检索到258处。RTT Viewer使用内置mock与`addr=0x20001000`：`info`不区分大小写检索94处，勾选区分大小写后无匹配（源为大写INFO）；结果区Esc关闭、顶部入口获得焦点时Ctrl+F打开均通过，清空接收缓冲后检索同步为0 B/0处。控制台无error。截图：串口检索（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/log-search-20261102/serial-search.png`）、RTT检索（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/log-search-20261102/rtt-search.png`）。

本worktree中的`dist/zynq-etm-bridge/zynq-etm-bridge.exe`已重建，旧程序归档并保留data；原E盘工作区程序未更新。EXE SHA-256：`572d08e409089858d609e23c70606a742e7ab1bc8a83ef3c0e9bcf45bf1ccbcb`。

[冻结程序离线验收](frozen-verification.json)通过：1792个包文件、禁用硬件路由、F103ZE/H743离线解码/索引、Web/CLI HTML导出一致及重复启动复用。[源码核对](source-package-match.json)确认4个本次前端文件与包内字节一致。构建记录为f659909基线加sourceDirty=true，以文件SHA绑定实际源码。

收尾已断开模拟RTT、关闭测试页、停止源码服务；PID28324不存在，8898无监听，冻结验收keptRunning=false，无本任务遗留后台服务。
