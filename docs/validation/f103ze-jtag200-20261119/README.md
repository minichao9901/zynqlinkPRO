# F103ZE 原始 HCLK 下的 JTAG200 测试


[JTAG 系统框图（SVG）](../../jtag-architecture.svg) · [系统框图（PNG）](../../jtag-architecture.png) · [128 MHz 读写时序（SVG）](../../jtag-128-timing.svg) · [读写时序（PNG）](../../jtag-128-timing.png)

## 本轮结果

在同一块 F103ZE 和 J7 上，最快持续 SRAM 档为 **HCLK128、TCK 125.490196 MHz、tap16、采样时隙34、idle13**。三轮各 60 秒，方向速率中位数为读 **8.21975**、写 **8.21896 MB/s**，各验证 737,472,512 字节。独立的三轮各 60 秒只读中位数为 8.21678 MB/s。最高持续双向工作频率为 **TCK 128.000 MHz**，同 HCLK/tap/时隙、idle17，读写均 **7.87153 MB/s**。每个 CLKDIV 字并行发出四个 TCK，连续提交 APACC DRW，并对回采数据逐字校验。以上为 A9 探针本地驻留图案的有效载荷吞吐，读写分别以各自方向占用时间计。[通过窗口及字节数](summary.json) · [可复测 bit/ELF 和哈希](../../../prebuilt/jtag-only-f103ze-quad-20261119/manifest.json)

| HCLK MHz | TCK MHz | idle | 混合实板读 / 写 MB/s | 对应仿真与验收 |
|---:|---:|---:|---:|---|
| 48 | 100 | 33 | 4.991 / 4.991 | 1 秒，CM3 5.049 / 5.049 |
| 96 | 100 | 19 | 6.081 / 6.081 | 3 × 60 秒，CM3 6.168 / 6.168 |
| 96 | 125.490 | 21 | 7.272 / 7.272 | 3 × 60 秒，CM3 7.395 / 7.395，实板占 98.3% |
| 128 | 125.490 | 13 | **8.220 / 8.219** | 3 × 60 秒，无等待协议模型 8.399 / 8.399，实板占 97.9%；完整 CM3 在所测 idle13 点收到 WAIT |
| 128 | 125.490 | 17 | 7.717 / 7.717 | 同条件 1 秒，CM3 7.872 / 7.872，实板占 98.0% |
| 128 | 128.000 | 17 | **7.872 / 7.872** | **3 × 60 秒**，CM3 8.029 / 8.030，实板占 98.0% |

固定 TCK 125.490 MHz，从 HCLK96 提升至 HCLK128 后可把 idle 从 21 减到 13，持续读写提升 13.0%。在较高的 TCK 128.000 MHz 档，所需 idle 增多，吞吐随之下降。[HCLK128 同 idle 仿真对照实测](f103-128-cm3-match-windows.json.gz) · [TCK128 长窗](f103-128-final-bracket-windows.json.gz) · [TCK128 CM3](upper-128-cm3.json)

相邻的 130.612 MHz 在 HCLK96 曾通过一次 60 秒，第二轮在 5.7 秒失败。HCLK128 重扫 133.333 MHz 有一轮混合跑至 21.5 秒失败，148.837 MHz 曾短时读写 9.129 MB/s，换次加载未持续复现。连续和段式路径均保留密扫结果，高频通过点不随频率单调变化。200 MHz 在 HCLK128/idle29 的 CM3 仿真读写均 10.511 MB/s，实板虽可重复识别 TAP，整块未获持续通过。所有实板 TCK 均来自 PS 时钟树与分频，缺少引脚示波器读数。[连续密扫](f103-128-quad-dense-windows.json.gz) · [段式复核](f103-128-segment-limit-windows.json.gz)

**主机路径。** 正式 USB 配对固定 TCK 60 MHz，HCLK48/96/128 三轮中位读分别 2.413/2.417/2.417 MB/s，写分别 2.390/2.394/2.396 MB/s；每档另跑 10 秒交替校验。实验配对则用 XSCT 与物理 AP0 交换实际 PC 数据；125.490 MHz 的长测会话另传 8 个不同的 1 KiB 块，主机读回中位 0.082、写入中位 0.127 MB/s。驻留图案绕开此主机传输，前表给出探针至目标的速度。[USB/96](f103-usb60-hclk96-state.json) · [USB/128](f103-usb60-hclk128-state.json) · [XSCT 每次时长](f103-128-quad-long-windows.json.gz)

**收尾。** 在低速 JTAG 扫描前临时开放 AFIO；现场双 TAP 从 TDO 起分别为 `0x3BA00477`、`0x06414041`。最后经独立低速 SWD 核对 20,168 字节目标 ELF 载入映像、原 4 KiB SRAM 与两侧哨兵、AFIO 可读位、APB2、时钟和内核运行态。SWJ_CFG 按已验证目标映像恢复为 2；HCLK 回到 48 MHz，Flash 等待周期和 USB 门控恢复。目标继续运行，目标 CDC 以 `F103CDC0001` 枚举在 COM34。J7 恢复初始 BOOT_MODE=0、LEVEL_SHIFTERS=0、FPGA_RESET=0x01f33f0f。目标 Flash 和探针 QSPI 编程次数均为零。本轮交付到本地实验分支；远端 main、固定 EXE、Pages、Release 下载包、QSPI 冷启动交付不适用。[最终独立读回](final-site.json)

## 仿真与实板基线

固定 SRAM 测试页为 `0x20008000–0x200083ff`。FPGA 和 A9 检查块地址和长度。CM3 台架使用 CortexM3DbgAXI、AXI SRAM、4 位 DAP 和 5 位边界 TAP、实际 Xilinx SelectIO 原语。目标 HCLK 48 MHz，TDO 另加 0.8 ns 延迟。检查写入后的目标模型 SRAM 及读回的 256 个字，包含末字和越过页尾的命令拒绝。原协议模型另覆盖 WAIT、末字故障和粘滞错误。板上时延、时钟相位与 SRAM 总线仲裁会改变通过点。

| TCK MHz | 路径 | idle | 仿真读 / 写 MB/s |
|---:|---|---:|---:|
| 50 | 段式 | 32 | 2.360 / 2.360 |
| 66.667 | 连续 | 33 | 3.366 / 3.366 |
| 100 | 连续 | 49 | 4.181 / 4.181 |

在 66.667/80/100 MHz 的 idle 9/13/17 写入返回 WAIT。相位选择也影响解码。[首轮模型结果](cm3-initial.json) · [idle 对照](cm3-idle.json)

J7 HS3 `210299008529` 开测时 BOOT_MODE=0，PL 隔离并处于复位。临时加载 `prebuilt/release-20261106` 后经物理 MEM-AP0 核对 85,844 字节。F103ZE CDC48 的两个 ELF 载入段均从目标读取核对。CPUID `0x411fc231`，DBGMCU `0x10036414`，RCC_CFGR `0x51040a`，8 MHz HSE、PLL ×6、AHB /1，HCLK 48 MHz。内核原先运行。先暂停并双读备份 4 KiB 和两端哨兵，再临时开放 AFIO，通过 1 MHz 的 JTAG TAP 和整区读取。

正式配对在推算 TCK 59,999,999 Hz、512 字、深度 32、256 块的三轮中位数为读 **2.4131**、写 **2.3898 MB/s**，另完成 10 秒交替验证。首次块读应答失败后经低速 SWD 恢复，请求 TDO 模式 16、切换到 60 MHz 后寄存器实际读回 17，重跑通过。两次独立恢复核对 4 KiB、哨兵、RCC、AFIO 可读位、APB2 与运行态。SWJ_CFG 按核对过的 CDC48 源码恢复为 2。[首次 USB](usb-initial.json) · [模式 16](usb-mode16.json)

复测示例，从工作树根目录运行。Vivado 2018.3，`--rtl` 指向本机授权的 CM3DbgAXI 源码目录。

```powershell
python -X utf8 tools/jtag200_cm3_sim.py --rtl <CM3DbgAXI/rtl> --out build/jtag200/cm3-new --point 15 2 29 33 --point 10 2 30 49
python -X utf8 tools/jtag200_f103_fixture.py --out build/jtag200/usb-new --execute --baseline
```

## 提高目标 HCLK 的同板对照

新测试页配对的实板 bit 和 ELF 见 [manifest](../../../prebuilt/jtag-only-f103ze-20261119/manifest.json)，路由 WNS +1.874 ns、WHS +0.087 ns，加载后由 HS3 的物理 MEM-AP0 核对 3,064 字节 OCM 执行段。连续路径以 1 KiB 为单位，图案预驻探针，A9 提交、等待、PL 逐字校验计入方向时间。分方向 MB/s 按该方向占用时间计，交替窗口中的每个方向各约占一半时间。一次性 PC 上传、USB 下载不在此项计时内。频率从探针实际时钟寄存器计算。覆盖范围为本板本接线，无外部频率计读数。

| HCLK MHz | TCK MHz | 混合 idle | 1 秒读 / 写 MB/s | 同页仿真读 / 写 MB/s |
|---:|---:|---:|---:|---|
| 48 | 100 | 33 | 4.991 / 4.991 | 5.049 / 5.049 |
| 96 | 100 | 19 | 6.080 / 6.080 | 6.168 / 6.168 |
| 128 | 100 | 13 | 6.713 / 6.713 | 6.816 / 6.816 |

每轮先用低速 SWD 核对 CDC48 和 RAM 双读备份，再用 1 MHz JTAG 读回，测试过程中不同图案与反相图案实际交替写入。96/128 MHz 临时在目标暂停时调 PLL、APB 分频、USB 门控和 Flash 控制器等待周期，用 SRAM 自循环及 DWT 验证目标 HCLK，随后恢复临时程序、核心寄存器、DWT。每次恢复独立 USB 配对并逐字节检查末轮图案、相邻 3 KiB 和两端哨兵，再复原备份的 4 KiB、映射、时钟及运行状态。开测夹具的首次子程序调度遗漏已读出的 TAP 字段，修正保存顺序后复测；该次在切换高速配对前退出，亦已恢复。

[48 MHz 逐轮](hclk48-windows.json) · [48 MHz 恢复](hclk48-state.json) · [96 MHz 逐轮](hclk96-windows.json) · [96 MHz 恢复](hclk96-state.json) · [128 MHz 逐轮](hclk128-windows.json) · [128 MHz 恢复](hclk128-state.json) · [48 MHz CM3 细测](cm3-fine.json) · [96 MHz CM3](cm3-96.json) · [128 MHz CM3](cm3-128.json)

## 每个 CLKDIV 周期连续发送四个 TCK

上一配对在 133.333 MHz 及以上逐段扫描。F103ZE/HCLK128 在 133.333 MHz 单秒交替读写为 3.836/4.038 MB/s，而同板 100 MHz 连续流水为 6.713/6.713 MB/s。四 TCK 路径让 TMS、TDI 每拍前移四位，独立回采每拍四位，按实际采样相位拼接前一 AP 应答；写入、末字、比较、错误停止以及块尾 RDBUFF/CTRLSTAT 沿用已有机制。四 TCK 模式要求每帧的 43+idle 个 TCK 可被四整除。新增 FCLK 分频点细扫 120.755 至 156.098 MHz 区间。

CM3 HCLK128 下，133.333 MHz/idle21 的 1 KiB 仿真读写均 7.858 MB/s，160 MHz/idle25 均 8.889 MB/s，200 MHz/idle29 均 10.511 MB/s。200 MHz 的另一个采样时隙在建链即失败。协议模型在理想应答、200 MHz/idle5 达 15.438/15.441 MB/s。对实板的效率比较使用同 HCLK、相同 idle 和块长度的完整 CM3 台架值。[四 TCK 模型](cm3-quad.json) · [96 MHz 模型](cm3-96-exact.json)

### 四 TCK 配对上板

实现约束 133.333 MHz，路由 WNS +2.048 ns、WHS +0.018 ns。Vivado DRC 共 22 项 warning（含报告截断、DDR 时钟使能及 BRAM 异步控制检查），零 error。模型运行结果包含真实 CM3、无等待协议模型和 Xilinx 原语回归。协议模型用于比较特定连续扫描序列的上限，CM3 检查目标 AP 在指定 HCLK 下能否接受该序列。[原语回归](quad-xsim.txt) · [CM3 更多频点](f103-cm3-quad-bound.json) · [CM3 临界档](f103-cm3-quad-148.json) · [同协议开销理想对照](f103-quad-wire-budget.json) · [上板身份](quad-load.json)

HCLK96、TCK 100 MHz/idle19 的原两 TCK 配对，实际三轮各 60 秒交替读写和三轮各 60 秒只读通过，方向吞吐约 6.081 MB/s，同条件 CM3 为 6.168 MB/s。HCLK128 的四 TCK 配对在 125.490 MHz/idle13 和 133.333 MHz/idle17 通过短窗，约 8.219 和 8.192 MB/s。后续 32 tap 密扫曾在 148.837 MHz/tap24/slot35/idle17 通过 1 秒混合 9.129 MB/s。188.235 MHz 的该轮整块只读最长达到 152 KiB 后数据不符，200 MHz 在 32 tap 中 22 个可三次读回 ID，扫描到的块读均失败。短窗与持续验收分别保存。另测 PC 经 XSCT/物理 MEM-AP0 向驻留探针写入全新 1 KiB 图案并返回完整 1 KiB，记录 8 组独立时长；此路径包含 PC 文件传输和 XSCT 往返。[96 MHz 持续验收](f103-96-long100-windows.json.gz) · [128 MHz 粗扫](f103-128-quad-pilot-windows.json.gz) · [128 MHz 密扫含失败](f103-128-quad-dense-windows.json.gz)

### 持续读写与报告保存中断

HCLK128、TCK 125.490196 MHz、tap16、采样时隙34、idle13：三轮各 60 秒交替读写和三轮各 60 秒只读均通过。每次混合窗结束后用 50 MHz 段式路径逐字核对末轮图案。PC 实际发收的新载荷与最终独立 USB 读回也通过。同档 A9 本地读写约 8.22 MB/s，无等待协议模型为 8.399 MB/s，约 97.9%。在完整 CM3 的 48/96/128 MHz 时，是否需要 WAIT 还取决于目标 AP 延迟。[125.490 MHz 长窗](f103-128-quad-long-windows.json.gz) · [恢复](f103-128-quad-long-state.json)

重新加载后，148.837 MHz 和 136.170 MHz 的早期通过点均出现未复现的窗口。再扫 133.333 MHz 时末次完成的临时报告比正式报告多 9 个窗口，均可解析；原先保存异常能阻断 finally 中后续重载。HS3 仍在线，独立补跑临时加载并核对正式配对 85,844 字节，SWD 恢复原 4 KiB、哨兵、AFIO、APB2、RCC、Flash 等待周期、运行态；USB 重新枚举。已为 Windows 原子替换增加限时重试，并把探针和目标恢复放入独立 finally。离线持有 JSON 读句柄 200 ms 后释放，报告替换及读回通过；另有两个异常注入单测分别确认最终保存失败仍调用目标恢复和探针重载。现场原始异常代码尚未确认。[中断窗口](f103-128-quad-inline-windows.json.gz) · [目标恢复](f103-128-quad-inline-state.json) · [重载配对](usb-recovery-load.json)

### HCLK96 及独立核对

HCLK96（DWT 实测 96.031 MHz）、125.490196 MHz TCK/idle21，三轮 60 秒混合的方向速率为读 7.27169、写 7.27154 MB/s。同档 CM3 模型为 7.395/7.395 MB/s，约 98.3%。在 130.612 MHz，一组参数通过首轮 60 秒，第二轮仅 5.7 秒便失败。188.235 MHz 通过单次 1 秒只读，重新确认持续读时失败。保持失败窗口及后续低速 USB 恢复证据。[96 MHz 逐轮](hclk96-quad-confirm.json.gz) · [时钟和 RAM](hclk96-quad-confirm-state.json) · [最终 CM3/96](final-cm3-96.json) · [最终 CM3/128](final-cm3-128.json)

从仓库根目录复测四 TCK 配对，需 J7 和已核对的 CDC48。全程使用一个未被占用的新输出目录。检查探针配对后可用以下夹具命令。HCLK96/128 临时改变 PLL、APB 与等待周期；HCLK48 保持初始时钟。独立恢复入口读取同一目录保存的备份及源状态。

```powershell
$fixture = 'build/jtag200/f103-new'
python -X utf8 toolbox.py project run tools/jtag200_f103_fixture.py -- --hclk 128 --out $fixture --execute --command python -X utf8 tools/jtag200_f103_sweep.py --fixture $fixture --pair prebuilt/jtag-only-f103ze-quad-20261119 --cable-serial 210299008529 --rates 125.490 --quad --host-payload --seconds 60 --execute
```
