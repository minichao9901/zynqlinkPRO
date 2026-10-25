# Zynq PS USB HS CDC 实测

日期：2026-10-25，Asia/Shanghai。板上识别为 Zynq-7020；JTAG 下载器枚举为 Digilent JTAG-HS3，USB ID `0403:6014`。CH340 启动串口是 COM5，测试固件的 CDC 是 COM33。

**后续更新：**本文保留第一轮 legacy 基线结果。最新已通过的缓存方案、MSC 对照和变化数据校验见 [MSC 与 cache 对照分析](/E:/zynqlinkPRO/docs/MSC与Cache对照分析.md)，当前 512 B O3 的 IN/OUT 约 22.46/19.19 MB/s，板上也已切换到新方案。

## 结论

**已用实际硬件确认：512 字节传输慢的一个主要原因是 USB 中断合并，而不是 512 字节包本身无法跑快。**

- 同一 O0 固件，只把 ITC 从 8 改成 0，512 字节传输 IN 从约 **0.512 MB/s** 提高到 **9.45 MB/s**，OUT 从约 **0.512 MB/s** 提高到 **9.49 MB/s**。
- 修正后的测试固件使用 O3，在目前可工作的旧内存布局下，512 字节传输达到 **IN 18.23 / OUT 16.23 MB/s**。
- 4 KiB 提交 + O3 达到 **IN 32.76 / OUT 31.59 MB/s**，说明连续 CDC 流并不需要 128 KiB 提交才能获得较高吞吐。
- 在同一个 512 字节 O3 固件上，如果主机也改成每次只写 512 字节，OUT 约 **8.47 MB/s**；主机读写方式同样影响结果。

这里的 IN 是设备→电脑，OUT 是电脑→设备。全部使用十进制 MB/s；原始 JSON 同时保留 MiB/s。

## 实验在什么目录进行

原始 `E:\Share\github\ZYNQ7020_YuanZi` 未修改。

本轮需要的源码、后期 BSP、原始板级初始化文件和链接 specs 已复制到：

`E:\zynqlinkPRO\reference\legacy_zynq`

共 358 个文件，约 8.8 MB，逐文件清单为 [snapshot_manifest.json](/E:/zynqlinkPRO/reference/legacy_zynq/snapshot_manifest.json)。编译使用这份本地副本，生成文件位于 `build/`，测试结果位于 `results/`。

本轮只下载 RAM 固件，没有烧写 QSPI 或 SD，也没有重新生成或下载 PL bitstream。

## 测试方法与有效范围

每个矩阵配置都独立构建、重新下载：

1. 读取 USB 实际寄存器，确认 `PORTSC1` 速度字段为 High Speed，ITC 与测试值一致。
2. IN、OUT 各运行三次，每次约 2 秒，采用实际字节数与实际时间计算速度，表中为三次中位数。
3. OUT 每次都通过 JTAG 读取不可缓存的固件计数器，核对设备接收字节增量与主机发送字节数**完全相等**。
4. 每组另跑约 0.5 秒的 IN 数据模式校验。检查固定字节 ramp；它能检查内容错误，但不能排除整段 ramp 的重复或丢失。
5. 所有通过的配置，固件提交错误计数均为零。

主矩阵的主机 chunk 为 64 KiB；测试 128 KiB 设备提交时，主机 chunk 也使用 128 KiB，以使 OUT 接收描述符完整结束。设备提交长度和 USB 单包长度不是同一个量：所有组合的 HS bulk MPS 都是 512。

这些是单向连续流测试，**没有测双向并发，也没有测 DAP 请求→响应 RTT**。OUT 速度的计时来自主机，设备计数用于确认接收量，不是设备端计时。并未做 OUT 数据 CRC、长时间稳定性、复位/拔插压力测试。

## 单变量矩阵结果

除表内变量外，使用同一份修正后的测试源码、DSB 提交屏障及 `memory-mode=legacy`。默认在 IN 完成回调里续传，不主动追加 ZLP。

| 设备单次提交长度 | 优化 | ITC | IN 续传 | 每次满包后 ZLP | IN MB/s | OUT MB/s |
|---:|---|---:|---|---|---:|---:|
| 512 B | O0 | 8 | 回调 | 否 | **0.512** | **0.512** |
| 512 B | O0 | 0 | 回调 | 否 | **9.45** | **9.49** |
| 512 B | O0 | 0 | 回调 | 是 | **4.64** | **9.46** |
| 512 B | O0 | 0 | 主循环 | 否 | **7.24** | **9.47** |
| 512 B | O3 | 0 | 回调 | 否 | **18.23** | **16.23** |
| 4 KiB | O0 | 0 | 回调 | 否 | **32.13** | **28.30** |
| 4 KiB | O3 | 0 | 回调 | 否 | **32.76** | **31.59** |
| 128 KiB | O0 | 0 | 回调 | 否 | **32.08** | **36.01** |

[汇总 JSON](/E:/zynqlinkPRO/results/summary.json) 包含中位数、最小/最大值、校验状态、实际寄存器值和 ELF 哈希。[逐次数据](/E:/zynqlinkPRO/results/matrix/512_O3.json) 包含每一次测试的字节数、时间、设备前后计数器。

512 B O3 三次 IN 为 18.219–18.240 MB/s，OUT 为 16.224–16.259 MB/s；短时重复性较好。

单变量可支持的归因：

- **ITC**：O0 的 512 B 两组只改 ITC，约提高 18.5 倍。结果与一次小传输等待约毫秒级完成通知的现象相符。
- **ZLP**：只开启逐次 ZLP，IN 从 9.45 降至 4.64 MB/s；OUT 基本不变。连续流不需要每个 512 字节提交后都结束一笔主机传输；具体上层协议需要何时发送 ZLP，仍应按其接收请求长度决定。
- **续传位置**：回调续传比主循环续传的 IN 高约 30.5%。两种方式都只有一笔应用层传输在途。
- **O3**：在这份修正后的测试固件及旧内存布局下，O3 枚举和数据模式校验均通过，512 B 吞吐进一步提高。没有证明旧工程所有 O3 枚举问题均已修复。

## 主机每次也只读写 512 字节

使用同一个 `512 B / O3 / ITC0 / 回调续传 / 无逐次 ZLP` 固件，再做三次对照：

| 主机读写 chunk | IN MB/s | OUT MB/s |
|---:|---:|---:|
| 64 KiB | 18.23 | 16.23 |
| 512 B | 18.37 | 8.47 |

原始记录：[matrix_host512/512_O3.json](/E:/zynqlinkPRO/results/matrix_host512/512_O3.json)。OUT 设备计数也全部吻合。

这意味着设备每次提交 512 字节可以很快，但主机同步写入许多小块仍会增加成本。Windows CDC 是字节流，主机一次 write 与总线上的一次 USB 请求并不保证一一对应，不能把此表直接当作 WinUSB DAP 的性能。

## 与原始 CDC 示例的对照

直接构建未改动的旧 CDC 源码，链接本地复制的后期 BSP，使用旧链接布局、O0、128 KiB buffer、实际 ITC=8：

- IN 单次 3 秒约 **26.18 MB/s**。
- OUT 主机提交约 **34.91 MB/s**；这份原始固件没有新计数器，因此该数值没有做设备字节数核对。

记录：[原始 IN](/E:/zynqlinkPRO/results/original128k_itc8_in.json)、[原始 OUT](/E:/zynqlinkPRO/results/original128k_itc8_out.json)。它证明旧工程可以在本机恢复工作，但与新矩阵同时存在多个差异，不能用来单独归因某一项优化。

## 本次修改和仍未解决的问题

测试固件增加了参数化提交长度、ITC、可选 ZLP、回调续传、设备计数器和 DMA 提交前 DSB。删除了旧示例固定初始化 128 KiB 的语句，避免缩小 buffer 后越界。主机工具改为原始二进制字节计数，并记录 JSON。

**内存布局仍需要后续处理。**

- 当前通过测试的 `legacy` 布局将代码、USB 数据等放在同一个 1 MiB 区间；驱动将这一整段映射为不可缓存。这影响 CPU 性能。
- 尝试将 USB 数据独立放到另一个按 1 MiB 对齐的不可缓存区、保留其他区域原缓存属性后，固件进入 main，USB 协商到 HS，但停在设备描述符请求阶段。尚未定位原因。
- 因此本轮速度结果只适用于已测通的 `legacy` 配置；不能认为缓存/DMA 问题已彻底解决，也不应直接把失败的独立布局用于 DAP。

此外，仍没有实现多个独立 512 字节请求的 dTD 排队。4 KiB 的连续流测试不能解决 DAP 小命令的立即响应问题，尤其不能通过等待凑满 4 KiB 来加速命令往返。

JTAG 曾发生 FT_Write/FT_Read 短传输。释放 hw_server 并重启对应 FTDI 设备后恢复；128 KiB 组合第一次下载失败，日志已保留，重新下载后完成三轮双向测试。它是下载链路故障，未算作 CDC 测速结果。

## 复现与当前板上状态

当前板上最终保留的是：**512 B / O3 / ITC0 / 回调续传 / 无逐次 ZLP / legacy 布局**。

```powershell
python E:\zynqlinkPRO\tools\build_cdc_bench.py --tx 512 --rx 512 --itc 0 --opt 3
python E:\zynqlinkPRO\tools\run_xsct.py E:\zynqlinkPRO\tools\download_cdc.tcl E:\zynqlinkPRO\build\cdc_bench\tx512_rx512_itc0_zlp0_cb1_O3_memlegacy\cdc_bench.elf
python E:\zynqlinkPRO\tools\run_cdc_matrix.py --cases 512_itc8 512_itc0 512_O3
```

主机测法和全部选项见 [CDC 测试使用说明](/E:/zynqlinkPRO/docs/CDC测试使用说明.md)。重启/断电后应重新下载 RAM 测试固件。

下一步优先做两项：一是将这组收益迁移到 XUsbPs/WinUSB DAP 路径，直接测小命令往返；二是在保留稳定基线的前提下定位独立缓存布局的枚举问题，再引入小槽位的多请求队列。
