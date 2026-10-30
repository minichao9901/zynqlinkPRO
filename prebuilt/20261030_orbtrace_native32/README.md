# ORBTrace native-32 实验配对（2026-10-30）

本目录为本次源码实际生成的 bit/ELF，**尚未加载实板，不是已上板验收版本**。
原有 `prebuilt/` 根目录已知可用配对保留。trace 线用户已确认暂未接好。
本次 native-32 的 DAP/CDMA 吞吐、USB 枚举/采集、真实 F103ZE ETM 均待硬件验收。

- bit：`prebuilt/20261030_orbtrace_native32/zynqdap_orbtrace.bit`
- ELF：`prebuilt/20261030_orbtrace_native32/zynqdap_orbtrace.elf`
- 加载初始化：本目录 `ps7_init.tcl`，复制自已知基线；ELF 单独初始化 FCLK1 的 200 MHz 参考。
- 源码提交、构建选项、输入/产物 SHA-256：`manifest.json`、`firmware-build.json`、`SHA256SUMS`。
- FCLK 100 MHz 下现有约束 setup +0.568 ns、hold +0.024 ns；ELF 调试时钟限制 50 MHz。
- LUT 19,228 / FF 27,858 / BRAM 10 / DSP 1；资源与时序证据：
  `docs/validation/orbtrace-native32-20261030/`，分析见 `docs/orbtrace-area-native32.md`。
- 板上实际 FCLK/TCK 尚无测量值；不能用此处构建上限代替实际运行记录。

准备好硬件后，在仓库根目录使用该配对进行 JTAG RAM 加载：

```powershell
python tools/run_xsct.py --sdk E:\Xilinx\SDK\2018.3 tools/download_dap_fpga.tcl `
  prebuilt/20261030_orbtrace_native32/zynqdap_orbtrace.elf `
  prebuilt/20261030_orbtrace_native32/zynqdap_orbtrace.bit `
  prebuilt/20261030_orbtrace_native32/ps7_init.tcl
```

J7.16=TRACECLK，J7.15/17/18/19=D0/D1/D2/D3，J7.14=GND；3.3 V 输入，当前约束为
50 MHz DDR。连接和加载后仍须核对时钟、同步、丢失状态、捕获字节和解码指令流。
