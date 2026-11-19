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

正式配对在推算 TCK 59,999,999 Hz、512 字、深度 32、256 块的三轮中位数为读 **2.4131**、写 **2.3898 MB/s**，另完成 10 秒交替验证。首次块读应答失败后经低速 SWD 恢复，强制 TDO 采样模式 16 重跑通过。两次独立恢复核对 4 KiB、哨兵、RCC、AFIO 可读位、APB2 与运行态。SWJ_CFG 按核对过的 CDC48 源码恢复为 2。[首次 USB](usb-initial.json) · [模式 16](usb-mode16.json)

复测示例，从工作树根目录运行。Vivado 2018.3，`--rtl` 指向本机授权的 CM3DbgAXI 源码目录。

```powershell
python -X utf8 tools/jtag200_cm3_sim.py --rtl <CM3DbgAXI/rtl> --out build/jtag200/cm3-new --point 15 2 29 33 --point 10 2 30 49
python -X utf8 tools/jtag200_f103_fixture.py --out build/jtag200/usb-new --execute --baseline
```
