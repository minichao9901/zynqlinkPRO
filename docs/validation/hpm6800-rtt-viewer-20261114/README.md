# HPM6800EVK RTT Viewer 吞吐修复（2026-11-14）

## 已定位的开销

SuperLinkPRO/akaLinkPro 使用 Chrome 直连 WebUSB 和 OpenOCD Wasm，JTAG 请求 8 MHz，7.18 秒内实收 155,618 B/s，覆盖和错位读计数均为零。探针 RTT→CDC 的 1.465 MB/s 使用独立数据路径。SuperLinkPRO 的原始记录 `docs/validation/hpm6800-wasm-sba-tail-20261107.md` 同时记录了渲染积压会把该项目的第一轮浏览器吞吐降到 4,541 B/s，以及渲染保护后的结果。

zynqlinkPRO 同样运行 OpenOCD Wasm。J7 的[原始 E2E](../hpm6800-e2e-20261114/README.md#rtt-viewer-吞吐追查2026-11-14)采用浏览器加本机代理，实际 TCK 24,999,999.5 Hz。独立计时窗内，Viewer 读 49,152 B 用 6.124 s，完成 6 次 8 KiB 轮询。期间 777 次 DAP OUT 和 778 次 DAP IN 各走同步 HTTP 请求，服务端 USB 函数累计 0.345 s。其余约 94% 墙钟时间在该函数外，包含浏览器、Wasm、HTTP、鉴权和调度。不同项目的探针及浏览器环境有差异，现有证据可定位 zynqlinkPRO 的请求放大，尚未拆出各环节的独立成本。

## 候选修复

- 内置 HPM6800EVK + zynqlinkPRO 的 Viewer 先用 Wasm 验证目标与控制块，当所有活动 RTT 缓冲及控制块位于已知 SRAM 区域时，释放 Wasm 的 USB 会话，以新 DAP 队列接管 JTAG。接管后重新检查 TAP 和 RTT 标识、通道配置，失败则关闭该会话并回到 Wasm。
- 上下行通过探针已有的 CMSIS-DAP TransferBlock 执行 SBA。单个 8 KiB 连续数据段最多 3 个块，块地址和数据共最多 6 次原子请求，控制块和读游标另计。轮询按原协议分两段处理环绕，写完确认完成再提交游标，响应失败后保留错误并要求重新扫描。重新扫描和软复位先归还 JTAG，再由 Wasm 执行。
- Viewer 根据大块读取和环水位立即暂停终端渲染，接收和原始数据记录继续。用户可以手动恢复。当缓冲不再积压且速率下降后自动恢复。
- 本机代理使用制造商与产品描述符区分同 VID/PID 的 zynqlinkPRO 和 akaLinkPro USB/HID。多个 zynqlinkPRO 仍报设备歧义。串口选择独立。

## 验收状态

J7 PS/PL 的物理状态读回空闲，OCM 执行代码 85,716 B 与 0.8-nonce32 QSPI 配对一致。开始测量前 Windows 未枚举到 J7 USB `12345678`（COM33），仅枚举到 SuperLinkPRO 的 USB（COM34）。未对任一探针重新加载、复位或写入，未安装 RAM 夹具。

候选软件覆盖边缘字节保留、8 KiB 分块、短响应停止、渲染保护和同 VID/PID 枚举。新旧浏览器路径同板吞吐、序号连续性、上下行和扫描、软件复位交接仍待 J7 恢复 USB 枚举后实测。

## 实板恢复与 RTT Viewer 对照

最初测试安装临时夹具后，Windows 丢失 J7（序列号 `12345678`），同一 USB 集线器仍能看到 SuperLinkPRO。J7 短暂重新枚举时发生 DAP Pipe error，标准夹具恢复也曾在 STOP 确认失败后退出。物理 AP0 独立路径识别 TAP 并核对了 ILM/AHB，随后 FTDI 传输中断。J7 改接后用已确认的新 DAP epoch 重连，直接暂停 HPM6880，回写并验证 ILM 256 B、AHB 32 KiB、AXI 64 KiB、所有保存的核心寄存器、缓存控制和 SYSCTL，恢复运行（DMSTATUS `0x430ca2`）。首 128 KiB Flash 双读保持 `e02c28713f8804d31ef4b3ffa4289b9ddb0da57920deefaceff7aba3e82b4c4b`。恢复后 J7 的串口由 Windows 分配为 COM5，按 USB 序列号确认。全过程只操作 J7。

同一 J7 / HPM6800EVK、Chrome 本机桥接、32 KiB 非缓存 AXI 环、1024 B 发布批次、Viewer 5 ms 轮询和 8 KiB 单轮上限，交替运行旧页面和修复后页面。两侧 FCLK 均为 49,999,999 Hz，寄存器折算实际 TCK 24,999,999.5 Hz，JTAG 采样相位均为 0。旧路径沿用 Wasm 原 JTAG 配置，新路径设 PL idle 8。两轮每种路径，每轮两个约 2.5 秒窗，四窗中位 **6.388 → 196.095 KiB/s**（**30.7 倍**）；新路径 AHB 16 KiB 环两窗中位 222.046 KiB/s。总导出 3,768,320 B，每轮从 u32 序号 0 起连续，覆盖和错位均为零。五轮向 256 B 下行环写相同的 11 个二进制字节，WrOff 从 251 到 6，RdOff 保持 128，256 B 全环独立读回一致。每个夹具均完成恢复。原始证据 `build/hpm6800-e2e-20261114/rtt-transport-ab-095004/results.json`。

## v1.3.7 发布

固定 EXE 由已通过离线验收的干净源包更新，保留用户 data，Chromium 实际打开版本窗口显示 `2026-11-14 01:27:37 UTC`。Pages 版本窗口显示 `2026-11-14 01:27:21 UTC`，工程下载卡为 v1.3.7，链接到本项目 Release。源码提交 `3486736b`，Pages 静态提交 `0ae1f73b`。公网匿名完整下载 ZIP 为 56,201,500 B，SHA-256 `d2d0fc88f9309bb926b9053b01c27d677caef2d2b5bf4678b5f463d37fa2d17a` 与 GitHub 资产及本机候选一致。[Pages](https://minichao9901.github.io/zynqlinkPRO/) · [Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.7)

Chrome 使用哈希核对过的 v1.3.7 Pages 资源，USB 和 HID 直接连接 J7。实际 TCK 24,999,999.5 Hz，Viewer 使用 16 KiB AHB 环、1024 B 发布批次和 5 ms 轮询。两个约 1.3 秒窗口中位 **784.4 KiB/s**，对应原生 CLI **624.5 KiB/s**。浏览器额外保留完整原始流，743,424 个 u32 从 0 连续，11 B 跨环下行及游标读回一致。

同一实际 TCK 下，J-Scope 的 Web／CLI 稳态均约为单路 10 µs **100,000 组/s**、八路 40 µs **25,000 组/s**。浏览器全会话分别收到 428,647／104,418 组，探针在稳态窗外分别跳 1／119 拍，两个稳态窗均无跳拍。独立解析原始包，USB 丢样、包序缺口、读错及 STOP 尾差均为零。原始数据见 `build/hpm6800-e2e-20261114/rtt-release-bench-100448/report.json` 和 `rtt-release-bench-095702/report.json`。

## 在线 RTT 转发补测状态

2026-11-14 补测前确认 Windows 仅枚举到一个 CMSIS-DAP 串口 COM5，对应 J7 序列号 `12345678`。J7 的 HPM6800 TAP 为 `0x1000563d`，目标运行，首 128 KiB Flash 双读与原快照一致，RTT、HSS 和物理采集引擎均空闲。Chrome 已运行逐文件校验的 v1.3.7 Pages 资源，硬件通路为浏览器直连。原授权绑定于旧的 Windows 设备实例，本轮打开 COM5 授权对话框，300 秒内未收到授权，未安装 RAM 夹具、未打开串口、未启动转发。之前 CLI 实际 TCK 24,999,999.5 Hz，两窗中位 1.553 MB/s。线上同 TCK 的速度、上行全量序号和 STOP 尾包仍待授权后复测。补测等待记录 `build/hpm6800-e2e-20261114/online-cdc-tail-100931/result.json`。

## 在线 RTT 转发实板结果

COM5 人工授权后复用同一 Chrome 配置。固件身份为 0.8-nonce32，HID 再读 SN `12345678`。浏览器保持 Pages 原站点，页面资源来自线上下载并与发布清单核对，CDC 使用真实 Web Serial。使用与 CLI 基线相同的 16 KiB 非缓存 AHB RTT 环、1024 B 发布批次和 2048 B 探针转发块。两边均从物理寄存器读回 FCLK 49,999,999 Hz、折算 TCK 24,999,999.5 Hz，采样相位 0。稳态两个约 3 s 窗分别为 1.559633、1.558743 MB/s，中位 1.559188 MB/s，CLI 两窗中位 1.552523 MB/s，线上约快 0.43%。

- 固定长度连续流 12,582,912 B 和两组非整包、非整字尾 15,743 B、1,003 B，目标发布、探针搬运、浏览器实收逐组相等，原始流从 u32 序号 0 起逐字节比对通过。
- 连续供数时主动点击 STOP 三轮，点击后继续收到 6,144、4,096、4,096 B，累计实收逐轮为 829,440、626,688、659,456 B，均等于探针搬运数，逐字节比对通过。独立回读每轮另有 15,360 B 未搬运、仍留在目标 RTT 环，满足目标发布字节 = 浏览器实收 + 目标环剩余。六轮均确认 STOP 和 START 按钮恢复，无读写错误。
- 首次授权后驱动等待时钟控件时超时，修正为等待型号读取完成。首次连续流阶段 DAP 控制在活动转发期间被拒，随后以有上限的独立 RAM 发布程序完成，采集过程中不抢占 DAP。两次接触夹具的失败或验证路径均核对恢复。最终 RAM、寄存器和 SYSCTL 核对通过，目标继续运行。首 128 KiB Flash 双读与试前一致，探针引擎空闲。

原始证据 `build/hpm6800-e2e-20261114/online-cdc-tail-123504/result.json`、`online-cdc-tail-123616/result.json`、`cdc-followup-final/snapshot.json` 及同目录 `idle.json`。CLI 基线为 `rtt-release-bench-095702/report.json`。

## 复测经验

- 排查 Viewer 速率先固定探针配对、实际 TCK、目标内存、负载和计时窗口，再记录每轮传输次数与服务端处理时间。此前调整 Wasm 流水线和文本缓冲只带来小幅改善。本机桥接的主要耗时来自频繁的同步请求，J7 的探针块读减少请求，环积压显示保护降低渲染对轮询的影响。
- 用从 0 开始的非重复载荷验证连续性，原始接收在显示截断之前保存。STOP 对账核对浏览器实收、探针已搬运和目标环剩余，单列探针调度跳拍、传输丢样和尾差。
- Windows 重枚举后用探针序列号重新确认 COM 口。浏览器授权、型号读取和业务启动分别确认；授权等待阶段保持夹具未安装。长流用有限发布量自然结束，避免在转发持有 DAP 时写目标的停止标志。异常收尾用独立会话恢复备份，逐项核对 RAM、核心寄存器、缓存控制和运行状态。
