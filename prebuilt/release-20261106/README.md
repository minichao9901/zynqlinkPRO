# J7 正式交付 · 2026-11-06

F103ZE/J7 限定交付，包含五路 ELD1、原始 SWD `0x1D` 修复、L14/TDO 输入隔离及 WebUSB 网页入口。WebUSB 返回 `https://minichao9901.github.io/zynqlinkPRO/#download`，通知是否显示由浏览器决定。

bit 沿用本日已经验收的相同字节，本轮仅重编 PS ELF，未重新综合 PL。133.333333 MHz 约束下 setup/hold 余量 0.067/0.044 ns，ELD1 默认五路零 tap。构建选项、实际源码输入、文件 SHA-256 和继承验证范围见 [manifest](manifest.json)、[源码绑定](source-binding.json)与[交付报告](../../docs/validation/release-20261106/README.md)。

本轮实板通过 BOS/WinUSB/GET_URL（含短读与非法请求 STALL/恢复）、物理 MEM-AP0 执行段对拍、16 次原始 SWD DPID/奇偶校验、SWD10/JTAG1/10 IDCODE/内存读取，以及24 MHz TRACECLK的100 ms DDR+USB/解码。相同 bit 的 SWD/JTAG60 和 TRACECLK32 MHz 来源于此前限定验证，本轮未重新测速或改目标 PLL。

```powershell
python -X utf8 tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/release-20261106/application.elf prebuilt/release-20261106/probe.bit prebuilt/release-20261106/ps7_init.tcl
python -X utf8 tools/verify_probe_ocm_code.py --elf prebuilt/release-20261106/application.elf --out-dir build/release-identity-new
```

先核对板卡占用与引擎空闲；未配置 PL 时不能读取其 AXI 寄存器。加载仅到 RAM，未写 QSPI。ZL-007 外部 I/O 时序签核、ZL-159 断开后 TCK 高阻及 RTCK 自适应仍未完成；36 MHz 校准候选裕量不足。此交付不扩大 H743/HPM 或 QSPI 冷启动的已验范围。
