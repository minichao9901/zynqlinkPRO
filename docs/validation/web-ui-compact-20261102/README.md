# Web 紧凑工作台第一批实现

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

日期：2026-11-02（Asia/Shanghai）。分支 `codex/web-ui-compact`，基于 `e6f26cc` 创建独立 worktree。对应评审及问题 ZL-100、ZL-101、ZL-102。

## 本批行为

- 串口、终端、RTT Viewer、RTT 转发、烧录增加“收起/展开设置”，独立保存各页偏好；收起时在现有工具栏显示配置摘要。复用现有工作区布局，不新建导航栏；单行顶栏、窄边框保留。
- ETM 成功打开记录后默认收起采集设置；用户显式展开/收起优先，重复打开记录仍保留选择。“配套源码设置”会显式展开面板，避免焦点落入隐藏区域。历史质量、源码和分析入口保持可见。
- 串口/RTT/转发统一“暂停显示 / 恢复显示”“导出缓冲”“持续记录”文案，提示接收与持续记录独立于显示；记录失败、落盘和计数逻辑保持原实现。
- ZL-100：RttView 原先在恢复 `rtt.target` 前调用 applyTarget，造成芯片/标签/范围基于ARM默认派生。现在先恢复架构再派生 UI；已保存的自定义扫描范围优先保留。用户切换架构时仍按原流程更新范围。
- ZL-101：HTML 移除字节节点后的重复 B，由 format.bytes 统一输出单位。

## 验证

- `toolbox.py project run web.check`：10份共享驱动一致，153模块语法检查通过。
- `toolbox.py project run test.web`：96/96通过，含新增3项ETM布局生命周期测试：默认历史分析、显式偏好/临时展开、窄屏设置浮层。
- `toolbox.py project run test.cli`：55/55通过。输出有现有依赖弃用及临时文件ResourceWarning，无失败。
- 源码服务8898，不启用native probe。1280×720浏览器：保存的HPM6800/RISC-V配置显示JTAG TCK与对应芯片/范围；手填`0x01241000-0x01242000`刷新保留，随后还原测试前范围。未核对硬件实际下发参数，ZL-100保留部分解决。
- 串口演示模式：0 B、906 B、2.7 KB均无重复单位；暂停显示后计数从906 B继续增长到2.7 KB，按钮显示恢复显示。全部为页面模拟串口，没有打开真实COM口。
- ETM打开版本管理的100ms记录`capture-2579cfda576445a3a7e9b12d8cf76627`，550478路径；默认side-hidden，执行流和源码占满宽度。主动展开后再次打开同记录保持展开。
- 截图：ETM分析（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/web-ui-compact-20261102/etm-analysis.png`）、串口宽工作区（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/web-ui-compact-20261102/serial-wide.png`）。实际浏览器检查不替代实板资源交接/采集回归。

## 后续范围

ZL-102保持部分解决；跨页目标/ELF配置复用、日志检索、命名配置等属于后续批次。本批未改PL/PS或加载配对，没有板卡访问。

## 独立程序交付

`python -X utf8 toolbox.py bridge-build`成功，程序位于本worktree的`dist/zynq-etm-bridge/zynq-etm-bridge.exe`。原目录用户程序和数据未更新。EXE SHA-256：`20e5bdef528b79e89b3e8ca9c4a752da031c30d0a5d0eec6d4a23bafd4dca4e9`。

冻结预检及[F103ZE/H743离线验收](frozen-verification.json)通过，1799个包文件校验、原生解码/索引、Web/CLI HTML导出逐字节一致、重复启动复用通过；硬件路由禁用，PATH无Python/Node。构建时sourceRevision为基线e6f26cc且sourceDirty=true；[9个本次前端输入与包内文件SHA逐字节核对](source-package-match.json)通过，用其绑定本批实际源码，不将基线提交号冒充完整构建来源。

收尾浏览器控制台无error，已关闭测试页并停止源码服务；PID29060/29956均不存在，8898/58812无监听，无本任务遗留服务。测试仅接触内置模拟串口和离线记录。
