# Zynq 高性能 DAP：旧工程梳理与 USB 性能分析

分析日期：2026-10-25。原始目录：`E:\Share\github\ZYNQ7020_YuanZi`。本次未修改原始工程。

## 1. 结论

1. **功能最完整、最适合恢复工作的候选基线是 `ZYNQ_DAPLINK_RTL_100TO50MHz`，其中 `usb_bsp_xusbps_daplink_rtt` 是 DAP+RTT 版本。** 这是源码、工程引用和历史总结共同支持的判断；尚未重新上板确认，不能称为本次已验证的最终发布版本。
2. 这个目录没有 Git 历史，无法恢复严格提交顺序。目录名的 `NEW`、复制时间和 ELF 文件名都不能独立证明哪个更新。尤其 SDK 内混有多个应用、重复配置头、源码副本和旧 ELF。
3. USB 有两条路线：**早期 CherryUSB ChipIdea 驱动**与**后期 Xilinx `XUsbPs` 驱动**。后期 DAP+RTT 采用后一条；USB 优化不能把两套驱动当成同一版本。
4. **USB HS bulk 最大包 512 字节，不等于一次 DAP 命令只能有 512 字节。** 最新配置实际为 `DAP_PACKET_SIZE=4096`、`DAP_PACKET_COUNT=16`；端点 `MaxPacketSize=512`、OUT `BufSize=4096`。
5. “大 buffer 才快”首先应检查**传输完成频率、中断合并、重新挂接间隙、在途请求数、ZLP 和主机读写粒度**。不能仅凭大块 CDC 吞吐推断 DAP 小命令性能。
6. 本次已经恢复独立 CDC 构建与测速工具，源码和 BSP 已复制到当前工作区。JTAG、UART、CDC 现已恢复；新实测结果另见 [CDC 实测报告](/E:/zynqlinkPRO/docs/CDC实测报告.md)，以该报告和对应 JSON 为准。

## 2. 工程关系与差异

下表是结构上的演进关系，不是已证明的 Git 祖先关系。

| 目录 | 源码/工程证据 | 定位与建议 |
|---|---|---|
| `vdma_lcd` | 显示应用源文件，不是完整 DAP 工程 | 历史显示实验 |
| `19_vdma_lcd` | VDMA Vivado 工程，SDK 含 `PS_CherryUSB`、显示应用 | USB/显示早期试验，非 DAP 最终版 |
| `PS_CherryUSB_Minichao` | CDC、CDC speedtest、MSC、UAC、UVC、复合设备等多个应用 | USB 实验集合；`PS_CherryUSB_CDC_speedtest` 适合恢复 CDC 基线 |
| `ZYNQ_DAPLINK` | 工程没有引用自定义 `swd_core/swd_controller`；`SW_DP.c` 为软件 SWD 路径 | 早期软件 SWD 版本；XUsbPs/CDC/DAP 起点 |
| `ZYNQ_DAPLINK_TRANSFER_FUNC_TEST` | `design_1`/`design_2`、AXI VIP、`register_map.md`，没有配套完整 PS SDK 应用 | SWD 控制器寄存器/传输仿真实验 |
| `DAPLINK_TXFER_FUNC_64B_TEST_FAIL` | 64 位 AXI 控制器、AXI VIP；核心与早期 RTL 核心一致 | 失败的总线接口实验，保留作参考 |
| `ZYNQ_DAPLINK_RTL_64B_FAIL` | `C_S_AXI_DATA_WIDTH=64`，PS 有 `swd_write64` 一类接口 | **64B 指 64 位访问，不是 USB 64 字节包**；不要作为默认基线 |
| `ZYNQ_DAPLINK_RTL_NEW/ZYNQ_DAPLINK_RTL` | 32 位 AXI 控制器；SDK 同时保留 XUsbPs DAP、CherryUSB DAP 和 `_opt` | 中间快照；`NEW` 不能说明比所有其他目录更新 |
| `ZYNQ_DAPLINK_RTL` | 32 位 AXI，控制器相对 NEW 有变化；`swd_core` 与 NEW、120MHz、64B 实验逐字节一致 | 早期 RTL 集成主线；SDK 含 `_daplink_2` 等应用 |
| `ZYNQ_DAPLINK_RTL_120MHz` | BD 的 FCLK0 为 120 MHz；`swd_core`/`swd_controller` 与普通 RTL 版哈希一致 | 时钟/参数实验，核心没有换代 |
| `ZYNQ_DAPLINK_RTL_100TO50MHz` | 新线性状态机、`IOBUF+BUFG+IDDR` 采样、256 bit SWJ、`swd_batch_engine`、DAP+RTT 应用 | **最完整候选基线** |
| `zynq_daplink_src_from_lizimu` | 独立 PS/CherryUSB/DAP 源码包，使用 `fpga.h`，没有完整 `.xpr` | 外部参考实现；不能推断成当前项目最终版 |

建议恢复路线：

```text
USB 实验：PS_CherryUSB_Minichao → 独立 CDC 小块/大块对照

DAP 功能：ZYNQ_DAPLINK（软件 SWD）
             → RTL 系列（普通/NEW，准确前后关系不能完全确定）
             → 120MHz 实验
             → 100TO50MHz（新采样结构 + batch + RTT）

旁支：TRANSFER_FUNC_TEST、64 位 AXI 的 FAIL 实验
参考：lizimu 源码包
```

哈希清单保存在 [archive_inventory.json](/E:/zynqlinkPRO/docs/archive_inventory.json)。普通 RTL、NEW、120MHz、两个 64 位实验的 `swd_core.v` SHA-256 前缀均为 `2363b5b8bd8e`；最新核心为 `f6573fbc4d3b`。这比工程名字更能说明哪些是同一个核心的变体。

## 3. 最新候选基线具体做到了什么

入口是 [100TO50MHz 工程](/E:/Share/github/ZYNQ7020_YuanZi/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.xpr)。

- `usb_bsp_xusbps_daplink_2`：较简单的 DAP+CDC 集成版本。
- `usb_bsp_xusbps_daplink_rtt`：增加 RTT、SWD 内存访问封装、CDC 环形缓冲、调试优先调度。恢复完整功能优先看它。
- `swd_controller.v`：32 位 AXI-Lite；`IOBUF + BUFG + IDDR`；实例化 batch engine。
- `swd_core.v`：线性状态机，SWJ 输入扩到 256 bit，替代此前 MMCM 多相采样路线。
- `swd_batch_engine.v`：命令/响应存储、MEM-AP 批量读写和 WAIT 重试；仍是 AXI-Lite 窗口访问，尚未做 AXI Full/CDMA 通路。
- `DAP.c`：block transfer 有 batch 加速，普通 transfer 保留传统路径。

历史 [project_summray.md](/E:/Share/github/ZYNQ7020_YuanZi/ZYNQ_DAPLINK_RTL_100TO50MHz/project_summray.md) 记录：50 MHz SWD 稳定读 IDCODE；OpenOCD 读约 1.36–1.40 MiB/s、写约 2.09–2.10 MiB/s；RTT 单独约 840–850 kB/s，与调试并行约 420 kB/s；该桥接路径纯 CDC 约 4.1 MB/s。**以上全部是旧记录，本次未复测。**

时钟方面要结合运行时看：BD 仍保存 120 MHz，但最新 `DAP_config.h` 的 `PORT_SWD_SETUP()` 会调用 `ps_set_fclk0_hz(100000000U)`。因此目录的“100→50”不能简单解读成 BD 一直输出 100 MHz。根目录 AGENTS 中关于旧 MMCM/100 MHz 约束的部分也已落后于当前源码，以实际 RTL、XDC 和运行时设置为依据。

不要混用不同版本的 PS ELF、PL bitstream、DAP 配置头和初始化文件。特别是软件寄存器布局由早期 128 bit SWJ 扩到 256 bit SWJ，并新增 batch 寄存器。

## 4. 512 字节：需要分清四个量

| 名称 | 当前含义 | 是否必须相等 |
|---|---|---|
| USB `wMaxPacketSize` | HS bulk 单个 USB 数据包上限，当前为 512 | 无需等于整次传输 |
| USB 传输/提交长度 | 一笔 DMA/主机请求可包含多个 USB 包，例如 4096/131072 | 可以大于 512 |
| `DAP_PACKET_SIZE` | DAP 命令和响应支持的最大长度，通过 DAP_Info 向主机报告 | 本地已有 512 和 4096 两种配置 |
| `DAP_PACKET_COUNT` / 在途深度 | 软件槽位、硬件描述符和主机实际排队深度各有一层 | 声明槽数不代表硬件始终有同样多请求在途 |

Arm 的 [DAP 配置文档](https://arm-software.github.io/CMSIS_5/5.9.0/DAP/html/group__DAP__Config__Debug__gr.html) 将 512 列为 HS WinUSB 的典型配置；[DAP_Info](https://arm-software.github.io/CMSIS-DAP/latest/group__DAP__Info.html) 定义了查询最大 Packet Count 和 Packet Size 的接口。实际主机兼容性仍要验证，不能认为把最大长度改大就一定能让所有调试工具使用它。

本地最新配置证据：

- [DAP_config.h](/E:/Share/github/ZYNQ7020_YuanZi/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp_xusbps_daplink_rtt/src/DAP/Include/DAP_config.h)：4096 字节、16 槽。
- [XUsbPs 端点配置](/E:/Share/github/ZYNQ7020_YuanZi/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp_xusbps_daplink_2/src/xusbps_intr_example.c:259)：DAP/CDC 都是 MPS=512，OUT BufSize=4096、NumBufs=16。
- 根目录旧测试日志还出现了 `o:262/i:1019` 和 `o:5/i:3084`，也说明历史 DAP 响应并非固定 512 字节。

若改为 512 字节 DAP，必须一起检查 DAP_Info、主机提交方式、接收描述符长度、队列和短包结束。只把 C 数组缩小或只改 `MaxPacketSize` 会引入另一组问题。

## 5. USB 性能问题：已确认的代码事实和待验证假设

### 5.1 最高优先级：ITC 中断合并

早期 [usb_dc_chipidea.c](/E:/Share/github/ZYNQ7020_YuanZi/PS_CherryUSB_Minichao/PS_CherryUSB_Minichao.sdk/PS_CherryUSB_CDC_speedtest/src/CherryUSB/usb_dc_chipidea.c:198) 有“不使用中断阈值”的注释，但真正清除 ITC 的语句被注释掉。后期 DAP 应用也没有找到显式调用设置中断阈值的代码。

Xilinx 的 [usbps 文档](https://xilinx.github.io/embeddedsw.github.io/usbps/doc/html/api/group__usbps.html) 说明默认 8 个 microframe 对应 1 ms，限制中断发出频率。**是否真是当前板上的设置，必须读 USBCMD 确认。**

若只有一笔传输在途，而且软件依赖完成中断才能重挂，小传输每次都支付明显的等待开销；大传输则把同样的开销摊给更多数据。举例，每 1 ms 才补一笔 512 字节约为 0.512 MB/s，补 4096 字节约为 4.096 MB/s。这只是解释机制的算例，不是对真实控制器吞吐的严格上限，也不能用它倒推旧 4.1 MB/s 结果的根因。

先测 ITC=8/0/1 的单变量对照，再结合 ISR 次数、完成时间和重挂时间判断。

### 5.2 一笔应用层传输在途，完成后再提交

早期 `cdc_acm_template.c` 的主循环：提交 128 KiB → 等待 busy 清除 → 再提交。IN 回调在长度为 MPS 整数倍时先提交 ZLP，直到 ZLP 完成才清 busy。

这意味着改成 512 字节时，不只是数据短了，而是**提交/完成/可选 ZLP/主循环重挂的次数大幅增加**。驱动能把一笔大传输拆成多个 dTD，并不等于它支持多个独立的小请求持续排队。

目标应是：多个 512 字节槽位先挂到硬件队列，ISR 批量回收完成描述符，业务层有数据就填槽；同时主机保持多个请求在途。512×16=8 KiB 就可以形成队列，未必需要每笔请求 128 KiB。能否达到预期要看该驱动的实际队列实现。

### 5.3 大 OUT buffer 可能增加小命令等待

AMD 的 [bulk 端点模型](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Interrupt-and-Bulk-Endpoint-Operational-Model) 描述了 dTD 与 USB 变长传输/短包结束机制。

如果软件预挂一个 128 KiB 接收，而主机仅发送一个完整 512 字节数据包后等响应，设备不能假设这个包天然就是整笔传输的结尾。需要长度约定或短包/ZLP，否则完成回调可能继续等。CherryUSB 原实现跨多个 dTD 的短包收尾还需要专门检查：ISR 遍历后续 active dTD 会抑制整体完成回调。

因此大 buffer 接收测速可以很好看，却不适合直接替代 DAP 命令边界。最新 DAP 的 4096 字节接收设置也必须与它报告的 DAP 长度及主机行为保持一致。

### 5.4 Cache/MMU 和 O3 枚举失败

已确认：

- 早期 main 注释记录 O0 可枚举、O3 不可枚举，并记录 128 KiB 时 OUT=30.229240、IN=23.483924 “MB/s”。这是旧脚本的输出单位，不能当成本次有效吞吐。
- `.noncacheable` 是链接节名，本身不会自动改变缓存属性。原驱动通过 `Xil_MemMap` 修改 MMU，粒度是 1 MiB；原链接脚本只做 32 字节对齐，可能把同一 MiB 内其他数据甚至代码一起变成不可缓存。
- 原 CherryUSB 路径关闭了 CONFIG_USB_DCACHE_ENABLE，依赖不可缓存区域；另一批 `_opt` 副本开启此选项，两者并非相同缓存策略。
- 早期 `cherryusb_bsp` 的 `xil_cache.c` 和 libxil 带 `do_trace/do_trace2` 钩子，不能把它视为未修改的官方 BSP。

O3 的具体故障点尚未定位。需要检查描述符交付前后的内存顺序、cache 属性、ISR/主循环共享状态、控制传输缓冲生命周期和初始化顺序。`volatile` 或降低优化等级不能代替 DMA 一致性方案。官方 [XUsbPs 描述符接口](https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/usbps/src/xusbps_endpoint.h) 也明确要求调用方管理描述符的 cache 一致性。

### 5.5 现有主机测速脚本不足以评价小包

原 `test_cdc_speed.py`：

- 固定 COM 号，传输量很小，未分离启动和稳态阶段。
- `'0xAA' * 4096` 是 16384 字节 ASCII 文本，并非 4096 个 0xAA。
- IN 先 decode 并忽略错误，再按字符数计数；不适合通用二进制吞吐。
- 用整数除法计算 MiB，却标 MB/s。
- 没有数据序号/CRC、设备接收确认、延迟分位数、队列深度对照。

新主机工具使用原始字节、`perf_counter()`、实际字节数、超时和 JSON 结果，并区分 MB/s 与 MiB/s。

### 5.6 后期 RTT 桥的 2048 字节门槛

[xusbps_class_cdc.c](/E:/Share/github/ZYNQ7020_YuanZi/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp_xusbps_daplink_rtt/src/xusbps_class_cdc.c:337) 在 used<2048 时直接返回，没有尾包定时 flush；还会调整某些发送长度，试图避开 512 的整数倍。少量日志最后一段可能一直积压。这种攒批策略不能直接用于要求立即响应的 DAP。

## 6. 后续应怎样优化

| 阶段 | 工作 | 判据 |
|---|---|---|
| A：恢复正确基线 | HS 枚举、binary pattern、控制请求、配置/复位稳定性 | 可重复、无数据错误，记录寄存器和版本 |
| B：固定开销 | ITC、ZLP、回调续传、主机 chunk 单变量对照 | 512 字节吞吐提升有可解释证据 |
| C：小传输排队 | 512 字节描述符环，深度 1/2/4/8/16，批量回收、buffer 所有权 | 在小槽位下维持总线忙碌，序号/CRC 无错 |
| D：迁移 DAP | WinUSB OUT→最小响应、不同请求/响应长度、DAP_Info 协商 | commands/s、RTT p50/p95/p99、实际 OpenOCD/pyOCD 读写 |
| E：SWD 系统优化 | 再分析 batch/AXI/RTT 开销 | 只在 USB 已不构成瓶颈后推进 |

CDC 连续流看的是带宽；DAP 更关心命令往返、短响应、主机排队和执行串行依赖。两者都要测。串口驱动可能合并写入，因此 `serial.write(512)` 不能保证每次都成为一个独立 USB 请求。

另外，迁移 DAP 前应检查原 `dap_main.c`：输入长度/队列满检查、响应缓冲在 DMA 完成前是否可能被重用、发送失败时是否仍推进计数。当前源码存在未检查发送返回值、队列满路径部分注释等线索；这些是需要验证和修复的正确性风险，尚未在本次证明已发生数据破坏。

## 7. 本次交付与验证边界

- [CDC 使用说明](/E:/zynqlinkPRO/docs/CDC测试使用说明.md)
- [构建脚本](/E:/zynqlinkPRO/tools/build_cdc_bench.py)
- [主机测速](/E:/zynqlinkPRO/tools/cdc_bench.py)
- [XSDB 运行器](/E:/zynqlinkPRO/tools/run_xsct.py)
- [RAM 下载脚本](/E:/zynqlinkPRO/tools/download_cdc.tcl)
- 三个已编译 ELF 在 `E:\zynqlinkPRO\build\cdc_bench\`，每个目录有编译日志、map 与输入哈希。

已完成源码/工程结构核对、Cortex-A9 固件构建、本地 hw_server/XSDB 恢复与实际 CDC 枚举。早先“目标为空”的阻塞已解除。上板数据校验和单变量吞吐对照见 [CDC 实测报告](/E:/zynqlinkPRO/docs/CDC实测报告.md)。**尚未完成 dTD 队列化；缓存布局和优化编译的支持范围以新实测结果为准。**
