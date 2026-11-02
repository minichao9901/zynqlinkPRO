# HPM6800EVK 66.667MHz原生测速配对

PL复用已验收133.333MHz bit；新PS增加显式RISC-V ARM PLL/10最高档、统一DAP/流cap及启动诊断。不是fixed-FCLK SWD固件，不是全平台Golden。

15请求频率×三个SRAM窗口、RTT及1/8变量HSS分档通过；66.667MHz/idle22/mode17 AXI读3.448/写3.401MB/s，三个窗口各30秒；RTT约3.188MB/s；HSS单变量296.296k、8变量56.338k组/s各三轮10秒零跳采窗口。详见[报告](../../docs/validation/hpm6800-speed-completion-20261102/README.md)和[manifest](manifest.json)。

原生源码变体为b5bb054加报告build-inputs四个精确文件；Web阶段的HID兼容修改另交付，不能据当前工作树推断本ELF。controls保存实际使用的IO-only对照及启动失败候选，均引用同一bit，不冒充最终通过配对。
