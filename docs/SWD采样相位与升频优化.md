# SWD 采样相位与升频优化（进行中）

2026-10-25。保留 `releases/dma50_20261025/` 作为回退版本。

> 当前正在验证第二版：统一 FCLK 域采样。下文 Q1/Q2 与 multicycle 描述属于
> 已退出的第一候选；当前 RTL 已去掉派生 SWCLK 采样时钟及该 multicycle 例外。

## 第二版：统一 FCLK 域

- SWCLK 由 FCLK 状态机寄存输出，不再额外经过 BUFG。
- 早采样：在预备发出上升沿时捕获输入，并保持到下一位的消费位置。
- 晚采样：IDDR 直接由 FCLK 驱动，使用其下降沿样本；采样时刻位于消费前
  半个 FCLK，即四分之一 SWCLK 周期。
- `SWD_CFG[17]` 为 1 选择早采样，为 0 选择晚采样。软件可实时切换。
- ACK 捕获、ACK 解码分两拍；parity 捕获、parity 判断分两拍。高速输入的
  半拍路径只进少量捕获寄存器，避免把多层判断逻辑串在同一半拍中。
- 接收数据、发送数据与 SWJ 序列改为移位寄存器，去掉动态位索引选择/写使能。

第一候选的实机记录：早模式 1/10/25/30/34.6/39.1 MHz IDCODE 通过，45/50 MHz
失败；晚模式 39.1/45/50 MHz 通过，25 MHz 失败。说明固定采样相位存在频段
依赖，不能简单统一选择一个边沿。见 `phase_candidate50_*.json`。

第二版行为模型使用延迟非阻塞赋值保留每个目标数据跳变；旧连续赋值的惯性
延时会在 TCO 大于位周期时错误过滤数据，现已修正。相同脚本验证了早/晚采样
窗口的不同；第二版完整矩阵见 `fclk_sampler_simulation.json`。

汇总计时第一候选结果：batch 224.27 ms，DMA/cache 上传 4.69 ms、下载 2.68 ms；
搬运约占这三项之和的 3.2%，并非当前主要瓶颈。该结果包含连接与恢复开销，
不能与单独的 SRAM 基准计时直接相减。日志 `candidate50_profile.json`。

## 第一候选历史记录（已退出）

## 采样问题

ADIv5 B4.3.1 规定目标在 SWCLK 上升沿更新输出。原线级测试目标在下降沿
发数，无法检出真实目标较快响应时的采样错位；现已改为上升沿发数，并将
输出延时参数化。旧下降沿方案在 1 ns 目标延时下失败，新上升沿方案在
50 MHz 的 1–16 ns、60 MHz 的 16 ns、81.8 MHz 的 12 ns 下通过测试。
81.8 MHz / 16 ns 失败，说明仍必须检查实际采样窗口，不能只看时钟频率。

原始仿真矩阵：`results/optimization/phase_simulation_matrix_final.json`。
这里是行为仿真，尚未包含真实线路和布局布线延时。

来源：[Arm ADIv5](https://documentation-service.arm.com/static/622222b2e6f58973271ebc21?token=)。

## 本轮实现

- `SWD_CFG[17]`：1 选择 IDDR Q1，上升沿捕获；0 保留原 Q2，供实测比较。
- vendor 0x80：设置/查询相位，同时返回真实 FCLK 及 CFG，传输忙时拒绝修改。
- 新请求首位与 start 接收重叠；写 ACK 后直接完成已开始的 turnaround。
- PLL 分频只向下取整，确保不超过请求的最大频率。
- vendor 0x81：默认关闭的汇总计时；可统计 batch、DMA/cache 处理时间，
  不再逐次 MMIO 写非缓存 trace。

借鉴 HFLink 的发数与采样分别控制思路。本轮只实现两个可切换的采样边沿，
尚不等同于 HFLink 的细粒度采样延时调节。

## 软件调频与实现时序

改变 PS FCLK 分频不需要重新综合或重新生成 bitstream。已有 routed DCP 可
直接重跑各频率的 STA；脚本 `fpga/report_clock_limits.tcl` 只报告，不改布局。
改变采样逻辑或状态机则需要重综合被修改的 RTL；其余 IP 继续用 OOC 缓存。

Q1 的消费发生在下一次 SWCLK 上升相位，即两个 FCLK 后。对 Q1 → FCLK 的
路径按实际使能关系设置 setup=2、hold=1，二者均显式 `-end`；Q2 保持单拍。
这不是跨时钟的 false path。依据：[AMD UG903 慢时钟到快时钟](https://docs.amd.com/r/2023.2-English/ug903-vivado-using-constraints/Example-Two-Setup-3/Hold-2-end)。

IO PLL 约 1.8 GHz，当前整数分频的档位如下：

| 请求 SWCLK | 实际 SWCLK | FCLK 分频乘积 |
|---|---:|---:|
| 50 MHz | 约 50 MHz | 18 |
| 60 MHz | 约 60 MHz | 15 |
| 75 MHz | 约 75 MHz | 12 |
| 80 MHz | 约 75 MHz | 12 |
| 82 MHz | 约 81.818 MHz | 11 |
| 90 MHz | 约 90 MHz | 10 |

实机频率、误码与 SRAM 性能结果将在验证后补入。

## AXI 内部路径

首次用 180 MHz FCLK 检查既有互联布局，发现跨多个 interconnect 的 ready /
数据路径超过 9 ns，不能直接把原来的整个 AXI 互联升到 180 MHz。
`fpga/axi_pipeline.tcl` 将四个互联的 crossbar 设为 32 bit，并启用各外部
S/M 边界寄存器。HP0 侧保留必要的宽度转换，批量 BRAM 数据保持原生 32 bit。
这部分是电路变化，需要重新实现相关 IP；单纯修改分频不需要这样做。

Q1 与 Q2 的最快时序条件不同：发布模式用 Q1，Q2 对照模式只允许 ≤50 MHz。
高频切换会强制选择 Q1。STA 的模式常量只在打开 routed DCP 后施加，不让
实现过程把诊断用的 mux 优化掉；50 MHz Q2 模式另行检查。

## 工具

```powershell
python tools/dap_clock_probe.py --phase 1 --output results/optimization/phase1_sweep.json
python tools/benchmark_sram_optimized.py --tag phase60 --speed 60000 --sessions 3 --loops 100
python tools/capture_optimization.py phase60_idcode --dpid --speed 60000
python tools/dap_profile.py start
# 在另一个命令中运行一轮 SRAM 基准后，读取汇总计时：
python tools/dap_profile.py stop --output results/optimization/profile.json
```

基准在 50 MHz（或更低请求值）连接并设置 F103 HCLK，之后切到被测频率；
结束时回到连接频率恢复 SRAM。高频阶段出错也会尝试恢复，日志保留错误。
