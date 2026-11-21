# J7 双频 SelectIO 候选配对

本目录配对用于 50 / 100 MHz SWD、JTAG、RTT、变量采样、可协商 16 KiB USB 帧与双沿 ETM 验证。它已通过布线时序和数字功能测试，实板资格待验。此前已验收的 100 MHz 配对位于 [selectio-j7-fusion](../selectio-j7-fusion/manifest.json)。

| 文件 | 用途 |
|---|---|
| `probe.bit` | XC7Z020 PL，四线 ETM 与 TRACECLK 各有一只输入 IDDR |
| `application.elf` | Zynq Cortex-A9 USB 探针固件 |
| `ps7_init.tcl` | 本次 Vivado 工程导出的 PS 初始化 |
| `manifest.json` | 配对哈希、RTL 源版本、时序、功能字、实板起测参数 |
| `ps-build.json` | SDK/BSP、固件源文件及链接脚本哈希 |

布线时序为 FCLK0 133.333333 MHz，setup +0.025 ns、hold +0.042 ns。通用时序报告中的 `SWCLK_max_Hz` 按传统 FCLK0 分频生成；高速 SelectIO 使用独立约 200 MHz 参考，队列按 2 或 4 分频。板测日志中的 `wire_hz` 由实际参考钟与队列寄存器折算。[布线核对](../../docs/validation/efficiency-20261122/routed-checks.txt)

从本工作树根目录看输入配对与加载计划。

```powershell
$pair = 'prebuilt/selectio-efficiency'
python -X utf8 toolbox.py probe-load --bit "$pair/probe.bit" --zynq-elf "$pair/application.elf" --ps-init "$pair/ps7_init.tcl" --dry-run
```

按实板验收入口临时加载、复核 OCM、测速和恢复目标。下例打印 50 MHz 的小范围计划。添加 `--execute` 开始实际运行，改为 `--clock 100000000` 可复测 100 MHz。50 MHz 的 tap、slot 和 idle 是初始候选参数。运行后用 SRAM 报告的时钟寄存器、RTT 的实收字节及采样跳拍核对结果。

```powershell
python -X utf8 toolbox.py project run board.accept -- --selectio --board f103ze --pair $pair --clock 50000000 --frame 16384 --only memory --only rtt --only scope --only usb-ddr
```

协议、独立命令、仿真工况及原始计数见[多协议 CLI](../../docs/selectio/README.md)和[效率验证](../../docs/validation/efficiency-20261122/README.md)。
