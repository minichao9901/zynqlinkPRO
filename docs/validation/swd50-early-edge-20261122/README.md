# 50 MHz SWD 提前安排 ACK 后的一个边沿

2026-11-22，Vivado 2018.3 XSim。现版参考队列使用 133.333 MHz AXI、100 MHz quad_clk、50 MHz SWCLK。Cortex-M3 DesignStart 模型 HCLK128，SWDIO 回传延迟设为 16 ns，主对照用 slot 22、idle 0。对照只替换 XSim 使用的 swd200_link，候选在 build 目录生成。仿真使用真实的 MMCM、OSERDES、ISERDES 和 IOBUF 模型，台架提供 AXI、载荷 BRAM 和模拟目标端的 RTT 数据生产。没有实板操作或产品 bit/ELF 交付。

## 提前边沿如何处理

当前协议配置为单拍换向，WAIT/FAULT 无数据段。紧接 ACK 的第一个上升沿，读 OK 时是 D0，写 OK、WAIT、FAULT 时是换向。四种情况下探针都释放 SWDIO，因此可以在 ACK 判定之前把这一个边沿放进发送段。ACK 和数据槽位所在 quartet 相同且满足发送段时序时，D0 在最后一个 ACK 采样后两个 quad 周期进入 RX。读 OK 用单独捕获的 D0 拼回数据，并计入偶校验。写 D0、读 D1 及后续路径仍由已解码的 ACK 决定。[Arm SWD 协议与时序图](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Low_Pin-Count_Debug_Interfaces_for_Multi-device_Systems.pdf)

## 协议验证

| 事务，slot 22 / idle 0 | 最后一位 ACK 至下一上升沿，原版 → 候选 | 上升沿数 |
|---|---:|---:|
| 读／写 OK | 50 → 20 ns | 46 |
| 读奇偶校验错 | 50 → 20 ns | 46 |
| 读／写 WAIT | 60 → 20 ns | 13 |
| 读／写 FAULT | 60 → 20 ns | 13 |

脚本目标逐位校验请求、写数据及校验位，在换向期间检查引脚驱动，监视目标与探针的驱动重叠。正常读覆盖 D0 = 0 和 1，错误读复核返回数据及校验状态。实际批次调度器自动重试一次 WAIT，成功完成两笔。FAULT 和奇偶校验错均以对应状态结束批次，后续描述符未发出。候选另以 slot 24 / idle 2 复核，OK 和错误读为 48 个沿，WAIT/FAULT 为 15 个沿，ACK 后间距仍为 20 ns。

## 窗口和计时边界

- **标准 SRAM 512 字**。保持与 CMSIS-DAP 快路径一致的两批 256 字，首项 DP RDBUFF 保持 TAR，每批尾部用 DP RDBUFF、CTRL/STAT 收尾，交替载荷银行。窗口从首批的银行选择到第二批的 CTRL/STAT 结果可查。写前预置载荷，读后逐字核验两银行。TAR 设置和测量后的载荷检查在窗口外。
- **RTT 8 KiB 环、2 KiB 块**。模拟已接管 SWD 队列的 CDC 路径。每次经实际队列取 24 B 描述符、两页负载，再写 RdOff，经 DP RDBUFF 和 CTRL/STAT 确认，并核对目标 SRAM。四次确认依次为 6144 → 0 → 2048 → 4096 → 6144，第四块在前一块确认后发布。计时从第一次描述符访问前到最终 RdOff 确认，包含模拟载荷 BRAM 读核对和 AXI 批次交接。
- **停钟**。在物理 SWCLK 上升沿间扣除 20 ns，累加超出部分。窗口耗时还含第一沿之前和最后一沿之后的控制时间。仿真覆盖引脚、队列和台架 AXI/BRAM 时序。PC 数据来自既有实板 A 布局，包含 PS、CDMA、USB 和主机调度。

## A/B 结果

| 仿真负载 | 窗口耗时，µs | 累计停钟，µs | 省下停钟，µs | 两版上升沿数 |
|---|---:|---:|---:|---:|
| SRAM 读，512 字 | 497.880 → 487.530 | 20.960 → 10.610 | **10.350** | 23,832 |
| SRAM 写，512 字 | 493.365 → 482.925 | 15.930 → 5.500 | **10.430** | 23,858 |
| RTT，4 × 2 KiB | 2,082.0375 → 2,039.0925 | 122.680 → 79.730 | **42.950** | 97,944 |

三项上升沿总数相同，无短周期。标准写的两次 WAIT 和 RTT 的 16 次 WAIT 均保持原响应和重试行为。ACK 段 DRAIN 的 quad 周期在 SRAM 读、写和 RTT 分别从 2,072、2,080、8,560 减至 1,036、1,040、4,280。相同物理时钟下，成功事务约省两个 quad 周期。读尾等待计数在前后完全相同，标准读还有 1,032 个 quad 周期用于读数据段末尾回采。内部计数与外部引脚停钟有重叠。普通共享引脚回归的 100 MHz JTAG 和 100 MHz SWD 也通过。

按每 2 KiB 归一化，将引脚停钟收益与既有实板 PC 差额比较。历史 PC 数据使用 HCLK96，现用 A 使用 HCLK128。这里计算的是已经在数字模型中定位的时间相当于实际差额的多少。套用差额的条件是该段节省能传递到 PC 的关键路径。

| 负载 | 历史 / 现用 A，MB/s | PC 时间差，µs / 2 KiB | 仿真省下停钟，µs / 2 KiB | 可解释的时间差 | 差值余量，µs / 2 KiB |
|---|---:|---:|---:|---:|---:|
| SRAM 读，512 字 | 4.047 / 3.846 | 26.42 | 10.35 | **39.2%** | 16.07 |
| SRAM 写，512 字 | 3.983 / 3.873 | 14.70 | 10.43 | **71.0%** | 4.27 |
| RTT，4 × 2 KiB | 3.995 / 3.810 | 24.92 | 10.74 | **43.1%** | 14.18 |

RTT 四包通过最终 RdOff 的数字窗口折算为 3.935 → 4.017 MB/s。主机端吞吐需另行验证。本轮结果定位到 ACK 分段的等待成本，留待归因的时间还包括读尾回采、批次交接和 PC 路径。

## 复现

在仓库根目录执行，输出路径也可使用新的 build 子目录。

```powershell
$edge = @('--swd-only','--half-rate','--return-ns','16','--swd50-faults')
python -X utf8 tools/selectio_cm3.py @edge --swd-slot 22 --idle 0 --out build/swd50-edges-before
python -X utf8 tools/selectio_cm3.py @edge --swd-slot 22 --idle 0 --out build/swd50-edges-after --early-swd50
python -X utf8 tools/selectio_cm3.py @edge --swd-slot 24 --idle 2 --out build/swd50-edges-slot24 --early-swd50
$window = @('--swd-only','--half-rate','--swd-slot','22','--idle','0','--return-ns','16','--target-clk-ns','7.8125','--wire-budget','--swd50-windows')
python -X utf8 tools/selectio_cm3.py @window --out build/swd50-windows-before-run2
python -X utf8 tools/selectio_cm3.py @window --out build/swd50-windows-after-run2 --early-swd50
```

[原始仿真计数摘录](results.txt) · [历史与 A 布局 PC 数据](../swd50-review-20261122/README.md) · [ZL-296](../../项目问题跟踪列表.md)
