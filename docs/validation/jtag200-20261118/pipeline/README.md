# J7 纯 JTAG PL 流水和真实 Hazard3 对照

2026-11-18，实验分支 codex/jtag-only-200mhz，Zynq-7020/HS3 210299008529。AXI 将整个块和描述符移交给 50/40 MHz 的 CLKDIV 域。PL 复用正式版本的 RISC-V DMI/SBA 核和块引擎，支持 HPM5301 ILM 地址、最多 256 字、一次一个块。每块开始时建立 DMI 会话，块内维持 SBA 自增、预读与返回流水，最后用 RDBUFF 核对。原始波形路径的六档保留，新增流水入口覆盖 50、160 和 200 MHz。

## Hazard3 实际 RTL

复用了 E:/zynq_harzard3_mcu 的 MCU 源码和其上游 Hazard3 DTM、异步 APB 桥、DM、CPU 与 AHB SRAM。目标 CPU 80 MHz，运行 SRAM 自循环指令。仅在仿真副本的 SBA 入口将 HPM 的测试地址别名映射到 Hazard3 的 0x80000000 SRAM，TDO 模拟 0.8 ns 板级延时。探针侧使用 Vivado 2018.3 的实际 MMCM、OSERDES、ISERDES 和 IDELAY 模型，AXI 提交并完成后计时。每个工作点向真实 SRAM 写 128 字，再通过 JTAG 读回并逐字校验。

| TCK MHz | DMI idle 拍 | SRAM 读 / 写 MB/s | 结果 |
|---:|---:|---:|---|
| 50 | 64 | 1.456 / 1.456 | 通过 |
| 50 | 16 | 2.336 / 2.336 | 通过 |
| 200 | 256 | 1.988 / 1.988 | 通过 |
| 200 | 128 | 3.025 / 3.024 | 通过 |
| 200 | 64 | 4.093 / 4.092 | 通过 |
| 200 | 32 | 4.971 / 4.968 | 通过 |
| 200 | 24 | 5.252 / 5.250 | 通过 |
| 200 | 20 | 5.405 / 5.403 | 通过 |
| 200 | 18、16、8 | — | DMI BUSY |

200 MHz/idle 20 时，每向 128 字用 142 个段，包括块头、DMI 激活和完成检查。独立统计 9,125 个 TCK，与 PL 计数一致。读块约 94.725 µs，其中 TCK 活动 45.625 µs，其余约 49.1 µs 来自分段组织、收发排空、状态机会合及命令完成。按稳态每字一次约 46 拍 DR 路径、加 20 拍 idle 估算的纯线速上限为 12.12 MB/s，按此次实际 TCK 计数但去掉段间空隙为 11.22 MB/s。含当前控制开销的 RTL 仿真读写成绩为约 5.40 MB/s。

原先 VexRiscv 仿真覆盖真实 JtagBridge 的 IDCODE 与 IR 缓存，首读 56 TCK，缓存后 40 TCK。修正旧用例在每次调用内覆盖整体计数起点的问题，100 次 IDCODE 共 4,000 TCK。该测试覆盖 IDCODE 事务。

[Hazard3 扫档及来源](hazard3-80mhz.json) · [200 MHz idle 细扫](hazard3-200-idle-fine.json) · [旧 VexRiscv 仿真入口](../../../../fpga/sim/tb_jtag_vexriscv.sv)

## HPM5301 实板

使用 1 KiB ILM、队列深度 1。读取目标时钟寄存器 CLOCK_CPU0 0x03110101，PLL0 配置解码为 720 MHz，CPU 360 MHz、AHB 180 MHz，测试前后寄存器一致。

| 数据路径 | TCK MHz | idle | 读 / 写 MB/s |
|---|---:|---:|---:|
| 正式 CMSIS-DAP | 25 | 8 | 1.052 / 1.025 |
| 正式 CMSIS-DAP | 25 | 64 | 0.645 / 0.627 |
| 正式 CMSIS-DAP | 50 | 64 | 0.988 / 0.993 |
| 正式 CMSIS-DAP | 50 | 16 | 1.523 / 1.416 |
| 新流水 Zynq 本地 | 50 | 64 | 1.359 / 1.374 |
| 新流水 Zynq 本地 | 50 | 16 | 2.057 / 2.090 |

正式测速从 PC 通过 USB 计时，新流水由 Zynq A9 计时并检查缓冲数据，两个数字保留各自计时边界。新流水 50 MHz 两档分别通过读、写和混合窗口各三轮 3 秒。200 MHz 使用复位和采样已验证的原始 PHY，切到块流水后，初次只读预检报无效 DMI。在 idle 256 下，四个 tap 与七个时隙组合有的在启动返回无效状态、有的完整完成但首字与备份不符，200 MHz 块流水仍待解决。独立读回证实该只读测试的 ILM 与哨兵一致。TCK 值来自寄存器或仿真时钟，实板引脚频率待独立量测。

[正式 50 MHz 对照](formal50.json) · [25/50 MHz idle 对照](formal25-50-idle.json) · [流水实板试跑](pipeline-hpm-pilot.json) · [流水 50 MHz 测速](pipeline-hpm50.json) · [流水 200 MHz 只读对照](hpm5301-200-readonly-phases.json)

## 恢复与复现

实板每次写入前双读备份本轮 ILM 与哨兵，全部写入限于测试 RAM。最终恢复原复位释放版 bit/ELF，再重新读取 1 KiB ILM 及哨兵，逐字节一致。系统运行态和 DMI/SBA 控制已恢复。未擦写目标 Flash 或探针 QSPI。

XSim 可通过 tools/jtag200_hazard_sim.py 的 --hazard3-root 指定源仓库，增加 --fine 可重跑 200 MHz idle 细扫。实板实验使用 tools/jtag200_pipeline.py，测试步骤在 --help，所有硬件操作只有显式 --execute 才执行。构建和时序记录见随附证据。

[流水试验配对](../../../../prebuilt/jtag-only-200mhz-pipeline-20261118/manifest.json) · [布线和回归记录](offline-routing.txt) · [恢复校验](final-restore.json)
