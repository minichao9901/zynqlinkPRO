# 当前 bit 的资源与 LUT 优化结果

2026-10-30 08:08，Vivado 2018.3，xc7z020clg400-2，完成布线并生成本次 bit。
通过现有约束的 STA，尚未加载实板；用户确认 trace 线暂未连接。

## 整机资源

| 资源 | 优化前候选 | 当前 bit | 减少 | 当前占器件 |
|---|---:|---:|---:|---:|
| LUT | 24,419 | **19,228** | **5,191（21.26%）** | 36.14% |
| FF | 35,219 | 27,858 | 7,361（20.90%） | 26.18% |
| Slice | 12,070 | 10,535 | 1,535 | 79.21% |
| BRAM Tile | 10 | 10 | 0 | 7.14% |
| DSP | 1 | 1 | 0 | 0.45% |
| Unique control sets | 1,317 | 951 | 366 | — |

当前 LUT 包括 logic 18,580、LUTRAM 362、SRL 286，latch=0。
Slice 占用仍明显高于 LUT/FF 比例，控制集与布局也值得优化。

基线为 07:11 的 routed candidate，trace 输入 hold −1.716 ns，不能称作已验收 bit。
本次同时包含 AXI native-32 修正和 trace 输入 IDELAY 校准，**不是只改一个变量的严格 A/B**。
但五个互联合计减少 5,192 LUT，可以确认面积主要收益来自互联。
旧 DCP 已被重新构建覆盖，仅保留报告和其 SHA，不声称仍持有旧网表。

原始证据：`docs/validation/orbtrace-native32-20261030/`；旧证据：
`docs/validation/orbtrace-area-20261030/`。本次候选 bit/ELF 在
`prebuilt/20261030_orbtrace_native32/`，身份以该目录 manifest 的 SHA-256 为准。

## 已落实的优化：使 AXI 内部 crossbar 真正为 32 位

`fpga/axi_pipeline.tcl` 原来只设置父对象 `CONFIG.XBAR_DATA_WIDTH=32`。
Vivado 2018.3 的 `data/ip/xilinx/axi_interconnect_v2_1/bd/bd.tcl:645–648` 仅在
`CONFIG.ENABLE_ADVANCED_OPTIONS=1` 时才把该值传给内部 crossbar；原来的五个内部
crossbar 实际仍为 64 位，因此生成了不必要的 32→64→32 通路。

已开启 advanced options，并检查 `$name/xbar CONFIG.DATA_WIDTH` 必须为 32。
本次日志确认五个内部 crossbar 均为 32；原 regslice 配置保留，HP0 边界仍保留必要转换。

| 实现后模块 | 优化前 LUT | 当前 LUT | 减少 |
|---|---:|---:|---:|
| PS AXI interconnect | 5,031 | 1,921 | 3,110 |
| DMA interconnect | 1,605 | 1,360 | 245 |
| CMD interconnect | 1,166 | 467 | 699 |
| RSP interconnect | 1,166 | 468 | 698 |
| Packet interconnect | 905 | 465 | 440 |
| **五互联合计** | **9,873** | **4,681** | **5,192** |

旧实现 9 个位宽 converter 本体共 4,470 LUT / 4,688 FF；整条互联还减少了 crossbar
和寄存器宽度开销，不能把 converter 本体成本与整机差值直接等同。
位宽转换行为参考 AMD [PG059 AXI Upsizer](https://docs.amd.com/r/en-US/pg059-axi-interconnect/AXI-Upsizer)，
本项目配置缺陷的直接证据是本机 2018.3 Tcl 和生成网表。

## 当前主要面积来源

| 模块 | LUT | FF | 占整机 LUT |
|---|---:|---:|---:|
| SWD/JTAG/probe | **12,713** | 17,506 | 66.1% |
| 五个 AXI 互联 | 4,681 | 8,124 | 24.3% |
| CDMA 本体 | 774 | 1,026 | 4.0% |
| ETM 接收器 | **388** | 475 | 2.0% |

SWD/JTAG/probe 内部，控制器直接层 2,985 LUT / 10,031 FF；JTAG core 2,709 LUT，
其中 shift 1,328；sampler 2,429（其中 352 LUTRAM）；RTT/HSS packet engine 2,611，
其中 RTT 1,092；DAP packet 496；SWD batch 779；SWD PHY/core 708。
父子层级不可重复累加，Vivado 跨层级 LUT combining 也会造成子项合计与父项略有差异。

## 后续优化顺序（尚未实施或量化）

1. **JTAG 诊断快照改用 RAM。** `swd_controller.v:110` 的 9 组 `32×32-bit` 数组共
   9,216 bit，动态写索引和读复用值得首先检查。控制器直接层有 10,031 FF / 2,985 LUT，
   但不能把这些全部归因于诊断数组。先单独统计存储 cell，再比较 LUTRAM/打包 BRAM；
   保留诊断寄存器接口和捕获能力，同步读增加延迟时正确处理 AXI RVALID/反压。
2. **Sampler FIFO 改用带预取的 BRAM。** `probe_sample_engine.v` 指定 distributed，
   FIFO 为 `16×32×32 bit`。本层 352 LUTRAM 是机会量级，BRAM 方案仍有预取/控制开销；
   需保持当前字可用、posted-read flush、停机尾样本、背压语义。
3. **JTAG 长扫描缓冲分段。** `jtag_shift` 的 256-bit 索引写和多组 64-bit 回显可比较
   按字或分段实现，减少按位选择和使能。必须回归长扫描、LSB 顺序、chain、最后一拍与恢复。
4. **控制集与 AXI 流水级。** 当前有 951 control sets、79.21% Slice 占用；逐类评估独立
   enable/reset、AXI-Lite 转换和 regslice。直接取消全部流水级可能恢复 READY 长链，
   应连同时序和实板吞吐逐项比较。

RAM 推断限制参考 AMD [UG901](https://docs.amd.com/api/khub/documents/bL2Ru8vOVyVmhcvVCB6G5g/content)
与 [UG949 RAM 复位检查](https://docs.amd.com/r/2023.1-English/ug949-vivado-design-methodology/Checking-for-Reset-Signals-on-the-Address/Read-Data-Registers)。
节省量必须用本机 Vivado 2018.3 网表确认，不能只加 ram_style 就宣称有效。

**ETM 仅 388 LUT，继续压缩它的收益有限，优先优化诊断存储与 JTAG/probe。**

## 时序与验证边界

- FCLK 100 MHz：setup WNS **+0.568 ns**，hold WHS **+0.024 ns**，TNS/THS=0。
- FCLK 120 MHz：setup **−0.265 ns**，配套 ELF 限 SWCLK/TCK **50 MHz**。
  100 MHz 是脚本测试档位中最高通过值，不是精细搜索的极限频率。
- TRACECLK 约束 50 MHz DDR、IDELAY 参考 200 MHz；保留 4 个 IDELAYE2、1 个 IDELAYCTRL、
  4 个 trace IDDR、BUFIO/BUFR，未用 false path 排除 trace 输入 setup/hold。
- 最差 setup 路径从 SWDIO IDDR 到 SWD 状态寄存器，数据延时 3.935 ns，其中布线 3.018 ns。
  继续升频还需检查该采样路径，面积下降不保证性能提升。
- 报告仍列有旧 SWD/JTAG 等端口未指定 input/output delay；通过现有约束不能表述为所有
  板外接口已完成时序建模。trace 线缆时序假设仍待实板核验。
- CM3 功能仿真/上游字节对照/OpenCSD、生产 C mocks、Web WASM 测试通过；本次 native-32
  实板 DAP/CDMA 吞吐、USB 和 ETM 尚未验收，原有已知可用 prebuilt 配对保留。
