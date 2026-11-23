# H743 高速 RAM 目标程序和性能进展

2026-11-23，J7 USB `12345678`、HS3 `210299008529`、CDC OUT 防护融合配对。沿用原排线。H743 原 Flash 装载段 7,740 B 仍与原 `dbgstress` ELF 相同，本轮启用独立 RAM 目标程序。CPU480/HCLK240 的三个硬件周期估计约 479.55–480.06 MHz。SWO 100 优先复验另用 CPU400/HCLK200，以便整数码元分频。ETM 未列入本轮。 [RAM 目标程序及构建参数](../../../prebuilt/targets/h743-perf-20261123/manifest.json) · [SWO 100 两模式复验](swo100.md)

第一次尝试从 HSI 切换时，原 LDO 尚未锁存，VOSRDY 未置位，高频 PLL 未执行。核对 SRAM 和核心已恢复后按同板已验证的启动顺序，锁存原 LDO 配置并重新核对就绪。480 档仅临时启用 ODEN，退出时回到原 HSI、SRAM、核心、PLL 和 VOS3。供电方式不变，LDO 锁存位由上电重新初始化。 [阶段完整证据](swo100-evidence.json)

## CPU480/HCLK240 已取证的项目

| 项目 | 已确认值 | 窗口 |
|---|---|---|
| SWD AXI SRAM，50 / 72.727 / 100 MHz | 3.692 / 3.679、5.039 / 5.112、6.508 / 6.722 MB/s 读／写 | 标准 CMSIS-DAP 深度 32、每档 3 轮 |
| JTAG AXI SRAM，50 / 72.727 / 100 MHz | 2.526 / 2.504、3.228 / 3.183、4.282 / 4.216 MB/s 读／写 | 同一标准路径。72.727 MHz 重标 slot26，SWD 重标 slot22 |
| 100 MHz RTT→CDC | SWD PC 4.359 MB/s，JTAG PC 2.156 MB/s | SWD 60 秒，JTAG 3 秒 |
| 100 MHz J-Scope 单／八变量 | SWD 约 1,000,002 / 125,000 组/s，JTAG 约 300,000 / 80,000 组/s | 四个 2 秒窗，零跳拍。SWD 单变量 16 tick 的约 1.5M 组/s 另有 3 秒候选 |
| H743 GPIO SPI→CDC | mode0/2 平均 13.333 MHz，mode1/3 平均 15.118 MHz | 各 3 秒，5,000,001 / 5,669,292 B，源和主机逐字节核对 |
| J7 SPI 主机 MISO | 100 MHz SCK 四模式接收 H743 TIM2 的约 30 / 40 MHz 异步 PWM | 每档每模式 3 秒，逐块核对频率与边沿分布 |
| H743 TIM2+DMA 串行码源 | NRZ 15 Mbaud，Manchester 7.5 Mbit/s，IF0/IF4 | 每组 12,288 B，完整混合载荷，DMA 无错误 |

100 Mbaud 的 CDC 同步 TAP 回送未通过，30/40 Msymbol/s 的 DMA 试探先发生源端 FIFO 错误。调试长窗在用户切换 SWO 优先级后安全退出，后续未启动的项记为跳过。 [逐项实板数据](other-perf-evidence.json)
