# MSC 对照、cache 修正与 CDC 后续结果

2026-10-25，Zynq-7020 实机。原始历史目录保持不变，实验使用当前工作区的源码副本。

## 结论

1. 图中 `cherryusb_bsp_xusbps_intr_example_1` 确实来自 **Xilinx XUsbPs MSC 例程**，这份本地工程修改过容量和逻辑扇区大小。目录带 cherryusb 字样，但实际驱动是 XUsbPs。
2. MSC 的接收路径确实由 **16×512 B buffer** 组成；关键是它们预先挂成硬件描述符队列。发送路径则直接提交整个 SCSI READ 请求，并提前排入 CSW；不是每发送 512 B 都回软件等完成。
3. 本机已复现约 33 MB/s。ITC 改为 0 后，MSC 无论使用 512 B 还是 4096 B 逻辑扇区，读取都约 **39.6 MB/s**。
4. 新 CDC 缓存方案保持程序、普通数据、USB payload 和描述符可缓存，并在 DMA 所有权交接时维护 cache；512 B O3 的连续流从上轮 **18.23/16.23** 提高到 **22.46/19.19 MB/s**（IN/OUT）。
5. CherryUSB 基线仍只有一笔应用层在途传输；随后新增的 XUsbPs 官方 MSC 改造 CDC 已验证 16KiB IN / 16KiB OUT 的批量 dTD 提交，可达到约 32.6/40.0 MB/s。详见 [XUsbPs 官方 CDC 移植报告](/E:/zynqlinkPRO/docs/XUsbPs官方CDC移植报告.md)。

## 1. 核实用户指定的工程

原目录：

`E:\Share\github\ZYNQ7020_YuanZi\PS_CherryUSB_Minichao\PS_CherryUSB_Minichao.sdk\cherryusb_bsp_xusbps_intr_example_1\src`

10 个文件已复制到 [reference/xilinx_msc](/E:/zynqlinkPRO/reference/xilinx_msc)，有逐文件 SHA-256 清单。编译链接当前工作区已复制的后期 `usb_bsp`，避免早期 BSP 中的 cache 跟踪钩子。

与 [AMD/Xilinx 官方例程](https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/usbps/examples/xusbps_intr_example.c) 的结构一致：EP1 OUT 设置 16 个接收描述符，各自 512 B；EP1 IN 有 16 个描述符槽位，数据最大包 512 B。容量等本地修改并非官方原始默认配置。

| 数量 | 这份本地工程的实际值 | 含义 |
|---|---:|---|
| USB HS bulk MPS | 512 B | 总线上单个数据包上限 |
| OUT buffer | 512 B × 16 | 8 KiB 的接收池和描述符队列 |
| IN 描述符槽位 | 16 | 可挂接多个 dTD，并不规定每个 dTD 只能描述 512 B |
| 虚拟磁盘容量 | 512 MiB | DDR 中的 VirtFlash 数组 |
| 本地逻辑扇区 | **4096 B** | 本地 header 已修改；注释中仍保留旧 512 B 设置 |
| 本轮另测逻辑扇区 | **512 B** | 保持 USB MPS、OUT buffer 和队列设置不变 |
| 主机大块测试实际最大 SCSI 请求 | **65536 B** | 固件在 READ/WRITE 命令中记录，非由扇区大小推测 |

MSC READ 的源码核心是：

```c
XUsbPs_EpBufferSend(InstancePtr, 1, &VirtFlash[Offset],
                  block_count * VFLASH_BLOCK_SIZE);
XUsbPs_EpBufferSend(InstancePtr, 1, (u8 *)CBW, 13);
```

也就是数据请求和状态请求依次挂入 IN 队列。64 KiB 数据由底层拆成多个 dTD 和 USB 包。官方 [MSC class 源码](https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/usbps/examples/xusbps_class_storage.c) 可以对照这条路径。

因此，你指出的“小 buffer 也能快”的方向是成立的；这里需要区分 **OUT 的多个小 buffer** 和 **IN 的大请求、多描述符连续发送**。

## 2. MSC 实测方法

- 使用刚下载到 RAM 的虚拟磁盘，没有格式化、分区或烧写真实存储。
- 主机以 `FILE_FLAG_NO_BUFFERING` 打开物理磁盘，绕过 Windows 文件缓存。
- 工具只接受确认为 `USB / Xilinx PS USB VirtDisk`、容量符合本次 RAM 固件且不是磁盘 0 的设备，拒绝其他磁盘。
- 测试区域为 RAM 磁盘偏移 64 MiB 起的 32 MiB；主机每次同步 I/O 为 64 KiB。
- 读、写各三轮，表中取中位数。
- 所有组合的写测试之后都完整读回 32 MiB，核对每块独立的偏移标记和全部 payload，均通过。
- 固件统计 SCSI 请求长度；通过 SCTLR 确认 I-cache、D-cache 实际开关，通过 USB 寄存器确认 HS 和 ITC。

## 3. MSC 结果

本表应用源码编译均为 O0，BSP 保持相同。关闭 D-cache 的实验仍然保留 I-cache，且底层 cache 维护调用没有移除。

| 逻辑扇区 | I-cache | D-cache | ITC | READ MB/s | WRITE MB/s |
|---:|---|---|---:|---:|---:|
| 4096 B | 开 | 开 | 8（原设置） | **32.65** | **8.11** |
| 4096 B | 开 | 开 | 0 | **39.59** | **21.91** |
| 4096 B | 开 | 关 | 0 | **39.15** | **21.84** |
| 512 B | 开 | 开 | 0 | **39.57** | **21.90** |

记录位于 [results/msc](/E:/zynqlinkPRO/results/msc)。例：[512 B 扇区结果](/E:/zynqlinkPRO/results/msc/sector512_dcacheon_O0_itc0.json)、[关闭 D-cache 结果](/E:/zynqlinkPRO/results/msc/sector4096_dcacheoff_O0_itc0.json)。原设置那组先测得速度，其缓存/ITC 状态由对应构建方式和下载寄存器读值确认；其 JSON 没有后续矩阵增加的 before/after 字段。

### 能从结果中判断什么

- 约 33 MB/s 已复现；ITC=0 时读取还能更快，说明本机 PS USB HS 路径具备较高带宽。
- 512 B 与 4096 B 逻辑扇区几乎相同，因为主机实际提交的是 64 KiB 请求；不能由扇区大小直接推算 CPU 回调次数。
- 原设置 OUT 只有约 8.1 MB/s，与 8 KiB 接收池以及 ITC=8 的组合相符。队列很有用，但队列深度和通知延迟需要配套。
- **这组 MSC 没有显示明显的 D-cache 单独收益。** 不能推广为 D-cache 不重要：其大块 READ 直接走 DMA，I-cache始终开启，且已有 cache 维护调用仍然执行。其他 CPU 拷贝、解析和更小请求负载可能不同。

## 4. 真正需要借鉴的实现点

### 接收端预挂队列

XUsbPs 预先给 DMA 挂好 16 个 512 B 接收 buffer；软件处理一个时，硬件还有其他 buffer 可接收。ISR 会遍历已完成描述符，调用应用处理、释放，然后重挂端点。

这与目前 CherryUSB CDC 的“一笔完成→回调→构建下一笔→prime”不同。buffer 小不等于硬件队列浅。

### 发送端提前排入可用数据

MSC 不需要等 64 KiB 数据完成才决定发送 CSW。XUsbPs 支持向活动队列追加描述符，使用 ATDTW 等机制检查端点状态，只有需要时才重新 prime。对照 [XUsbPs endpoint 源码](https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/usbps/src/xusbps_endpoint.c)。

DAP 可以借鉴“已有响应就入队”，但仍须为每个响应保留 buffer，直到 DMA 完成后才复用。

### cache 与 DMA 所有权

- CPU 写完 IN 数据后，先 clean/flush，使 DMA 能看到最新内存。
- OUT 交给 DMA 前避免遗留脏行；DMA 完成后 invalidate，再由 CPU 读取。
- 描述符和 QH 也需要相同的交接，而不是只维护 payload。
- buffer、dTD 和 QH 对齐须满足硬件与 cache line 要求；不能让 DMA 所有的行与 CPU 正在修改的数据混用。
- 程序和普通数据应保持可缓存，避免为了省 cache 维护，把整段程序一并映射成非缓存。

## 5. 本轮对 CDC 做的修改

新增 `--memory-mode cached`：

1. 去掉旧 ChipIdea 初始化中针对整个 1 MiB 段的非缓存映射。
2. 保持程序、USB buffer、QH 和 dTD 为正常 write-back cacheable。
3. 在 IN、OUT、QH、dTD 的 DMA 交接处增加明确的 flush/invalidate。
4. 给设备准备 QH 时清理旧的 active/halted 状态，交付前执行 DSB。
5. 仅将测速计数器放到独立非缓存区，便于 JTAG 实时读取。

继承的上游宏/节名仍叫 `.noncacheable`，但**节名不决定缓存属性**。当前已读取实际 MMU 表项：

| 对象 | 表项 | 实际属性 |
|---|---|---|
| main 所在段 | `00115DE6` | Normal write-back cacheable |
| USB payload 所在段 | `00115DE6` | Normal write-back cacheable |
| QH/dTD 所在段 | `00115DE6` | Normal write-back cacheable |
| 测速计数器所在段 | `00211DE2` | Normal non-cacheable |

SCTLR 的 I-cache、D-cache 位均已确认开启。原始读取记录：[mmu_layout.json](/E:/zynqlinkPRO/results/cached_cdc/mmu_layout.json)。

### CDC 吞吐对照

设备单次提交为表中长度；主机 chunk=64 KiB；ITC=0、回调续传、不逐次添加 ZLP。双向各三次，取中位数。所有 OUT 接收计数增量与主机字节数一致，固定模式检查通过。

| 设备提交 | 优化 | 内存/DMA方案 | IN MB/s | OUT MB/s |
|---:|---|---|---:|---:|
| 512 B | O0 | 上轮 legacy | 9.45 | 9.49 |
| 512 B | O0 | 本轮 cached | **21.48** | **17.77** |
| 512 B | O3 | 上轮 legacy | 18.23 | 16.23 |
| 512 B | O3 | 本轮 cached | **22.46** | **19.19** |
| 4 KiB | O3 | 上轮 legacy | 32.76 | 31.59 |
| 4 KiB | O3 | 本轮 cached | **32.66** | **31.61** |

这是整个缓存/描述符维护方案的比较，**不是单独切换 I-cache 或 D-cache 一个位的因果实验**。512 B O3 相比上轮，IN 约增加 23.2%，OUT 约增加 18.3%；O0 下收益更大。大提交时 USB 传输成本占比更高，差异较小。

记录：[cached_cdc/512_O3.json](/E:/zynqlinkPRO/results/cached_cdc/512_O3.json)，其余配置在同目录。

### 变化数据的 cache 一致性检查

另外构建专用校验固件：每个 512 B 帧都有递增序号、长度、序号反码，以及随序号变化的全部 payload。

- IN：校验 **111136 帧，56901632 字节**，从首个接收帧起要求序号连续且内容完全吻合。
- OUT：设备校验 **85376 帧，43712512 字节**，序号连续、内容错误数为零，设备字节数与主机一致。
- 提交错误数为零。

这是单独的正确性实验，不将其速度混入吞吐表。记录：[sequence_check.json](/E:/zynqlinkPRO/results/cached_cdc/sequence_check.json)。

初版主机校验器使用默认较小串口 buffer，并逐字节重新生成预期数据，曾出现跳号。改为 1 MiB 主机 buffer 和预计算 payload 后，**相同固件**完成上述校验；这也说明主机消费能力需要一并控制，不能把校验程序自身跟不上误判为 DMA 错误。

## 6. 未通过的方案与实际边界

- 原先 `isolated` 布局仍未解决，不能直接使用。
- 本轮另试 `hybrid`：描述符独立非缓存、payload 可缓存。它未通过完整收发测试，出现停流/OUT 写超时，已保存失败记录，**没有作为推荐方案**。
- 当前 CherryUSB 可工作的方案是 `cached`，依靠明确的 cache 维护保持 DMA 一致性；不是简单换一个 MMU 属性就能保证正确。
- XUsbPs 版本已完成 MSC 式的多 dTD 队列和批量软件请求；CherryUSB 版本仍保留一笔应用层传输在途的限制。
- 所有速度都是单向连续流，不能当成 DAP 小命令往返、并发双向或长时间稳定性结果。

## 7. 对高性能 DAP 的具体落地顺序

1. 将端点接收改为多个独立命令槽，例如 16×512 B。单个命令完成后立即处理，不等待凑满 4 KiB 或整个队列。
2. 将可用响应追加到硬件 IN 队列，按 DMA 完成回收槽位；保留未完成 buffer 的所有权。
3. 主机同样保持多个请求在途。队列深度、ITC 和每命令通知策略一起测，避免只在连续流中快、实际请求响应却等待攒批。
4. 直接增加 WinUSB 的小命令往返测试，记录每秒命令数和 p50/p95/p99 延迟，再接实际 OpenOCD/pyOCD。

cache 是必要的基础工作；从本轮结果看，**下一个需要解决的结构差别是队列和完成通知开销**。MSC 的测量与源码都提供了明确参照。

## 8. 复现

```powershell
# MSC 源码构建与缓存/扇区对照（只操作新下载的 Xilinx RAM 虚拟盘）
python E:\zynqlinkPRO\tools\build_msc_bench.py --sector 4096 --dcache on --itc 0
python E:\zynqlinkPRO\tools\build_msc_bench.py --sector 4096 --dcache off --itc 0
python E:\zynqlinkPRO\tools\build_msc_bench.py --sector 512 --dcache on --itc 0
python E:\zynqlinkPRO\tools\run_msc_matrix.py

# 可缓存 CDC 对照
python E:\zynqlinkPRO\tools\run_cdc_matrix.py --cases 512_itc0 512_O3 4096_O3 --memory-mode cached --output-dir E:\zynqlinkPRO\results\cached_cdc
```

当前板上已恢复为 **512 B / O3 / ITC0 / cached / 固定 ramp** 的 CDC 性能固件，COM33；仅 RAM 下载。
