# ZynqLinkPRO v1.3.14 RAM 调试同步验收

2026-11-17。将 SuperLinkPRO 的 `8cd8439`、`94d3ec4`、`0fede48` 和 `0c70569` 的工作台改动移植到 ZynqLinkPRO。使用本仓 OpenOCD 传输、RISC-V 会话、Windows 本机服务和发布流程。

- 镜像共用一个选择器。ELF 可按文件地址写入或运行到 `main`，Intel HEX 和 S19 保持镜像地址，BIN 显示加载地址。
- Cortex-M0+ 使用原版 CFG 连接，按向量表及 MSP 预填 SRAM。通用 RV32 使用加载、运行和 BSS 范围。点击「声明 RAM」后才登记。加载前检查地址范围，写入后回读。启动时复用架构调试会话，RAM 临时断点在停止后恢复指令。
- Windows EXE 核对启动浏览器的结果，配置被占用时支持工作台专用浏览器配置。二次启动沿用已确认的同一服务。
- 同步 Nano 系统复位回 Boot ROM、RTT 初始化时机，以及 RTT 转发单向和 RTT Viewer 双向的说明。

### 本轮验收边界

按用户安排，真机验收留到以后。本轮在测试夹具、浏览器模拟目标、冻结 Windows 包和分发入口取证，未访问 USB 探针、目标板及 Kingst。S、F、D、V、R、J、E 七组实板用例均留待以后。探针 bit/ELF 与 QSPI 冷启动证据沿用原配对记录。

共享驱动一致性与 177 个模块语法检查通过。207 个 Web 测试和 111 个 CLI 测试通过。源码浏览器导入实际 Nano ELF，在模拟会话验证 `0x20000000`、`65536` 预填，保留手动值。另验 ELF、HEX 与 BIN 载入、目录命令及回读。RV32 定向测试覆盖独立加载地址、BSS 和临时软件断点恢复。

### Windows 固定安装

干净源码 `c1f90aef9daee5ca4c96e64849e827b8d1dbc5fe` 构建 v1.3.14。冻结包核对 1,892 个文件，F103ZE 和 H743 保存记录的离线解码通过。Windows x64 ZIP 为 56,222,333 B，SHA-256 `75a817c5335d13537691fa8c9b1630751ce1dd62754dca9d09615919722250cf`。

固定路径 `dist/zynq-etm-bridge/zynq-etm-bridge.exe` 已更新。EXE SHA-256 为 `9d3423ce637654fd67f3c9c3a41c79614defb3f33db68e24d35828660ae940b4`。归档旧程序和 ZIP，安装前后 `data/` 的 451 个文件哈希一致。

从固定路径以离线模式启动，普通权限 EXE 与 Chrome 的完整性 RID 均为 8192，浏览器页面 worker 回报就绪。再次启动复用原服务，启动标识相同。普通权限验证覆盖正常打开及健康服务复用。另从固定 EXE 打开页面，使用实际 Nano ELF 重跑镜像流程，并点击可执行手册的 QSPI 离线预检。ARM/SWD 与 RISC-V/JTAG CFG 导入通过，前端将 ARM/JTAG 指向原生 CLI。

模拟 Windows 返回配置目录占用时，回退选择独立 Chrome 配置。模拟自动打开失败时，手动访问提示使用去掉令牌的地址。该失败提示的窗口标题仍显示 `SuperLinkPRO`，待修正。

### 线上工作台与 Release

GitHub Pages 静态提交 `6c9b748a45f276df0264ae57a36bb4ffd0850241`。匿名浏览器读到 v1.3.14、217 项站点清单，并核对 HTML 和 7 个前端文件的公开内容哈希。在线调试页再次用实际 Nano ELF 验证预填、手动编辑、共享选择器及模拟内存读回。[线上工作台](https://minichao9901.github.io/zynqlinkPRO/#dbg)

Release 于上海时间 20:03:29 发布。Git 标签 `v1.3.14` 指向构建源码提交。工程下载卡显示 v1.3.14 并指向该 Release 的 ZIP。匿名完整下载后核对 ZIP 大小、SHA-256、`SHA256SUMS.txt` 和包内 1,892 个文件，与本机包一致。[工程下载](https://minichao9901.github.io/zynqlinkPRO/#download) · [Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.14)

公开 QSPI 链接仍指向正式 0.8-nonce32 配对，匿名核对了清单及 15 个文件。本轮临时工作台服务已关闭。原始回归、版本及文件校验输出保存在本机 `build/workbench-v1314-port-20261117/`。ZL-261 的硬件启动、继续运行进入 Nano `msh` 和资源释放留待实板验收。
