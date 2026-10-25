# CDC 第一轮对照测试

本目录是独立恢复的实验工程，旧目录保持不变。当前固件仅使用 PS USB0，不依赖 SWD RTL。下载只进入 RAM，不烧写 QSPI/SD。源码、BSP、板级初始化文件已复制到 `E:\zynqlinkPRO\reference\legacy_zynq`，有逐文件 SHA-256 清单；后续实验使用本地副本。

新一轮 CherryUSB 推荐配置为 `--memory-mode cached --opt 3`，已通过枚举、收发和变化数据校验；XUsbPs 官方 MSC 改造 CDC 的批量 dTD 版本见 [XUsbPs 官方 CDC 移植报告](/E:/zynqlinkPRO/docs/XUsbPs官方CDC移植报告.md)。下面的 legacy 命令用于复现第一轮基线。

## 构建和下载

```powershell
python E:\zynqlinkPRO\tools\build_cdc_bench.py --tx 512 --rx 512 --itc 0
python E:\zynqlinkPRO\tools\run_xsct.py E:\zynqlinkPRO\tools\inspect_targets.tcl
python E:\zynqlinkPRO\tools\run_xsct.py E:\zynqlinkPRO\tools\download_cdc.tcl E:\zynqlinkPRO\build\cdc_bench\tx512_rx512_itc0_zlp0_cb1_O0_memlegacy\cdc_bench.elf
python E:\zynqlinkPRO\tools\cdc_bench.py --list
```

`build_cdc_bench.py` 使用 SDK 2018.3 自带 GCC，以及本工作区复制的早期 CDC 源码和后期板级 BSP。每个构建目录包含源码副本、编译日志、map、ELF 和输入文件 SHA-256。原始早期 BSP 带有 cache 跟踪函数，不适合作为干净测速基线，因此没有直接链接它。

`run_xsct.py` 使用 SDK 自带 Tcl/XSDB 库执行脚本，并将运行所需的 SDK DLL 复制到工作区。它没有修改系统 DLL、注册表或 Xilinx 安装目录；需要本机 Python 的 `pefile` 包。没有运行中的服务器时，会启动一个隐藏的 `hw_server`，PID 和日志在 `build/xilinx_runtime/`。

## 主机测速

将下面的 COM 号替换成新固件实际枚举的端口。本机 CherryUSB 历史固件曾为 COM33，当前 XUsbPs CDC 固件为 COM34；COM5 是板载 CH340 启动串口，不用于 CDC 测速。

```powershell
# IN：设备发给电脑；主机每次读取 64 KiB，设备仍然每次提交 512 字节。
python E:\zynqlinkPRO\tools\cdc_bench.py --port COMxx --direction in --chunk 65536 --seconds 5 --output E:\zynqlinkPRO\results\in512_itc0.json
# 正确性检查单独跑，避免 Python 逐字节验证影响峰值测速。
python E:\zynqlinkPRO\tools\cdc_bench.py --port COMxx --direction in --chunk 4096 --seconds 1 --verify --device-tx 512
# OUT：电脑发给设备。
python E:\zynqlinkPRO\tools\cdc_bench.py --port COMxx --direction out --chunk 512 --seconds 5 --output E:\zynqlinkPRO\results\out512_itc0.json
```

DTR=0：接收丢弃；DTR=1：连续发送。固件 IN 数据是每次传输从零开始的 `00 01 ... FF` 模式。IN 统计主机收到的原始字节；OUT 统计主机提交并 flush 的字节，**需要用设备 `bench_rx_bytes` 的增量核对后才能称为设备有效接收吞吐**。

保留 `bench_rx_bytes`、`bench_tx_bytes`、完成次数和提交错误数等全局符号，可通过 JTAG 检查。计数器是 32 位，长时间测试需处理回绕。OUT 当前只统计收到的长度，尚未逐字节校验主机数据；IN 的重复 ramp 也不能发现整段重复/丢失，后续队列优化必须加入单调序号和 CRC。

## 测试矩阵

| 维度 | 第一轮取值 | 目的 |
|---|---|---|
| 设备提交长度 | 512、4096、16384、131072 | 分离小块开销与大块峰值 |
| ITC | 8、0，必要时 1 | 确认中断合并对完成和重挂的影响 |
| IN 提交位置 | 主循环 `--callback-tx 0`、完成回调 `1` | 测量主循环间隙 |
| ZLP | `--zlp 1/0` | 对照流式连续发送与逐次结束传输的成本 |
| 主机 chunk | 512、4096、65536 | 区分主机系统调用和设备提交粒度 |
| 编译优化 | 先 O0，再 O2/O3 | 优化版本必须重新验证枚举、控制传输和数据正确性 |

一次只改一个变量，至少重复三次，记录中位数。每个固件组合单独下载，核对 `PORTSC1` 的速度字段确实为 High Speed，以及 `USBCMD.ITC` 的实际读值。

自动单变量矩阵：

```powershell
python E:\zynqlinkPRO\tools\run_cdc_matrix.py
# 只重复特定组合：
python E:\zynqlinkPRO\tools\run_cdc_matrix.py --cases 512_itc8 512_itc0 --seconds 2 --repeat 3
python E:\zynqlinkPRO\tools\read_cdc_status.py E:\zynqlinkPRO\build\cdc_bench\tx512_rx512_itc0_zlp0_cb1_O0_memlegacy\cdc_bench.elf
```

矩阵对每个组合重新构建、下载，读取实际 HS/ITC 状态，双向各测三次，并校验 OUT 主机字节数与设备接收计数增量相等。每组另做 IN 模式检查。结果与下载日志保存在 `results/matrix/`。计数器地址从对应 ELF 符号读取，不可对不同固件使用固定地址。

## 当前实现边界

这轮固件实现了可配置长度、ITC、ZLP 和回调续传，并增加 DMA 提交前的 DSB 屏障。它**仍然每个方向只有一笔应用层在途传输**，没有实现多个独立 512 字节请求的 dTD 队列。

默认 `--memory-mode legacy` 保留旧链接布局：USB 数据和程序等落在同一 1 MiB 区间，驱动将其映射为不可缓存。这个布局已经实际枚举并测通，但会影响 CPU 性能。`--memory-mode isolated` 将 USB 区独立按 1 MiB 对齐，保留代码等的原缓存属性；首轮实测在设备描述符阶段失败，暂不作为可工作配置。尚未确定根因，不能把这个失败简单归结为缓存映射错误或 O3 问题。

首轮缩小 buffer 时曾遗漏原示例的 128 KiB 初始化语句，已删除并重新构建。该初始固件作废；后续矩阵使用修正后的源码、DSB 和实际验证通过的内存布局。

原驱动最多使用 8 个 dTD，每个承载最多 16 KiB；128 KiB 是该版本的单次提交上限。大接收描述符可能等待满长度/短包才完成，而且原驱动的跨 dTD 短包收尾处理需要另行修复，不能拿它模拟小 DAP 请求。首轮小包实验优先使用 `--rx 512`。

CDC 是字节流，Windows 串口驱动可能把多次写入合并；主机 `write(512)` 不保证与一笔 USB/DAP 请求一一对应。CDC 吞吐结果之后仍需补 WinUSB bulk 的短响应 RTT、每秒命令数、队列深度 1/2/4/8/16 测试。
