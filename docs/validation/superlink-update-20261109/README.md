# superlinkPRO 更新对照与移植

2026-11-09，Asia/Shanghai。核对 `E:/superlinkPRO` 和远端 `main` 都指向 `044af4aee4b6f1ad6423976edacb47e0e4870f7e`。以此前对照点 `11441e5` 为起点，检查 18 个后续提交，覆盖 Web 源码、探针应用源码和 web.7 至 web.11 的验收及发布记录。板卡离线，本轮验证使用本机运行时、模拟目标、测试客户端与生产 C 的主机模型。 [上游对照范围](https://github.com/minichao9901/superlinkPRO/compare/11441e5...044af4a)

## Web、CLI 与运行时

| 上游来源 | ZynqLinkPRO 处理 |
|---|---|
| `c9454d0` 的 F103ZE Wasm 单调时钟与 64 KiB 二进制读缓冲 | 同步 JS/WASM Git 原字节及链接补丁。旧核心本机无 USB 调用 `ms`，间隔 50 ms 仍为 `-1 / -1`。上游核心对照为 `254 / 311`。本仓实际运行时专项确认时间单调推进。运行时报告 OpenOCD `g9f2d876`，因此保留本仓与实物二进制相符的源版本，未采用上游构建器的 v0.12.0 默认标签。ZL-181。 |
| `c9454d0` 的 F103 SRAM 快路径 | 仅用于内置 STM32F103 配置、DBGMCU DEV_ID=0x414、字对齐且 4 KiB 起的访问，地址全部落在 64 KiB SRAM 窗口内。HPM6800 物理 SBA 沿用独立门槛，寄存器及任意 CFG 继续走现有访问。保留 Zynq USB 租约和队列 epoch。性能对照待板验，关联 ZL-141。 |
| `6f33bae`、`f6c5dff` 的 RV32 指令与异常诊断 | 合并 JAL/JALR/AUIPC 半字解析和 32 位调用优先识别，并校正分支低立即数取自低半字。异常面板经 Wasm 读取命名 CSR，前后核对暂停和 PC。软件断点与观察点涉及代码写入及触发器分配，留在后续独立板验范围。ZL-182。 |
| `f6c5dff` 的 HPM 复位 | 移植到本仓共用探针类，调试、烧录及 RTT 的 HPM 软件复位共享。DMI 复位期间屏蔽 OpenOCD 后台轮询，读回 DMCONTROL 确认释放，成功及异常路径均恢复原轮询配置。全局 NRST 仍按本仓已有的物理引脚入口处理。ZL-183。 |
| `6f33bae`、`c18aafd` 的 RTT 事务与预览 | 上下行同用一个事务队列，重扫仍由用户显式触发。普通 RV32 运行态 SBA 轮询每次至多 8 KiB，ANSI 使用已有的有界渲染队列，出现显示缺口时复位 ANSI 解析状态。原始接收计数和文件记录独立。ZL-174、ZL-184。 |
| `c9454d0` 的 J-Scope 长窗 | 用类型数组、LOD、时间锚点的实际分配量求容量，HSS 回放和 WASM 精确时间戳都执行 128 MiB 样本预算，超限回放在分配样本数组前拒绝。保留本仓 DEF 校验和精确计数。原始 USB 包和文件输入本身另计。ZL-185。 |
| `c9454d0` 的 ETM 与 CLI | 仅允许未领取的白名单只读任务在旧租约过期后由新页领取，已运行任务及排队写保留旧所有者。原生前端失败或超时时清理非持久临时 JSON。KingstVIS 过滤器依赖 LA 采样和通道模型，Zynq FPGA 采集使用独立 DDR/RAW4 通路。ZL-186、ZL-187。 |

## 探针应用和多芯片证据

- `6962e41` 的 EVKLite CDC 末包修复在转发结束后补短包，避免主机继续等待整包长的传输。Zynq 的 EP3 已通过 `probe_stream.c` 的完成回调与 1 ms 空闲判定终止整包尾，且 ZLP 不消费数据槽。本轮以同样的 511/512/513/1024 B 边界在生产 C 模型对照，整包长尾只补一次 ZLP，非整包长尾不补。真实 USB 的接收完成由下一轮板验核对，关联 ZL-094。
- `c9454d0` 的 EVKLite 300/360 MHz SWD 汇编档位、施密特输入、MCHTMR 低字回绕、HSS 32 个发送槽以及 HPM 标定附加字依赖其 SoC、USB 驱动和采样器。Zynq 由 PL SWD/JTAG、FCLK 分频、PL 组帧/DMA 及 PS XUsbPs 队列实现对应功能。Zynq 调试让路走 `probe_before_dap` / `probe_after_dap` 的显式交接。保留本仓队列和时钟，不从 EVKLite 的 32 槽结果推断 Zynq 延迟或吞吐。
- 上游验收的 F103ZE、HPM6800EVK、RV32IM 和 RP2350 使用各自配对。上游 HPM6800EVK 的 JTAG 座未接 NRST，顶栏只能确认探针输出。上游 F103ZE 的部分高速 SWD/PPB 和 SYSRESETREQ 失败仍在追踪。Zynq 的独立实物回归按已加载 J7 配对、目标和实际时钟重测。

本轮探针侧提交是主机模型的扩充，生产 PS/PL 无需变更。已知配对和固定 Windows EXE 保持原交付身份。 [CDC 与 RV32 验收](https://github.com/minichao9901/superlinkPRO/blob/044af4a/docs/validation/rv32im-rtt-cdc-throughput-20261108.md) · [F103ZE 验收](https://github.com/minichao9901/superlinkPRO/blob/044af4a/docs/validation/f103ze-night-acceptance-20261108.md) · [HPM6800EVK 验收](https://github.com/minichao9901/superlinkPRO/blob/044af4a/docs/validation/hpm6800evk-web10-acceptance-20261109.md) · [RP2350 验收](https://github.com/minichao9901/superlinkPRO/blob/044af4a/docs/validation/rp2350-cfg-shared-hw-20261108.md)

## 离线验证与实板复验

- Web 自测 148/148，覆盖实际 Wasm 时钟、CFG 预检、模拟 DAP、HPM DMI 复位失败恢复、RV32 CSR 快照及失效 PC、F103 读写门槛、RTT 显示积压和 J-Scope 容量。
- CLI 自测 65/65，覆盖过期租约下未领取的只读接管，以及已领取只读任务和未领取写任务均拒绝接管。ETM 前端超时临时 JSON 清理通过。
- 生产探针 C 主机模型 9 组通过。保留既有 USB 描述符签名比较编译警告。共享模块和 Web 语法检查通过，`trace doctor --offline` 通过。

| 待板验 | 核对项 |
|---|---|
| F103ZE | 同一 J7 配对和时钟下比较 20/64 KiB SRAM，核对越界回退、地址对齐、哨兵和恢复，分开记录 Worker 和 USB 开销。回归断点、软件复位及 ETM 采集恢复。 |
| HPM6800EVK、RV32 | 软件复位停机与运行、DMCONTROL/DMSTATUS 和断点重命中，ECALL/非法指令与独立 CSR 回读，RTT 窗口连续序号及上下行。 |
| F103ZE、H743、HPM6800EVK | RTT→CDC 四档边界及高速连续窗口尾差，J-Scope 长窗、STOP 排空、跨页交接。ETM 联动与原生 CLI 使用新 WASM 的 F103/H743 回归。 |
| RP2350 | 导入原版 CFG、只读身份/RTT AP 选择及原已支持的调试和烧录矩阵。 |
