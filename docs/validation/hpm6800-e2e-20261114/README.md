# HPM6800EVK Web 端到端验收（2026-11-14）

源码 `203902be`，本地源码工作台、Chromium 157 与本机 USB/HID/串口桥接，HPM6880 hart0。JTAG TAP `0x1000563d`。服务进程按序列号 `12345678` 限定 zynqlinkPRO J7（COM33）。同 VID/PID 的 superlinkPRO 未连接，产品多探针选择边界仍见 ZL-224。

探针从 QSPI 启动 `0.8-nonce32`。物理 MEM-AP0 核对 85,716 字节 OCM 执行代码，两次一致。使用 [QSPI 配对](../../../prebuilt/qspi-probe-hid-20261114/README.md)，bit SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF `64d00fe597030175920b994e39ff51db8a683dbb8d5f907c0f8d73f8d55044b9`。目标原应用的 `.text` 所在加载区 45,008 字节与仓库 `dbgstress/fw.elf` 一致，首加载区已有 3,072 B 差异。恢复判据使用板上双读快照。原应用计数持续前进，SYSCTL 的 CPU0、MCHTMR0 和 AHB 配置试前试后分别为 `0x03020100`、`0x01010000`、`0x05040203`。

## 功能验收

| 操作 | 本轮结果 |
|---|---|
| 连接与身份 | 上电前原生 1/5/10 MHz 读全零，Web 10 MHz 链扫描读全一。用户给板上电后，原生和 Web 都读出预期 TAP，内置 HPM 原版 SDK CFG 建链通过。 |
| 调试 | 运行心跳、暂停、指令单步及 DCSR cause=4、运行到断点 `0x80005762`、源码单步跳过/跳出、回栈、局部变量和返回值通过。x5 和 32 B SRAM 改写后回读恢复；监视 `g_model.magic` 为 `0x4d4f4445`，同 ELF 重载后重新读取一致。RV32 数据观察点仍被 Cortex-M DWT 路径拒绝（ZL-195）。 |
| 异常与复位 | 已有停点的 RV32 CSR 读取及 JSON 导出与直接读寄存器逐项一致，读取到外部中断记录。本轮未注入新 trap。软件复位停于 `0x80003000`，复位运行后心跳由 4,428 到 9,036。JTAG 未接 NRST，ARM ETM/SWO 不适用。 |
| Flash | 内置 HPM CFG 经 Web 端执行稀疏 HEX、BIN、ELF 三轮擦写与校验。三个输入均来自已备份原字节，影响同一扇区。HEX 只给 `0x8000f040` 与 `0x8000f140` 各 1 B，夹在中间的 255 B 含非 FF。BIN/ELF 各给 64 B，作业分别约 7.91/7.58 s，包含传输、计划与校验。每轮独立双读首 128 KiB 与开测镜像一致。烧录算法改写 5,207/5,209/5,209 字节 ILM，已恢复并双读完整 128 KiB 工作区，暂停现场寄存器经比对恢复后继续运行。该用例验证稀疏镜像保留扇区空洞（ZL-215）。测试镜像没有替换原应用。 |
| RTT Viewer | 探针连接及现有控制块上行、浏览器缓冲导出、发送 HEX 到 ch0、独立 SBA 回读 8 B `00a5ff31320a8055` 及写游标通过。16 KiB 非缓存 AHB 环和临时 ILM 夹具均恢复。 |
| RTT 转发 | HID 启动、COM33 打开、Web 窗口捕获、下载、STOP 和释放通过，探针零读/写错；每个测量窗内 u32 序号连续。窗口之间包含下载和控制开销，没有把分窗当连续全量收尾核对。 |
| J-Scope | 一路/八路 HSS、一路 Wasm 主机轮询、JSP 与 CSV 逐样本核对通过。八路回放恢复 130,309 组。全部 HSS 窗口 Stop 尾差、包序缺口、USB 丢样及读错均为零，探针跳拍单列。 |
| 资源交接 | 调试保持连接时切到 Scope，仅导航不关闭调试。启动 Wasm 采样后调试连接释放。切回调试页不停止采样，重新连接调试器后正常停止 Scope，保留样本，目标继续运行。 |

## 流速实测

下表是浏览器收流或采样时间戳测量。单位 kB/s、MB/s 为十进制。Viewer 和 CDC 的实际 TCK 以相同设置独立复核，经物理 AP0 读 FCLK `49,999,999 Hz` 和分频配置 `0x20011`，计算 TCK `24,999,999.5 Hz`；HSS 的 DEF 回报 `24,999,999 Hz`。这些是寄存器和设备回报口径。

| 通路 / 负载 | 窗口 | 实测 | 完整性及边界 |
|---|---|---:|---|
| RTT Viewer / 16 KiB AHB 环、1024 B 发布批次 | 3×约 2.04 s | **8.06 kB/s** 中位数，范围 8.03–8.06 | 每窗 16,384 B，合计导出 49,152 B，连续 12,288 个 u32，零覆盖/错位。 |
| RTT→CDC COM33 / 同一环与发布批次，探针 2048 B 块 | 3×约 3.00 s | **1.560 MB/s** 中位数，范围 1.554–1.564 | 合计 14,053,376 B，各窗内序号连续。另一次物理读钟对照中 4,870,144 B / 3.003 s，按首尾数据块扣除窗口初始块为 1.575 MB/s。 |
| HSS 1 路 u32 / `g_ticks`，周期 10 µs | 约 5.213 s | **100.000 k组/s**，0.400 MB/s 有效样本 | 521,338 组，探针跳 1 拍。 |
| HSS 1 路同变量，周期 7.5 µs / 180 ticks | 3×约 5.22 s | **133.291 k组/s** 中位数，范围 131.618–133.333 | 探针各跳 8,941 / 223 / 2 拍。首轮约 1.29%，该档不能当稳定零跳拍。 |
| HSS 8 路连续 u32 / `g_seq_slot`，周期 40 µs | 3×约 5.21–5.24 s | **25.000 k组/s**，0.800 MB/s 有效样本 | 三轮零跳拍，130,309 / 130,309 / 130,884 组。45 µs 对照为 22.222 k组/s，零跳拍。 |
| Wasm 1 路主机轮询 / `g_ticks`，请求 10 ms | 约 3.06 s | **23.51 Hz** | 73 点、主机错过 234 个调度周期，读错 0。 |
| Wasm 1 路主机轮询 / `g_ticks`，请求 50 ms | 约 2.93 s | **16.75 Hz** | 50 点、主机错过 9 个调度周期，读错 0。 |

Viewer 断开后，旧夹具直接走 DAP 数据命令停止生产者失败，因为该 Web 会话已执行 DAP Disconnect。随后通过独立低速重建和恢复入口停止生产者，核对 RAM、寄存器、cache 和时钟后恢复运行。既有 ZL-196 的原生 STOP 返回 -4 和恢复中断问题没有在本轮验证修复。保留 Scope CTA 未完成 HID 身份前时钟控件禁用、CDC 脚本最初使用 kHz 错填 Hz 等驱动失败证据（ZL-090），不计入产品失败。

## 收尾与证据

HPM6800EVK 已运行原应用。首 131,072 B Flash 试前试后各双读并逐字节相等，SHA-256 `e02c28713f8804d31ef4b3ffa4289b9ddb0da57920deefaceff7aba3e82b4c4b`。五个 RTT RAM 夹具均核对恢复 ILM/AHB 区和核心寄存器；文档中的软件复位已正常重启应用。探针仍运行原 QSPI 配对，最后读钟 FCLK `119,999,998 Hz`，TCK 约 10 MHz。RTT、HSS、DDR 采集与 DMA 均空闲。测试浏览器页和本任务服务已关闭，共享 hw_server 保持运行。

本机原始证据在 `build/hpm6800-e2e-20261114/`。重点为 `powered-before/snapshot.json`、`debug-e2e/result.json`、`source-e2e/result.json`、`reset-e2e/result.json`、`handoff-e2e/`、`flash-guard/restore.json`、`flash-bin/`、`flash-elf/`、`rtt-e2e/`、`rtt-down-verified.json`、`cdc-e2e-run/`、`cdc-clock-confirm/`、`scope-rate-repeat/`、`scope-e2e/`、`final/snapshot.json` 和 `probe-final/result.json`。Flash/SRAM 备份和运行令牌留在本机，不入 Git。验收覆盖本机源码 Web 路径，未重新打包固定 EXE 或部署 Pages。
