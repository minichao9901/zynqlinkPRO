# 复合 USB 基准

为了把 DAPLink 协议问题与 USB 传输问题分开，新增 [firmware/xusbps_composite_bench](/E:/zynqlinkPRO/firmware/xusbps_composite_bench)。它保留旧 DAPLink 的复合设备描述符：接口 0 是 vendor bulk（WinUSB/CMSIS-DAP），接口 1/2 是 CDC ACM；暂时不运行 DAP 命令处理，只对两个 bulk 通道连续收发。

端点 MPS 都是 512B，设备软件 dTD buffer 为 4096B、队列深度 16。

## 连续流基线（主机 chunk=64KiB）

| 通道 | IN | OUT | 主机方法 |
|---|---:|---:|---|
| CDC COM33 | 33.29 MB/s | 33.94 MB/s | pySerial，host chunk=64KiB |
| WinUSB bulk EP1/EP2 | **40.24 MB/s** | **37.52 MB/s** | libusb，host chunk=64KiB |

WinUSB 主机 chunk=4KiB 时只有约 24.19/22.11 MB/s；增大主机提交粒度后达到上表速度。但 64KiB 整块只是测速工具的写法，OpenOCD 不会这样发命令。

## OpenOCD 的主机传输粒度

主机 chunk 不是 OpenOCD 自己选的，而是探针在 `DAP_Info` 里上报的 `Packet Size`：

| 传输类型 | DAP_Info Packet Size | 说明 |
|---|---:|---|
| CMSIS-DAP v1（HID） | 64 B | 固定 |
| CMSIS-DAP v2（bulk） | 512 B | DAPLink 标准值 |
| 本工程 `xusbps_daplink` | **4096 B** | `DAP_config.h`，Packet Count 16 |

测速时本机 OpenOCD 为 0.11.0+dev-02365（2023-09-18），行为与 v0.12 源码一致：读到 `INFO_ID_PKT_SZ` 后按该值分配缓冲，把一条 `DAP_Transfer` 打包到不超过它，`N = (pkt_sz - 4) / 5` 个寄存器传输；读命令 `3 + N` 字节，响应 `3 + 4N` 字节。v0.12 的 bulk 后端是同步 `libusb_bulk_transfer`，一次只有一笔在途；它也还没使用 `DAP_TransferBlock`（0x06），master 才加入块传输和异步提交（最多 `min(PacketCount, 4)` 笔在途）。2026-10-25 已升级到带异步后端的 nightly，见 [OpenOCD 环境](OpenOCD环境.md)；本节数据仍可用来对照旧版同步后端。

因此实际 USB 事务大小是：

| Packet Size | 读命令 | 读响应 | 每包传输数 |
|---:|---:|---:|---:|
| 512 B | 104 B | 407 B | 101 |
| 4096 B | 821 B | 3275 B | 818 |

## 512B 粒度实测（2026-10-25，Windows，单笔在途）

| 项目 | 512 B 包 | 4096 B 包 | 64 KiB 整块 |
|---|---:|---:|---:|
| 单向 bulk IN | 5.34 MB/s | 22.69 MB/s | 40.24 MB/s |
| 单向 bulk OUT | 5.04 MB/s | 20.88 MB/s | 37.52 MB/s |
| OpenOCD 式一问一答读 | **2.47 MB/s** | **10.15 MB/s** | — |

512B 时每笔约 96µs 固定往返开销，数据本身在 480Mbps 下只占 8.5µs，速度基本被 Windows/libusb 的同步传输延迟吃掉。这也解释了旧工程 OpenOCD 读只有 1.36–1.40 MiB/s 的量级：512B 标准粒度下 USB 侧上限本来就只有约 2.5 MB/s 有效载荷。

参考：若主机能把 4 笔同时在途（OpenOCD master 的异步后端），512B 单向可到约 9.2/8.7 MB/s，4096B 可到约 32 MB/s。

结论：本工程把 `DAP_PACKET_SIZE` 保持在 4096 是对的；退回 DAPLink 标准的 512B 会把 OpenOCD 下的 USB 上限压到约 2.5 MB/s。

结果位于 [results/composite_bench](/E:/zynqlinkPRO/results/composite_bench)。构建脚本为 [tools/build_xusbps_composite_bench.py](/E:/zynqlinkPRO/tools/build_xusbps_composite_bench.py)，测速工具为 [tools/composite_bulk_bench.py](/E:/zynqlinkPRO/tools/composite_bulk_bench.py)（单笔）、[tools/composite_bulk_pipeline_bench.py](/E:/zynqlinkPRO/tools/composite_bulk_pipeline_bench.py)（多笔在途）、[tools/composite_bulk_rtt_bench.py](/E:/zynqlinkPRO/tools/composite_bulk_rtt_bench.py)（一问一答）。
