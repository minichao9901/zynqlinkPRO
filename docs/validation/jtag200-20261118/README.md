# J7 纯 JTAG 50–200 MHz 实验

实验分支为 codex/jtag-only-200mhz，基线为 03b6a1da。实验配对使用 XC7Z020-CLG400-2 和 J7 的 TCK（29/L15）、TMS（31/L16）、TDI（25/M15）、TDO（27/L14），I/O 为 LVCMOS33。PL 只实例化 JTAG 波形与采样、AXI 寄存器和 PS 所需互连。PS ELF 只响应选档和输入延时 mailbox。操作入口通过现有下载线的物理 MEM-AP0，不需要 Web、CMSIS-DAP、USB 串口、SWD、流采样或 ETM。

## 时钟与工作档

| TCK MHz | FCLK1 MHz | DDR 高速时钟 MHz | 并行时钟 MHz | 每个半周期的时隙 |
|---:|---:|---:|---:|---:|
| 50 | 50 | 200 | 50 | 4 |
| 66.667 | 50 | 200 | 50 | 3 |
| 80 | 40 | 160 | 40 | 2 |
| 100 | 50 | 200 | 50 | 2 |
| 160 | 40 | 160 | 40 | 1 |
| 200 | 50 | 200 | 50 | 1 |

这是可运行时选择的六个预设。FCLK0 的约束为 7.5 ns，FCLK2 给 IDELAYCTRL 提供固定 200 MHz 参考。PS 初始化由 Vivado 生成，IO PLL 为 33.333 MHz 参考 ×48。选档时只调整 FCLK1 的分频（÷32 或 ÷40）。等上一次扫描完成后，PS 先保持 MMCM 和串行器复位，改分频后等待重新锁定。

三个 8:1 DDR OSERDESE2 并行发送 TCK/TMS/TDI。TDO 经 IDELAYE2（0–31 tap）和 ISERDESE2 将每个半拍时隙的样本写回。主机按时隙偏移对齐 TDO，能跨一个或多个 TCK 周期取样。每个事务最多 512 个并行字，包含前导和尾部空闲，ACK 或多条调试事务由上层决定。AXI 与并行时钟间用启动/完成握手，缓冲分时所有权，最后字地址从启动前保持到完成。

## 离线复现

从实验 worktree 执行以下命令。

```powershell
python -X utf8 toolbox.py project run jtag.experiment -- sim
python -X utf8 toolbox.py project run jtag.experiment -- firmware
python -X utf8 toolbox.py project run jtag.experiment-build
```

Vivado/XSim 2018.3 的实际 MMCM、OSERDES、ISERDES 和 I/O 延时模型通过六档。每档观测 312 个 TCK 上升沿和 312 个下降沿，验证周期、两个半周期、TMS/TDI、扫描结束和切档无多余 TCK。输入端回收 IDCODE 0x1000563D 及 257 位确定性伪随机数据。

| TCK MHz | TCK 周期 ns | 仿真 RX 偏移范围（时隙） |
|---:|---:|---:|
| 50 | 20 | 25–32 |
| 66.667 | 15 | 26–31 |
| 80 | 12.5 | 27–30 |
| 100 | 10 | 27–30 |
| 160 | 6.25 | 28–29 |
| 200 | 5 | 28–29 |

用于该表的 JTAG TAP 行为模型回包延时为 0.8 ns。RX 偏移包含了 FPGA 的串并转换流水延迟。40 MHz 参考的两档会产生 XSim 的 MMCM 参考周期属性提示，实测仿真周期为表值。板上仍需重新扫 tap 与偏移。

首轮构建暴露 PS7 的 FCLK 端口使能需同时设 PCW_EN_CLKx_PORT。输出目录检查还暴露生成的初始化 Tcl 在 *processing_system7* 目录。首轮仿真补齐 XSim secureip 和 timescale 后通过。对应脚本已修正。布线时序和 bit/ELF/初始化 Tcl 哈希见配对 manifest。

## 实板待验

首次上板先确认 J7 探针空闲和下载线序列号，然后经 RAM 临时加载。实验入口的 load 和 scan 默认只预览，现场确认后才加 --execute。加载器核对配对哈希、运行签名和物理 MEM-AP0 的 ELF 执行段。可先以 J7 pin 25 至 pin 27 的短接做回环。回环只证明物理输出和返回，TCK 频率和占空比由示波器在实验接口量测。再换 HPM6800EVK，从较低实验档开始验证实际 TAP，保留失败、TDO 相位与恢复记录。200 MHz 的完整目标协议测试需能承受该速率的外部 TAP。

```powershell
python -X utf8 toolbox.py project run jtag.experiment -- load --pair prebuilt/jtag-only-200mhz-20261118 --cable-serial <serial> --out build/jtag200/load
python -X utf8 toolbox.py project run jtag.experiment -- scan --kind loopback --cable-serial <serial> --mhz 200 --out build/jtag200/loopback-200
python -X utf8 toolbox.py project run jtag.experiment -- scan --kind idcode --idcode 0x1000563d --cable-serial <serial> --mhz 50 --out build/jtag200/hpm-50
```

截至本次离线阶段，板上 bit/ELF、引脚频率、外部信号裕量、HPM6800EVK 收发与现场恢复均待实板。固定 EXE、远端 main、Pages、Release 和 QSPI 不属于本轮交付。
