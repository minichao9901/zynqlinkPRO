# 增加地线后的复测（2026-10-30）

用户增加两根地线后，重复 PE2–PE7 静态逐脚测试：PE2–PE6 与 FPGA 对应管脚全部匹配，PE7 未串到五路；GPIO 原值已读回恢复。证据：`trace-wiring-extra-ground.json`。

使用与前次相同的 raw16 诊断 bit 和 USB-fix ELF：F103ZE 48 MHz HCLK，经 /4 临时降到 12 MHz，TRACECLK 名义 6 MHz；SWD 1 MHz，GPIO 输出模式 1，恢复 RCC 和 GPIO 后目标继续运行。bit/ELF 的 SHA-256 和完整寄存器见 `raw16-extra-ground/acceptance.json`。

原始采集得到 7,216 字节，USB 序号连续，但报告 FIFO 溢出；相位 1 的参考 TPIU 解析在偏移 44 字节发现结构错误与保留源 ID 127，第一条带溢出标记的 USB 包之前已传出 1,920 条记录。地线加强前对应首个结构错误偏移为 37；窗口起点不同，两次数值不能用于定量比较。

因此这次静态连线通过，但尚不能声称高速链路或 ETM 解码通过。原始数据和 USB 传输保留在同目录；`extra-ground-comparison.json` 汇总条件。下一步用独立 200 MHz 过采样与较大诊断 FIFO 继续核验采样边沿。
