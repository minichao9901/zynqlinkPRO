# XUsbPs 官方 MSC 例程移植 CDC 实测

2026-10-25，Zynq-7020 实机，USB HS，Windows CDC 串口 COM34。实验源码位于 [firmware/xusbps_cdc](/E:/zynqlinkPRO/firmware/xusbps_cdc)，它保留 Xilinx `usbps_v2_4` 的 Chapter 9、端点队列和中断驱动，只把设备类描述符和类请求改成 CDC ACM。

## 结论

- 官方 MSC 的关键不是“每个 USB 包大于 512B”，而是**一次向 XUsbPs 提交较大的软件请求，由驱动拆成多个 512B USB 包，并提前挂入 dTD 队列**。
- 直接把 CDC 每次提交限制为 512B，实测 ITC=0、O3、16 深度只有 IN 25.13 MB/s、OUT 21.14 MB/s。
- 将 IN 软件提交长度改为 16KiB，仍保持 bulk MPS=512B，IN 达到 **32.46 MB/s**。
- 将 OUT 接收 dTD 的软件 buffer 改为 16KiB，仍保持 MPS=512B，OUT 达到 **39.98 MB/s**；JTAG 读到的 `bench_rx_bytes` 与主机发送字节完全相等。
- 这已经达到用户所说的官方 MSC 约 33 MB/s 水平。此前 MSC 测得的 39.6 MB/s 是专用大块磁盘读路径，不能直接等同于 CDC 串口路径；CDC 还包含 Windows 串口类驱动开销。

## 为什么 512B 仍然可以达到 33 MB/s

USB HS bulk 端点的 `wMaxPacketSize` 仍是 512。`XUsbPs_EpBufferSend()` 的 `BufferLen` 是软件请求长度，驱动会在一个调用中创建多个 dTD；每个 dTD 最多 16KiB，硬件再按 512B 包发送。

因此采用下面的分层：

| 层 | 本轮设置 | 含义 |
|---|---:|---|
| USB bulk MPS | 512 B | 总线上单个 bulk 包大小，没有改变 |
| IN 软件提交 | 16 KiB | 一次提交 32 个 512B 包，完成回调减少 |
| OUT 接收 buffer | 16 KiB | 一次接收 32 个 512B 包，RX 回调减少 |
| IN/OUT 队列 | 16 | 预挂多个 dTD |
| ITC | 0 | 与 MSC 高速配置相同的对照 |
| 编译优化 | O3 | 与最终性能固件相同 |

这与官方 MSC 的核心路径一致：MSC 的 READ 请求通常是 64KiB，XUsbPs 再拆成多个 dTD 和 512B USB 包。DAPLink 的小命令仍可使用独立的 512B 命令槽；连续数据和响应队列则应采用这种批量 dTD 提交方式。

## 实测矩阵

主机每次读写 64KiB，单向连续 3 秒；速度单位为 MB/s（10^6 字节）。每次下载后确认 `PORTSC1` 为 High Speed，读取固件统计计数。

| 固件 | IN | OUT | 设备 OUT 计数 | 备注 |
|---|---:|---:|---:|---|
| TX=512, RX=512, depth=16, ITC=1 | 25.17 | 20.86 | 62,586,880 B | 官方 XUsbPs CDC 初始版本 |
| TX=512, RX=512, depth=16, ITC=0 | 25.13 | 21.14 | 63,438,848 B | ITC 改变很小 |
| TX=512, RX=512, depth=32, ITC=0 | 25.17 | 21.23 | 63,700,992 B | 单纯增加队列深度收益很小 |
| TX=16KiB, RX=512, depth=16, ITC=0 | **32.34** | — | — | 只验证 IN 聚合 |
| TX=4KiB, RX=4KiB, depth=16, ITC=0 | **32.23** | **38.58** | 115,736,576 B | 4KiB 软件请求对照 |
| TX=16KiB, RX=16KiB, depth=16, ITC=0 | **32.57** | **39.98** | 119,996,416 B | 当前推荐吞吐配置 |

结果文件位于 [results/xusbps_cdc](/E:/zynqlinkPRO/results/xusbps_cdc)。

## 正确性检查

使用 512B 固定帧、递增序号、反码和变化 payload 的专用固件，完成：

- IN 校验 99,264 帧、50,823,168 B，序号连续，内容无误。
- OUT 校验 74,976 帧、38,387,712 B，设备端错误数为零，计数与主机发送量一致。
- `bench_submit_errors=0`，USB 速度字段为 High Speed，D-cache/I-cache 均开启。

记录见 [official_sequence.json](/E:/zynqlinkPRO/results/xusbps_cdc/official_sequence.json)。
DMA 池扩容后的当前源码又重跑了 1 秒校验，记录见 [official_sequence_current.json](/E:/zynqlinkPRO/results/xusbps_cdc/official_sequence_current.json)，同样为 `status=passed`、提交错误和内容错误均为零。
推荐 16KiB IN 固件的 ramp 内容也用独立校验器通过，记录见 [official_16k_in_verify.json](/E:/zynqlinkPRO/results/xusbps_cdc/official_16k_in_verify.json)。

## 当前实现和边界

`CDC_TX_BYTES` 和 `CDC_RX_BYTES` 是**软件 DMA 请求长度**，不是 USB 端点 MPS。第一次使用 16KiB RX 时，DMA 池仍是 128KiB，16 个 OUT buffer 需要 256KiB，因而出现写阻塞；将 `DmaMemory` 扩为 512KiB 后，16KiB RX 稳定通过。后续可测试不同主机 API，或直接转 WinUSB bulk，避免把 CDC 串口驱动开销混入 DAPLink 结论。

DAPLink 协议本身不应把一个命令强行延迟到 4/16KiB 才响应。建议保留多个 512B 命令/响应槽，收到完整命令立即处理；对连续数据或已准备好的响应，再用 4KiB～16KiB 的 dTD 批量排队，DMA 完成后回收 buffer。

## 复现命令

```powershell
# 推荐吞吐固件：USB MPS 仍为 512B，软件 IN=16KiB、OUT=16KiB
python E:\zynqlinkPRO\tools\build_xusbps_cdc.py --tx 16384 --depth 16 --rx-depth 16 --rx-bytes 4096 --itc 0 --opt 3
python E:\zynqlinkPRO\tools\run_xsct.py E:\zynqlinkPRO\tools\download_cdc.tcl E:\zynqlinkPRO\build\xusbps_cdc\tx16384_d16_rx4096x16_itc0_O3\xusbps_cdc.elf
python E:\zynqlinkPRO\tools\cdc_bench.py --port COM34 --direction in --chunk 65536 --seconds 3
python E:\zynqlinkPRO\tools\cdc_bench.py --port COM34 --direction out --chunk 65536 --seconds 3
python E:\zynqlinkPRO\tools\read_cdc_status.py E:\zynqlinkPRO\build\xusbps_cdc\tx16384_d16_rx4096x16_itc0_O3\xusbps_cdc.elf

# 512B 固定软件请求的变化数据正确性检查
python E:\zynqlinkPRO\tools\build_xusbps_cdc.py --tx 512 --depth 16 --rx-depth 16 --rx-bytes 512 --itc 0 --opt 3 --sequence
python E:\zynqlinkPRO\tools\cdc_sequence_check.py E:\zynqlinkPRO\build\xusbps_cdc\tx512_d16_rx512x16_itc0_O3_seq\xusbps_cdc.elf --port COM34 --seconds 2 --output E:\zynqlinkPRO\results\xusbps_cdc\official_sequence.json
```
