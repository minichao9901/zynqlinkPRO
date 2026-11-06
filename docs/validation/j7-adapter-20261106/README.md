# J7 转接板改脚与验收

2026-11-06（上海时间），XC7Z020 CLG400-2。按照转接板接线表更新 Bank 35 球号，沿用 LVCMOS33。TMS/TCK 对应探针已有的 SWDIO/SWCLK 复用端口。

| 信号 | J7 | FPGA 球号 | 顶层端口 |
|---|---:|---|---|
| TMS | 31 | L16 | `swdio_0` |
| TCK | 29 | L15 | `swclk_0` |
| TDO | 27 | L14 | `gpio_rtl_0_tri_io[1]` |
| TDI | 25 | M15 | `gpio_rtl_0_tri_io[0]` |
| nSRST | 23 | M14 | `gpio_rtl_0_tri_io[2]` |
| nTRST | 19 | N15 | `gpio_rtl_0_tri_io[3]` |
| RTCK | 15 | H15 | `rtck` |
| TRACECLK | 41 | J16 | `trace_clk` |
| TRACED0 | 39 | K16 | `trace_data[0]` |
| TRACED1 | 37 | M18 | `trace_data[1]` |
| TRACED2 | 35 | M17 | `trace_data[2]` |
| TRACED3 | 33 | L17 | `trace_data[3]` |

RTCK 保留为输入，JTAG 使用固定 TCK。J16 是普通 I/O。沿用 RAW4 对五路信号的独立 200 MHz 过采样，DDR 采后下载路径保持同一设计。专用 BUFIO 采样路径需要时钟能力引脚。 [AMD UG472](https://docs.amd.com/v/u/en-US/ug472_7Series_Clocking)

后续逐项复核确认，生产 RAW4 bit 是直接输入版，五路 IDELAYE2/ELD1 未实例化。端口方向、原始 `0x1D`、TCK 断开状态与未覆盖验收项目见 [J7 改脚复核](../j7-eld1-20261106/j7-production-audit.md)。

改脚采用上次 RAW4+DDR 的 post-opt DCP。该网表已链接、未放置，对应 `5be7176`，FPGA 和 PS 源码与本轮基线 `23e3c5c` 相同。最初新建工程并接入 RTCK GPIO 读回触发整套 IP 综合，随后停下该流程。最终方案在网表上增加无负载的 RTCK 输入缓冲，释放旧球号后统一应用新约束。H15 直接赋值在试验中因旧 TRACED0 占用被 Vivado 拒绝，保留日志。布局、物理优化、布线、时序、DRC 和 bitgen 均针对新球号重新运行。

```powershell
# 使用对应 RAW4+DDR 源工程生成的已链接、未放置 post-opt DCP。
$env:ZYNQLINK_FPGA_OUT = 'E:/zynqlinkPRO/build/j7-adapter-repeat'
python -X utf8 toolbox.py project run fpga/rebind_j7_adapter.tcl -- build/history-20261105/session-flight-20261105/fpga/zynqlink_dma.runs/impl_1/system_wrapper_opt.dcp
python -X utf8 toolbox.py project run firmware.build -- --j7-adapter --compact-code --opt 3 --max-swclk-hz 60000000 --timing build/j7-adapter-repeat/verified_clock.json --out build/j7-adapter-repeat-ps
```

## 时序、身份与下载

新 bit 在 7.5 ns FCLK 约束下，setup 余量 0.074 ns，hold 余量 0.054 ns。短 SWCLK 输出路径 6.644 ns，余量 0.356 ns。36661 条可布线网络全部完成，bitgen DRC 为 0 error、47 warning，仍保留 ZL-007 的 IO/CDC 签核范围。实际 I/O 报告逐项核对 12 个球号、Bank 35 和 LVCMOS33。RAW4 DDR 离线集成 9 场景及环形回绕通过，CLI 工具入口与交付布局 10 项通过。

最终配对通过 JTAG 下载到 PL 和 PS OCM，启动后物理 MEM-AP0 核对 85580 字节执行段一致。装载前记录 JTAG 启动模式、PL 隔离及单个 XC7Z020。替换首轮 PS 前核对探针租约、采集、DMA、RTT 和 HSS 空闲。配对和逐文件 SHA 见交付目录（历史归档 `archive/main-before-formal-release-20261106:prebuilt/j7-adapter-20261106/README.md`），时序、I/O 及下载见[证据清单](raw/manifest.json)。

## JTAG 与 ETM 实测

目标是 F103ZE，`CPUID=0x411FC231`，设备 ID `0x10036414`。SWD 比对 CDC48 ELF 的 20168 字节 Flash 装载段完全一致。目标 CPU/HCLK 名义 48 MHz，TRACECLK 名义 24 MHz，由既有固件和 RCC 配置确定。

首轮用原 PS 启动 JTAG 后返回 `16 00 00 00 00 00`，DHCSR 从 `0x01010000` 变为 `0x03010000`。旧夹具的 GPIO2 接目标 nTRST，`PORT_JTAG_SETUP` 给 GPIO2 低脉冲。新板 GPIO2 接 nSRST，这次脉冲使目标 MCU 发生一次系统复位。CDC48 启动会关闭 JTAG，导致之前临时打开的 AFIO SWJ 配置被覆盖。首轮复位前的 MCU 运行现场无法恢复，保留失败回包及状态。首轮 ETM 仍单独采通，该记录属于首轮 PS。

转接板专用 PS 通过 `--j7-adapter` 在 JTAG Connect 前保持 nSRST 释放。TAP 复位走 TMS 序列，nTRST 仍可由显式引脚控制操作。最终 bit 沿用通过时序的同一文件，配套 ELF 重新编译并独立读回。使用 F103 临时 SWJ 夹具确认以下两档 JTAG，恢复 AFIO 可读位、固件定义的 SWJ_CFG=2、APB2ENR 与运行状态。复测期间 DHCSR 未再出现系统复位标志。

| 测试 | FCLK | 链路时钟 | 结果 |
|---|---:|---:|---|
| ARM JTAG | 1.999999 MHz | TCK 0.9999995 MHz | IDCODE `0x3BA00477`，16 次 CPUID 与 4096B 累计 Flash 读回匹配 |
| ARM JTAG | 19.999999 MHz | TCK 9.9999995 MHz | 同一 IDCODE 与 16 次 CPUID，4096B 累计 Flash 读回匹配 |
| ETMv3 DDR/USB | 119.999998 MHz | SWD 9.9999998 MHz | 完整 100ms 硬件窗，94980 帧，384283 字节 ETM，解码 1891730 条指令 |

链路频率按物理寄存器读回的 PLL 和分频推算。两档 JTAG 的 PHY 计数各增加 60352 位、1840 次扫描。最终 ETM 帧丢失、formatter parser 错误、DDR writer 错误及解码包错误均为 0，保留 2 个解码缺口和 12 字节不确定尾部。100 ms 窗口由硬件 20000000 参考拍确认。原始输入只归档最终配对的一份。[JTAG 回包](raw/jtag-final.json) · [ETM 完整结果](raw/etm-final-result.json)

最终目标运行，`DHCSR=0x01010001`。CDC48 装载段、目标 RCC 配置、ETM 暂存配置和 FPB 通过收尾核对。PL/PS 保持最终 RAM 配对，采集、DMA、RTT 和 HSS 均空闲。目标 Flash 与探针 QSPI 无写入。本任务测试进程已退出，本机 `hw_server` PID 3904 保持供编程链使用。本报告覆盖 F103ZE 短窗和两档 JTAG，RTCK 只验实现中的输入分配。 [目标复核](raw/target-final.json) · [探针空闲](raw/probe-idle-final.json)
