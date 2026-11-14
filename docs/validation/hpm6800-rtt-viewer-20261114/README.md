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

## 在线 RTT 转发补测状态

2026-11-14 补测前确认 Windows 仅枚举到一个 CMSIS-DAP 串口 COM5，对应 J7 序列号 `12345678`。J7 的 HPM6800 TAP 为 `0x1000563d`，目标运行，首 128 KiB Flash 双读与原快照一致，RTT、HSS 和物理采集引擎均空闲。Chrome 已运行逐文件校验的 v1.3.7 Pages 资源，硬件通路为浏览器直连。原授权绑定于旧的 Windows 设备实例，本轮打开 COM5 授权对话框，300 秒内未收到授权，未安装 RAM 夹具、未打开串口、未启动转发。之前 CLI 实际 TCK 24,999,999.5 Hz，两窗中位 1.553 MB/s。线上同 TCK 的速度、上行全量序号和 STOP 尾包仍待授权后复测。补测等待记录 `build/hpm6800-e2e-20261114/online-cdc-tail-100931/result.json`。
