# ZynqLinkPRO v1.3.16 调试器 RTT 终端验收

2026-11-18。构建源码 `283ad0c54f84b88aca3f88f69c4040af46dd979d`，Pages 静态提交 `7b312e6f266bb0978e60b025135cb86d8c60e664`。Pages 和 Windows 包的 Web 构建时间为上海时间 10:52:04 和 10:52:10。关联 ZL-263。

调试器 RTT 使用下行通道 0 接收键盘和粘贴输入，由目标返回回显与响应。独立轮询在调试器运行和停机期间持续读取。勾选「连接后自动开始」时，等待 ELF 符号和固件初始化控制块。只有上行通道的固件继续显示日志。

## 验证

- 源码、Pages 静态候选、冻结 EXE 候选、固定路径 EXE 和公开 Pages 均经过浏览器模拟目标。核对晚初始化、自动刷新、键盘实际字节、跨环尾、粘贴、满环提示、UTF-8、ANSI、清屏、停止和重连。 [回归入口](../../../tools/verify_debugger_rtt_browser.py)
- 207 项 Web 测试、111 项 CLI 测试、177 个 Web 模块语法和共享驱动一致性检查通过。冻结包通过 F103ZE 和 H743 保留记录的离线验收。固定 EXE 从固定路径启动，点击可执行手册的 QSPI 离线预检通过。
- 开测时 USB 枚举到 akaLinkPro，未发现 ZynqLinkPRO 调试会话。D/V 仅完成主机与模拟目标专项，S/F/R/J/E 和实板 D/V 未执行。ZL-263 实板待验。

## 分发

- 固定 EXE 路径为 `dist/zynq-etm-bridge/zynq-etm-bridge.exe`，SHA-256 为 `0ab3aa03c7e4f8f20d05abd1300c2b3f1481614acd66cecdbe819998f23ee755`。更新前后 451 个用户数据文件的 SHA-256 一致，旧程序与 ZIP 已归档。
- Windows ZIP 为 56,222,683 B，SHA-256 为 `cbd1a58a905a17eebb1dde9dcc0bfa55f05f99afe760005a3d8c754a6304731a`。匿名完整下载后核对 `SHA256SUMS.txt` 及 1,892 个包内文件。Release 标签和包来源均指向构建源码。
- 公开 Pages 的站点清单、入口和相关前端文件与静态候选一致。发布 API 当轮有 TLS 中断，匿名浏览器中的下载卡显示「最新发布」，其链接已核对跳转到 v1.3.16 的 ZIP。Release 上传中断后复用同一草稿，核对 ZIP 和校验文件后公开。 [线上工作台](https://minichao9901.github.io/zynqlinkPRO/#dbg) · [工程下载](https://minichao9901.github.io/zynqlinkPRO/#download) · [GitHub Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.16)

完整本机证据保存在 `build/workbench-v1316-rtt-20261118/`。
