# ORBTrace 分支资源与 LUT 优化分析

> 此文件保留优化前候选的分析。**当前结果已更新为 19,228 LUT（减少 5,191）**，
> 见 [本次 bit 的资源与优化结果](orbtrace-area-native32.md)。下面的“正在构建”和 hold 失败
> 均指旧候选，不代表当前 bit。旧 DCP 已被重新构建覆盖，仅保留报告及旧 DCP 的 SHA。

分析对象：2026-10-30 07:11 完成布线的 `system_wrapper_routed.dcp`，xc7z020clg400-2。
它尚未通过 trace 输入 hold 检查，因此**不是已验收 bit**。后续正在加入的校准输入延时
不包含在本报告中；不能把这里的数值冒充后续构建结果。

原始报告：`build/orbtrace_area/routed_utilization.rpt`、`hierarchy.rpt`、`control_sets.rpt`。
复现：`python tools/run_vivado.py -mode batch -nojournal -source fpga/report_area.tcl`。

## 总体

| 资源 | 使用 | 器件容量 | 比例 |
|---|---:|---:|---:|
| LUT | 24,419 | 53,200 | 45.90% |
| FF | 35,219 | 106,400 | 33.10% |
| BRAM Tile | 10 | 140 | 7.14% |
| DSP | 1 | 220 | 0.45% |
| Slice | 12,070 | 13,300 | 90.75% |

LUT 中 logic=23,360，LUTRAM=698，SRL=361；latch=0。
有 1,317 个不同 control set。Slice 占用比 LUT/FF 比例高很多，应连同控制集、宽复用器和
寄存器布局一起优化；不能只看“LUT 还剩一半”就认为布局宽松。

## 模块分布（实现后）

| 模块 | LUT | FF | 说明 |
|---|---:|---:|---|
| SWD/JTAG/probe 总模块 | 12,754 | 17,508 | 约占总 LUT 52.2% |
| PS AXI interconnect | 5,031 | 7,326 | 7 路外设主互联 |
| DMA interconnect | 1,605 | 3,421 | CDMA 到 DDR/BRAM 的互联 |
| CMD interconnect | 1,166 | 1,944 | PS/CDMA 到 CMD BRAM |
| RSP interconnect | 1,166 | 1,944 | PS/CDMA 到 RSP BRAM |
| Packet interconnect | 905 | 877 | PS/CDMA 到 packet BRAM |
| CDMA 本体 | 774 | 1,026 | 并不是 DMA 通路的主要面积 |
| ETM 接收器 | 390 | 473 | 约占总 LUT 1.6%；OOC 综合为 388 LUT |

五个互联合计 9,873 LUT，约占总量 40.4%。Vivado 提示跨层级 LUT combining 会使子项
相加略大于父项，不能把层级所有行累加为整机资源。

SWD/JTAG/probe 内部：

| 子模块 | LUT | FF |
|---|---:|---:|
| 控制器直接层（寄存器/诊断等） | 2,983 | 10,033 |
| JTAG core | 2,729 | 1,802 |
| 其中 JTAG shift | 1,330 | 792 |
| HSS sampler | 2,434 | 1,235 |
| RTT/HSS packet engine | 2,626 | 3,143 |
| DAP packet engine | 496 | 258 |
| SWD batch engine | 781 | 593 |
| SWD PHY/core | 709 | 444 |

## 优先级 1：消除不必要的 32→64→32 转换

这是已从生成的 XCI 和实现层级共同确认的事实，而不只是 RTL 推测：

- 当前有 7 个 64→32 downsizer、2 个 32→64 upsizer。
- 这些 converter 在实现中合计 **4,470 LUT、4,688 FF**。
- PS GP0 和多数外设实际只需要 32-bit；DDR HP0 的 64-bit 边界仍需要保留适当转换。
- `axi_pipeline.tcl` 的意图是 native 32，但当前生成 XCI 仍显示上述转换。必须排查配置
  传播和生成产物刷新，不能仅以父对象打印“32/USER”认定已经优化成功。

建议让 PS 外设、CMD/RSP/packet 路径保持 32-bit，只在 HP0 边界转换，并重新生成 IP、
综合对比。4,470 LUT 是**现有 converter 总成本**，不是承诺全部可省；新的边界转换、
寄存器和交叉开关仍有成本。之后再按时序需要保留 regslice，避免一次性取消流水线而
损失原有 USB/SWD 吞吐。

AMD [PG059 Width Conversion](https://docs.amd.com/r/en-US/pg059-axi-interconnect/Width-Conversion)
说明不同 SI/MI 位宽会实例化宽度转换；本项目的实际数量与开销以上述网表报告为准。

## 优先级 2：诊断快照改用 RAM，避免大规模 FF 存储和读复用

`swd_controller.v` 定义 9 组 `32 × 32-bit` 的 JTAG 诊断数组，源码容量共 9,216 bit。
控制器直接层占 10,033 FF，远大于正常控制寄存器需要的规模。实际可省多少需单独统计
优化后网表，不能直接把源码位数等同于物理 FF 数。

优先保留诊断地址接口，把存储写口与异步复位控制分开，评估 LUTRAM 或打包宽行 BRAM
实现；同步读增加等待时应正确处理 AXI RVALID/反压。只复位指针/有效计数，不清空整片
存储。也可以提供生产/调试编译配置：生产关闭内部快照、调试保留；这是功能取舍，应
明确暴露配置，不能悄悄删除调试能力。

RAM 推断与读口复位限制可参考 AMD [UG901](https://docs.amd.com/api/khub/documents/bL2Ru8vOVyVmhcvVCB6G5g/content)
和 [UG949](https://www.xilinx.com/support/documents/sw_manuals/xilinx2022_1/ug949-vivado-design-methodology.pdf)。
需要以 Vivado 2018.3 的实际综合结果验证，不能只加 `ram_style` 就宣称已省资源。

## 后续小项

1. Sampler FIFO 被显式指定 distributed RAM；本层实际有 352 LUTRAM。改成带预取的 BRAM
   FIFO可能再省几百 LUT，需保持 first-word 可用时序、posted-read flush 和背压语义。
2. `jtag_shift` 的 256-bit 按索引写入，以及多组 64-bit 回显，引入大量按位使能与选择。
   可比较分段缓冲或短扫描快路径；不能简单改移位方向或缩短长度，否则会破坏 LSB 顺序、
   JTAG chain 和 CMSIS-DAP 长序列。
3. 检查占用范围确有上限的内部计数器和复位/enable 粒度，以改善 control-set 和布局。
   外部可见的 32-bit 计数、时间戳回绕、协议长度不能直接截断。
4. ETM 目前只有约 390 LUT；固定四位宽/单 source ID 的收益上限很小，不应作为第一目标。

## 实施建议

先做 AXI native-32 的独立 A/B 综合，再做诊断存储的独立 A/B，记录 LUT/FF/BRAM、时序
和回归结果。这样可以把收益归因，也能避免同时改协议、存储和互联导致难以定位回退。
面积优化不替代 trace 输入延时修复：当前 `-1.716 ns` 输入 hold 仍需独立关闭。
硬件交付仍须按 AGENTS.md 生成并保留本次 bit/ELF、哈希、时序和实际上板验收记录。
