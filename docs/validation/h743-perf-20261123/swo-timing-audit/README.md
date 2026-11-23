# SWO 100 两种编码的时序排查

2026-11-23，沿用 H743 与 J7 标准排线。这里分别复核 TAP 替代码源、J7 数字解码时序和 H743 原生 SWO 寄存器访问。 [逐点记录](evidence.json)

## TAP 回送波形

ST DS12110 Rev 11 表 206 对 H743 rev. V 给出 2.7–3.6 V 条件下额定 TCK 最高 37 MHz、TDO 输出有效延时最大 13.5 ns。原 TAP 夹具以 TCK 变化在 PB3 合成回送码流。按提交给 J7 的时隙数组统计，交替数据的四个测试帧只有 4 次相邻 TCK 下降沿相隔 5 ns。两组混合数据分别有 278 次和 234 次。5 ns 是波形规划值。实际 L14 数字样本中，可对拍的交替码为 0/568 差异，混合码至少有 301/568 个码元不符。这个替代码源超出厂商 TAP 时序条件。样本是 J7 数字回采，具体引脚延时和模拟波形失真的位置仍待独立仪器定位。 [ST DS12110 Rev 11 表 206](https://www.st.com/resource/en/datasheet/stm32h743ai.pdf#page=315) · [TAP 逐点和样本](../swo100-evidence.json)

## 接收端时序模型

按 100 档配置 UART 和 Manchester 接收器。Manchester 快速通道在每个帧的起始沿选择采样相位，帧内使用固定半位采样位置。用现有 `selectio_uart_rx`、`selectio_manchester_rx`、`selectio_manchester_fast`，送固定混合数据，以三个初相运行。Manchester 每点 576 B，NRZ 每点 128 B。源为无噪声的数字电平，接收时钟为固定模型。原串行回归和派生时序矩阵均已运行。

| 目标实际位周期 | NRZ | Manchester phase0 | Manchester phase1 |
|---|---:|---:|---:|
| 9.90 ns | 3/3 | 0/3 | 0/3 |
| 9.95 ns | 3/3 | 0/3 | 0/3 |
| 9.98 ns | 3/3 | 3/3 | 2/3 |
| 10.00 ns | 3/3 | 3/3 | 3/3 |
| 10.02 ns | 3/3 | 2/3 | 3/3 |
| 10.05 ns | 3/3 | 0/3 | 0/3 |
| 10.10 ns | 3/3 | 0/3 | 0/3 |

±0.5% 周期偏差在 64 位后累计约 3.2 ns，与 5 ns 半位相比已不可忽略。该结果反映模型中的时序余量。实际 L14 的 TAP 波形失真与这个接收端边界是两条各自成立的证据。Manchester 100 Mbit/s 仍需一条已核对码元时序的外部混合码流。 [模型源码](tb_timing_margin.sv) · [Arm Manchester 时序](https://documentation-service.arm.com/static/622b33ee8804d00769e9db13)

## H743 原生码源与现场恢复

冷上电后由 HS3 重新临时加载融合配对，物理 OCM 80,260 B 核对通过。目标保持 HSI。经 AP2 能读到 `DBGMCU_ID=0x20036450`，打开调试时钟后 SWO 的 PIDR0 为 `0x14`、LSR 为 `0`。第一次读取 `SWO_CODR` 在 `0xe00e3010` 返回 WAIT。没有编程分频器或发送 ITM 载荷。随后调试时钟门回写未能确认。`CPUID` 和 HSI 配置曾在 SWD 上恢复可读，后续只读核对又未完成。J7 端采集、RTT/HSS、DDR 与调试队列均空闲。目标 Flash 和探针 QSPI 无写入。H743 完整现场恢复仍待再次上电后的只读核对。 [实板寄存器和恢复状态](evidence.json)

## 后续冷上电恢复确认

用户再次断电重上电，排线原样。J7 初始为 JTAG 启动且 PL 处于复位，经 HS3 临时加载同一融合配对，物理 OCM 80,260 B 相符。H743 经 SWD 只读核对原 Flash 的 7,740 B 装载段，`g_ticks` 和 `g_loops` 均前进，RCC 回到 HSI 64 MHz，AP2 `DBGMCU_CR=0`，`DEMCR` 和 AHB4 GPIO 时钟门为零。J7 探针回到空闲。恢复核对未访问 SWO 分频寄存器。 [冷上电恢复证据](recovery-readonly.json)
