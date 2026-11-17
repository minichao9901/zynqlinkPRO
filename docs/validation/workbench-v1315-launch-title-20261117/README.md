# ZynqLinkPRO v1.3.15 启动提示验收

2026-11-17（上海时间）。ZL-262 的 Windows 手动访问提示标题已改为 `ZynqLinkPRO`。v1.3.15 由干净提交 `408d0b5190e4166ea335332fb2bc3073e2bde88a` 构建。

在源码中模拟浏览器交接失败，确认标题和去掉令牌的本机访问地址。另从 v1.3.14 和 v1.3.15 冻结 EXE 提取相同的启动失败处理函数，在受控失败时调用真实 Windows `MessageBoxW`。读取对照包标题 `SuperLinkPRO` 和新包标题 `ZynqLinkPRO`，新包正文显示 `http://127.0.0.1:8912/`。窗口由验收进程关闭。

207 项 Web 测试、111 项 CLI 测试、冻结包预检和 F103ZE/H743 保存记录离线解码通过。固定 EXE 已更新，旧程序和 ZIP 已归档，安装前后 451 个 `data/` 文件的哈希一致。

固定路径 `dist/zynq-etm-bridge/zynq-etm-bridge.exe` 的 SHA-256 为 `88afd783e9a8d4d181420f0449876ab1489082e50b59a39e5847f089eea361dc`，与弹窗验收的冻结候选一致。固定程序离线启动后，普通权限 EXE（RID 8192）自动打开 Chrome，页面 worker 就绪。再次启动复用相同服务。可执行手册的 QSPI 离线预检通过。

GitHub Pages 静态提交为 `d92500f3945d250d1006def698ab58a1758df23b`。匿名浏览器显示 v1.3.15，比对了 217 项站点清单、HTML 和 7 个前端文件。工程下载卡指向 v1.3.15 的 Release 和 ZIP。公开 QSPI 0.8-nonce32 清单及 15 个文件校验一致。[线上工作台](https://minichao9901.github.io/zynqlinkPRO/#download)

Release 于上海时间 20:21:12 发布，标签指向构建源码。匿名完整下载 Windows x64 ZIP，核对 56,222,690 B、SHA-256 `e429cabc3fa965f719a79eb3b75747f857b31247b16ee80a500a49ffb20b1d7d`、`SHA256SUMS.txt` 和包内 1,892 个文件。本机原始证据在 `build/workbench-v1315-title-20261117/`。[Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.15)

本轮为主机侧验收，未访问探针、目标板或 Kingst。S、F、D、V、R、J、E 七组实板用例留待以后，ZL-261 继续实板待验。
