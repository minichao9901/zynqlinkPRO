# ZL-144：双击EXE没有自动打开浏览器

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

日期：2026-11-04。本轮只修改主机交付；没有加载固件、连接目标或写Flash。

## 根因及同字节对照

`E:/zynqlinkPRO`目录具有可继承的Low Mandatory Level标签。构建/复制出的EXE继承该标签，启动进程的完整性RID实测为4096（Low）。Chrome子进程返回`0x80000003`，Edge返回21；调用桌面COM则被拒绝访问。源码Python进程RID12288，源码自动打开正常，不能代替冻结验收。

按用户要求关闭全部Chrome/Edge后，原交付EXE在8932仍出现服务正常、CLI页面未连接（HTTP409），与此前8895/截图8893病例一致。残留浏览器进程不足以解释原故障。

决定性对照使用原交付EXE，SHA-256始终为`1ae6ed71abac01386db708e09e3cb0bc99f5149e388882bed3a58906be2612d7`：仅对该文件设置标准Medium完整性标签，关闭全部浏览器后，以8954/独立数据目录启动，进程为RID8192，原有`webbrowser.open`即自动打开工作台，真实浏览器CLI返回`ready=true/hardwareAccessed=false`。EXE字节和浏览器调用代码均未改变。

这符合[Microsoft的MIC说明](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control)：新进程采用用户与可执行文件完整性级别的较低者。

## 最终修复

- 构建候选和发布副本分别对启动器EXE设置Medium标签，避免复制到固定dist后重新继承Low；仅调整该交付文件的标签，工作区/系统其他标签及DACL不变。
- 冻结预检报告进程完整性RID，构建拒绝发布低于8192的候选；发布标签设置失败时回滚程序并保留用户data。
- 自动打开浏览器的启动路径发现Low完整性时给明确错误，提示从普通用户目录重新解压或重新发布。`--no-browser`、离线Trace CLI仍可按原有用途执行。
- 保留原有默认浏览器调用，移除未奏效的Chrome/Edge直启、DLL环境转发、PowerShell和COM代理方案；最终包不新增pywin32依赖。

10项桥服务/发布测试通过，包括新增的标签设置失败回滚及数据保留测试。

最终交付源码`5e20c77192ddc5acbed3501fb0190836e1cbef7a`，manifest的`sourceDirty=false`。固定`dist/zynq-etm-bridge/zynq-etm-bridge.exe` SHA-256为`90fc8d1c04d331cb80fd29aff0c7545251d99b779a5d0f8c6ee6377723d3ed82`，文件标签Medium；工作区目录仍保持原Low标签。身份及构建验收见[delivery.json](delivery.json)。

- 冻结预检和F103/H743双协议离线记录/导出验收通过，子进程PATH无Python/Node，硬件路径禁用。
- 每次前后关闭全部Chrome/Edge，8970、8971两个独立数据目录冷启动均自动打开，真实页面CLI `ready=true`，进程RID8192，见[frozen-acceptance.json](frozen-acceptance.json)。最终冻结程序8页45条CLI回归通过，见[web-cli-summary.json](web-cli-summary.json)。
- 固定入口不带任何参数启动（8882、默认data）同样自动打开并返回`ready=true`、RID8192，见[default-acceptance.json](default-acceptance.json)。现有data已保留；该目录records为空（0文件），未声称完成有业务记录的数据保留对拍。
- 复制相同最终EXE字节到继承Low标签的隔离测试文件，自动启动明确返回1并提示低完整性，未创建数据目录或启动服务，见[negative-acceptance.json](negative-acceptance.json)。
- 全部浏览器及本任务测试服务已停止，未留下本任务后台进程。

关闭原浏览器后在同一服务内强换CLI页面的夹具曾等待超时：既有队列永久绑定首worker，新的worker被409拒绝，协议提示需关闭服务后更换。此项属于原有单执行页面契约（ZL-090），不能据此认定浏览器未打开；修正验收为每轮重启服务/浏览器，保留该失败。未修改队列接管策略，也不声称支持更换页面接管。

## 对照与失败证据

此前候选ce4c150、9244760、72b7d44、5d9157e、2529d3c、f93f99a、ca982be都未通过原Low标签条件下的完整自动启动验收。源码成功、HTTP服务可用、系统Shell接受请求、COM调用成功返回或单个浏览器进程返回0均未用作关闭依据。打开线程的假设未得到验证；后续栈显示服务与线程仍正常运行，主要失败在浏览器子进程与桌面权限。

一次候选发布因本任务测试进程占用dist而失败，原程序保留；停止自有测试进程后重新构建。原始输出保留在`build/bridge-browser-fix-build*.txt`和`build/bridge-browser-fix-20261104/`，运行时含本机令牌，不提交。

只读查看了`E:/superlinkPRO/web/bridge/etm/etm_bridge.py`及其打包器：它也使用普通`webbrowser.open`，未发现需要照搬的特殊启动补丁。其仓库目录同样具有可继承Low标签；用户实际运行的解压目录/EXE标签未核对，不能把用户日常正常启动直接当成本轮同路径实测结果。未修改superlinkPRO文件。

Windows UI工具因不能可靠确定浏览器URL停止操作；业务验收使用真实浏览器执行的公开CLI及页面状态。后续对照按用户要求在每次测试前后关闭Chrome/Edge。
