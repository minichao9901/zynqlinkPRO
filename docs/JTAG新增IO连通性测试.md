# JTAG 新增两根线的临时固件测试

只测试用户确认的两根新增连线：Zynq B19 → F103CB PA15（TDI），F103CB PB3（TDO）→ Zynq A20。SWCLK/TMS 和目标 Flash 不参与改写。

F103 运行 `firmware/target/probe_jtag_gpio.c` 的 SRAM 临时程序：关闭 JTAG、保留 SWD，将 PA15 配成输入，将 PB3 配成推挽输出，持续执行 `PB3 = !PA15`。在 SRAM 邮箱中记录输入高低电平次数及上升、下降沿数。设置停止标记后，程序恢复 AFIO、GPIO 和 RCC 配置。

Zynq 运行 `firmware/diagnostics/probe_jtag_gpio_zynq.c` 的临时 PS 程序：轮流驱动 B19 高、低，直接读管脚输入回读 CSR，同时检查 A20 是否返回相反电平。分别覆盖 AXI GPIO 输出、JTAG 手动输出两条复用路径。每条路径在 1000、100、10 µs 稳定等待时间下分别检查 200、2000、20000 次，共 44400 次。等待时间用于 IO 功能检查，不作为 JTAG 时序或最高频率测量。

## 运行

板上须已加载支持 JTAG GPIO 复用的 probe bit。`--probe-bit` 指定该配对 bit，测试结束后恢复它和 `--probe-elf`；目标程序只装入 SRAM。

```powershell
python tools/test_jtag_gpio.py `
  --probe-bit build/fpga_dma_global/system_wrapper_verified.bit `
  --probe-elf build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf `
  --output results/jtag/gpio_continuity.json
```

脚本先保存 F103 全部 20 KiB SRAM、核心寄存器和运行/暂停状态，再装入临时程序；Zynq 临时固件执行完，通过 XSCT 完整恢复 probe 配对以重建 USB。随后停止 F103 临时程序，核对 GPIO 配置恢复，再恢复并逐字节核对 SRAM、逐项核对核心寄存器。备份保存在报告旁的 `.backup.bin`，核心寄存器保存在 JSON 中。

临时固件输出在 `build/jtag_gpio/f103_gpio.elf`、`f103_gpio.bin`、`zynq_gpio.elf`。构建及运行日志也在该目录。JSON 包含固件 SHA-256、各阶段检查数、错误数、管脚回读错误数、F103 统计，以及恢复核对结果。

## 首轮发现的问题

旧 JTAG bit 的首轮反相回环检查 22200 次，错误 11100 次；F103 输入在整个窗口内几乎不翻转。检查综合网表发现 `g_aux[*].u_pin/T` 被接成常量 1，GPIO 保持高阻。Vivado 2018.3 将 generate 块引用的后声明 `jtag_config`、`manual_pins`、`jtag_tdi` 解析成了无驱动的局部隐式信号。修复为在生成块之前声明这些信号，并在 routed 验收脚本中拒绝 GPIO 输出使能被接成常量的网表。

首轮报告保留在 `results/jtag/gpio_continuity_before_io_fix.json`，其 SRAM/核心寄存器已恢复核对成功。修复后的实板结果见 `results/jtag/gpio_continuity.json`。

## 2026-10-27 修复后实测

| Zynq 输出路径 | 稳定等待 | 反相检查次数 | 错误 |
| --- | ---: | ---: | ---: |
| AXI GPIO | 1000 µs | 200 | 0 |
| AXI GPIO | 100 µs | 2000 | 0 |
| AXI GPIO | 10 µs | 20000 | 0 |
| JTAG 手动管脚复用 | 1000 µs | 200 | 0 |
| JTAG 手动管脚复用 | 100 µs | 2000 | 0 |
| JTAG 手动管脚复用 | 10 µs | 20000 | 0 |

总计 **44400 次，0 错误**，B19 管脚自身的高低电平回读也是 0 错误。F103 记录到 22214 次上升沿和 22214 次下降沿（包含测试准备及恢复时的额外变化）。确认 B19→PA15、PB3→A20 的连通性及两条输出复用路径均正常。

`gpio_restore_match`、`ram_restore_match`、`registers_restore_match` 全部为 true。Zynq 已恢复正常 probe 配对，F103 恢复测试前的暂停状态。测试所用 bit 的内部时序在 FCLK 120 MHz 下 setup slack 0.260 ns、hold slack 0.041 ns；本回环测试不代替 JTAG 协议与高速时序验收。
