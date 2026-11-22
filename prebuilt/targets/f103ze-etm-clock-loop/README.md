# F103ZE SRAM 时钟验收夹具

同一小段 Cortex-M3 SRAM 程序用于测量目标的 DWT 周期并提供受控运行上下文。调试主机配置目标时钟，ELF 本身运行 SRAM 中的交替分支和计数。通过 `tools/selectio_f103_clock_accept.py` 保存和恢复目标 SRAM、RCC 与核心现场。

```powershell
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostdlib -g '-Wl,--build-id=none' -T firmware/target/f103_etm_clock_loop.ld firmware/target/f103_etm_clock_loop.S -o prebuilt/targets/f103ze-etm-clock-loop/fw.elf
```
