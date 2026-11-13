# 工作台版本与构建信息验收

2026-11-13，工作台右上角的「帮助 → 版本与构建信息」显示 Web 版本、构建时间以及探针版本、编译时间。桌面包和静态站点的构建流程各自在输出中的 Web 模块写入 UTC 构建时间。源码模式显示未打包。

- 实板原正式 J7 QSPI 固件经 Chromium 和本机 HID 读到 `0.6-nonce32`，编译时间显示「当前固件未提供」。
- 同一 PL 配对经 JTAG/RAM 加载 [新增时间字段的 PS 固件](../../../prebuilt/j7-probe-fw-info-20261113/README.md)。物理 MEM-AP0 验证 85,828 字节 OCM 执行代码，FCLK 按寄存器推算为 133,333,332 Hz。真实 Chromium 通过本机 HID 读到 `0.7-nonce32` 和 `Nov 13 2026 20:51:50`，与构建机本地编译时间一致。
- 验收后从原正式 QSPI 镜像复位恢复。BOOT 读回及正式 PS ELF 的 85,844 字节 OCM 执行代码一致。原始记录在本机 `build/probe-fw-info-20261113/`。关联 ZL-206。

固定入口已更新为 Web v1.3.3，原 data 目录保留。冻结包验收和 Chromium 实机显示复验均通过。窗口显示的 Web UTC 时间与包清单中的 `2026-11-13T12:56:10+00:00` 一致。静态站点离线生成并核对时间模块的 manifest 哈希。159 项 Web 自测、164 个模块语法检查和探针生产 C 状态机测试通过。

随后按用户要求，将同一 `0.7-nonce32` ELF 与同一 J7 bit 重包并固化。使用 `--skip-backup`，实测 4,281,040 字节 BOOT 写后及实体冷启动后两次读回均一致。用户断电重上后先通过 JTAG 独立核对 85,828 字节 OCM 执行代码和自主启动交接，再由已安装的 Web v1.3.3 实读固件版本和编译时间，均与构建值一致。最终探针在 QSPI 模式运行，已确认空闲。验收覆盖 BOOT 区和启动流程。[QSPI 镜像与验收](../../../prebuilt/qspi-probe-fw-info-20261113/README.md)

## v1.3.3 公开发布验收

静态站点和 Windows x64 便携包均从干净的 `93074a77bc4af063d0846d4b6b6f563f393cd7c4` 构建，Release 标签指向同一提交。两份产物各自写入 Web 构建时间。发布阶段未访问板卡。

- Chromium 匿名打开公开工作台，点开「帮助 → 版本与构建信息」，显示 `v1.3.3 (OpenOCD Wasm)` 和 `2026-11-13 13:09:54 UTC`。线上首页、构建标记、详情模块、OpenOCD Wasm 及站点清单的 SHA-256 与暂存文件一致。部署提交为 `f01e4de10145884926e5e4a6eb29f3f4284ff499`。[在线工作台](https://minichao9901.github.io/zynqlinkPRO/) · [Pages 部署](https://github.com/minichao9901/zynqlinkPRO/actions/runs/43431913530)
- 首次访问静态站点时，在详情模块初始化前点击按钮未打开窗口。等待页面初始化完成后，用新浏览器会话重验，点击成功。
- Windows 冻结包验证了清单中的 1,886 个文件并通过 F103 和 H743 的离线 Trace 验收。独立启动发布候选，Chromium 显示同一版本及 `2026-11-13 13:10:02 UTC`。日常 EXE 和发布候选的本机页面均显示 27 条手册命令，点击 QSPI 预检均得到退出码 0。静态工作台隐藏依赖本机 CLI 服务的手册页签。[公开版本说明](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.3)
- 发布草稿完成上传后，使用 Pages 下载入口指向的匿名地址完整下载 56,192,787 字节。下载文件、本地 ZIP、GitHub 资产 digest 及公开 `SHA256SUMS.txt` 的摘要均为 `5435d1b463fae49b4fe9f9ee273b0e2084a5df871141a69833db49cefb4643d5`。首次大包上传超时，在同一草稿中通过保留 TLS 校验的 DNS 地址重试，去掉 `Expect: 100-continue` 后上传完成。关联 ZL-164、ZL-205、ZL-206。[Windows x64 ZIP](https://github.com/minichao9901/zynqlinkPRO/releases/download/v1.3.3/zynq-etm-bridge-win64.zip)
