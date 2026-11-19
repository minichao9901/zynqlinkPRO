# F103ZE 原始 HCLK 下的 JTAG200 测试

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
