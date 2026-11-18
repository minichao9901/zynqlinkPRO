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

三个 8:1 DDR OSERDESE2 并行发送 TCK/TMS/TDI。TDO 经 IDELAYE2（0–31 tap）和 ISERDESE2 将每个半拍时隙的样本写回。主机按时隙偏移对齐 TDO，能跨一个或多个 TCK 周期取样。每个事务最多 512 个并行字，包含前导和尾部空闲，ACK 或多条调试事务由上层决定。AXI 与并行时钟间用启动/完成握手，缓冲按扫描前后分时归属，最后一字的结束标记随波形写入 TX BRAM。

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

首轮构建暴露 PS7 的 FCLK 端口使能需同时设 PCW_EN_CLKx_PORT。输出目录检查还暴露生成的初始化 Tcl 在 *processing_system7* 目录。首轮仿真补齐 XSim secureip 和 timescale 后通过。对应脚本已修正。首个路由候选的 CDC 报告标出扫描长度的直接跨域，最终实现让结束标记随双时钟 BRAM 过域。最终布线通过，WNS +2.482 ns，WHS +0.060 ns，WPWS +0.264 ns。CDC 撤去扫描长度的直接跨域后，报告仍标出锁定丢失和软件保持信号合成的异步复位断言，复位释放由四个 CLKDIV 拍同步。外部引脚建立保持和信号完整性待板测。详见[离线证据](offline-evidence.txt)和[配对 manifest](../../../prebuilt/jtag-only-200mhz-20261118/manifest.json)。

## 实板待验

首次上板先确认 J7 探针空闲和下载线序列号，然后经 RAM 临时加载。实验入口的 load 和 scan 默认只预览，现场确认后才加 --execute。加载器核对配对哈希、运行签名和物理 MEM-AP0 的 ELF 执行段。可先以 J7 pin 25 至 pin 27 的短接做回环。回环只证明物理输出和返回，TCK 频率和占空比由示波器在实验接口量测。再换 HPM6800EVK，从较低实验档开始验证实际 TAP，保留失败、TDO 相位与恢复记录。200 MHz 的完整目标协议测试需能承受该速率的外部 TAP。

```powershell
python -X utf8 toolbox.py project run jtag.experiment -- load --pair prebuilt/jtag-only-200mhz-20261118 --cable-serial <serial> --out build/jtag200/load
python -X utf8 toolbox.py project run jtag.experiment -- scan --kind loopback --cable-serial <serial> --mhz 200 --out build/jtag200/loopback-200
python -X utf8 toolbox.py project run jtag.experiment -- scan --kind idcode --idcode 0x1000563d --cable-serial <serial> --mhz 50 --out build/jtag200/hpm-50
```

### 2026-11-18 SuperLinkPRO DFU 对端

HPM5301EVKLite（序列号末八位 0AE800E0）在同一 USB 端口 1-2.3 经 HID 切到 0D28:0207。J7 使用 Digilent HS3 序列号 210299008529。起始为 JTAG 启动且 PL 电平转换关闭，实验 bit/ELF 经 RAM 临时加载，物理 MEM-AP0 比对 592 字节执行段通过。

按标称 50 MHz 扫查 IDCODE 三轮，三轮采样全为 0xff。保留原始失败，追加 50 MHz 以及波形加长的 10/5 MHz 对照，每档分别用 IDELAY tap 0、16、31，采样仍全高。频率来自 FCLK1 寄存器和波形时隙计算，未用仪器量测。当前尚未区分接线、目标 JTAG 输出和探针引脚链路。下一步先确认四线共地或用物理短回环定位，再验证目标 IDCODE、DMI 和 RAM。SuperLinkPRO 留在 DFU。本轮没有访问目标 RAM 或执行非易失存储操作。[实板证据](superlink-dfu-jtag-attempt.json)

### 正式探针对照

按用户要求从 J200 切回 J7 正式 JTAG/RAM 配对 release-20261106。物理 MEM-AP0 核对 85,844 B 执行段通过，ZynqLinkPRO CMSIS-DAP 枚举为 0D28:0204、序列号 12345678。此时 HPM5301 的 USB 序列号在运行态和 DFU 均回查不到，未确认目标 JTAG 引脚已释放，本次对照未发送外部 JTAG 扫描。J7 留在正式 RAM 配对。保留原 J200 全高记录，待 HPM5301 回到 DFU 后用正式链路扫 IDCODE。[正式探针对照证据](production-probe-contrast.json)

## 同接线复测与修复

用户用正式探针在 10 MHz 读到 0x1000563D。原生 CLI 随后独立读到同一 IDCODE 和 DTMCS 0x00007071。切回原实验配对后，50、10、5 MHz 仍全高，AP0 逐字写入波形也复现。加载时曾遇到 XSCT 在系统复位后沿用旧 APU 上下文，改为重选并验证读回后恢复。

新配对在 J7 N15（nTRST）和 M14（nSRST）保持高电平。同接线复测，50 MHz IDCODE 随即通过。两根复位线的旧电平未单独量测。新配对的 200 MHz 内部时序 WNS +2.482 ns、WHS +0.060 ns，XSim 六档继续通过。

80/100 MHz 能读复位后的默认 IDCODE，显式装载 IR 时需要调 TDI。保持 TMS 时序，TDI 提前一个串行时隙后，两档各 10 次显式 IDCODE 通过。CLI 用 --tdi-advance 1 指定该调整。100 MHz 初次 RAM 测试在恢复后的 SBCS 查询收到无效 DMI 响应，随后 200 MHz 核对原值，100 MHz 改 tap、采样时隙和 idle 后复测通过。

| 标称 TCK MHz | IDCODE 样本 | RAM 测试 tap / TDO 时隙 / DMI idle 拍 | RAM 写读与恢复 |
|---:|---:|---|---|
| 50 | 3/3 | 0 / 36 / 64 | 通过 |
| 66.667 | 3/3 | 0 / 36 / 86 | 通过 |
| 80 | 10/10 | 8 / 35 / 103 | 通过 |
| 100 | 10/10 | 16 / 36 / 192 | 通过 |
| 160 | 3/3 | 8 / 37 / 205 | 通过 |
| 200 | 100/100 | 8 / 39 / 256 | 通过 |

RAM 测试固定为 HPM5301 ILM 的 SBA 系统地址 0x0105FFF0，双读备份 4 字节，写入测试字、读回、还原并逐档核对。当前 J7 留在实验配对的 50 MHz 档，最后复核 IDCODE 三轮通过。本轮证据来自一块 HPM5301EVKLite 和当前接线，TCK 由时钟寄存器与波形时隙推算，引脚示波器量测、长时间吞吐和其他板卡待验。整个过程未执行 Flash/QSPI 写入或擦除。

- [复位释放版配对和 SHA-256](../../../prebuilt/jtag-only-200mhz-reset-release-20261118/manifest.json)
- [最终硬件结果和失败对照](hpm5301-reset-release-hardware.json)
- [复位释放版仿真与时序](reset-release-offline-evidence.txt)

## 六档 RAM 压力测试

已记录六档实测吞吐、100/200 MHz 长窗对照及失败后的恢复。见[HPM5301 RAM 压力报告](ram-stress/README.md)。

## PL 块流水与真实目标仿真

见[Hazard3 RTL / HPM5301 对照](pipeline/README.md)。

## 段间加速和 HPM5301 DMI 错位修复

见[Hazard3 A/B 和 HPM5301 只读边界对照](segment-overhead/README.md)。

固定 EXE、远端 main、Pages、Release 和 QSPI 不属于本轮交付。
