# J7 改脚复核

后续修复记录：ZL-158 已在独立的新 ELD1/序列修复配对完成实板验收。下表和原问题描述按最初 J7 生产配对保留。 [修复范围与证据](../j7-sequence-fix-20261106/README.md)

2026-11-06（上海时间）。对象为 `prebuilt/j7-adapter-20261106` 的生产 bit/ELF。核对用户的 12 球号、实布线 I/O 报告、实现网表日志、生产 ELF 与已完成的板测。沿用的生产 RAW4 网表原本没有 ELD1。上次交付未明确注明这点，此处补齐。

| 项目 | 实现和核查结果 |
|---|---|
| 球号和电气配置 | 12 球号全部与转接板表一致，均为 Bank 35 / LVCMOS33。TRACECLK/D0～D3 与 RTCK 是输入，SWD/JTAG 通用管脚通过 IOBUF 复用。 |
| TMS/SWDIO L16、TDI M15、TCK/SWCLK L15 | L16 在 JTAG 作 TMS 输出，在 SWD 需要双向。TDI 由 JTAG 引擎驱动。普通 SWD/JTAG 读写已分别验到实际约 60 MHz。 |
| TDO L14 | JTAG 模式下 RTL 固定为接收，布线日志证实 Q1/Q2 的 IDDR 都实际使用。另发现原始 SWD 序列的旧 GPIO 路径，见 ZL-158。 |
| nSRST M14、nTRST N15 | J7 专用 PS 修复 Connect 误触发 nSRST，普通 JTAG 连接和读写复测通过。nTRST 的显式拉低由 GPIO3 控制，释放时切回输入。nSRST 当前 GPIO2 释放为输出高电平。两根脚的独立脉冲波形和复位功能未专项验收。 |
| RTCK H15 | 实现为只输入的预留 pad，未接入自适应 TCK 引擎。JTAG 固定时钟通过。 |
| TRACE 接收 | J16 是普通 I/O。生产配对使用 RAW4 的 200 MHz 过采样，实网表确认 5 路同步器、0 个 TRACE IDDR、0 个 BUFIO/BUFR、0 个 IDELAYE2。DDR/USB 连续窗口和环形采集已有实板证据。ELD1 需单独构建，五路延时与采样端点由新实现日志验收。 |
| FCLK / 外部时序 | 133.333 MHz 内部实现时序通过，`check_timing` 中无无时钟寄存器和未约束的内部最大延迟端点。`swdio_0`、`gpio_rtl_0_tri_io[0:3]` 仍缺外部 input/output delay。保留 ZL-007 的 IO/CDC 签核范围。 |
| 交付和其他功能 | JTAG/RAM 下载已验，RTT/HSS 空闲状态已读回。转接板上的 RTT/HSS 跑流、独立复位脚和 QSPI 冷启动不在已验收项目中。 |

**ZL-158，原始 SWD 序列可能驱动 TDO。** 生产 PS 的 `DAP_SWD=1`。命令 `0x1D` 可进入 `DAP_SWD_Sequence`。其中旧 `PIN_SWDIO_OUT_ENABLE` 清除 AXI GPIO TRI bit1，旧 `SWD_Sequence` 也通过该 GPIO 位收发。J7 的该位已接到 L14/TDO。SWD 模式使能 GPIO 路由后，清 TRI bit1 会使 L14 变成输出。生产 ELF 的 `DAP_ProcessCommand` 中可见清 bit1 后调用 `SWD_Sequence` 的指令。若连接的目标同时驱动 TDO，存在输出争用风险。此次按源码、网表绑定和生产反汇编确认，未在板上发该命令。普通 `SWJ_Sequence`（`0x12`）和 MEM-AP 读写走现有硬件路径，校准使用这两条路径。 [DAP 命令实现](../../../firmware/xusbps_daplink_dma/DAP/Source/DAP.c) · [GPIO 与管脚函数](../../../firmware/xusbps_daplink_dma/DAP/Include/DAP_config.h)

**ZL-159，断开时 TCK 输出仍常使能。** `PORT_OFF` 的注释描述调试脚高阻。RTL 的 SWDIO/辅助管脚有三态控制，但 L15 的 `u_clock_iobuf` 的 `T` 固定为 `0`，所以断开后 L15 仍驱动空闲电平。此为已有实现与隔离行为的差异，本次按源码和实际配对的 RTL 输入指纹复核，未使用第二个调试器做争用试验。 [SWD 控制器](../../../fpga/rtl/swd_controller.v) · [配对 RTL 指纹](../../../prebuilt/j7-adapter-20261106/rtl-inputs.json)

[原布线 I/O](../j7-adapter-20261106/raw/j7-adapter-io.rpt) · [原实现摘要](../j7-adapter-20261106/raw/implementation-summary.txt) · [60 MHz 板测](../j7-adapter-limits-20261106/README.md)
