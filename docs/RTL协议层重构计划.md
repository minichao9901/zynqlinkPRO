# CMSIS-DAP 协议层 RTL 化计划

目标是保留 PS 的 USB HS 控制器和端点收发，把 USB 包之后的常用 CMSIS-DAP
协议处理下沉到 PL，减少 PS DDR/cache、C 语言解析和 AXI-Lite 碎片访问。

## HFLink 可借鉴的分层

HFLink 将 `DAP_SWJ`、`DAP_Seqence`、SWD transfer 状态机、响应长度和 USB 包
缓冲分开。当前工程已经有 SWD core、batch engine、CDMA 和双口 BRAM，下一步
应在它们之间增加 packet engine，而不是把 HFLink 的 Gowin USB/PLL 直接移植。

```text
PS USB OUT buffer (DDR)
        │ CDMA burst
        ▼
DAP command BRAM → packet parser → transfer scheduler → SWD batch/core
                                      │
                                      ▼
PS USB IN buffer (DDR) ← CDMA burst ← response BRAM
```

## 第一阶段：只覆盖高速 SRAM 路径

硬件 packet engine 先实现：

- `DAP_TransferBlock`（0x06），count、request、连续 AP memory read/write；
- AP posted-read 的首个 dummy 和末尾 RDBUFF；
- `DAP_TransferConfigure` 的 idle/retry 配置；
- 响应 count/status/data 的连续写入。

PS 只需提交 DDR 源地址、长度和目标 DDR 响应地址，轮询完成状态，再调用
XUsbPs 发送 IN 包。现有 `0x04/0x05` compact batch 命令保留作为回退路径。

## 第二阶段：常用控制命令

再加入 `DAP_Connect`、`DAP_Disconnect`、`DAP_SWJ_Clock`、`DAP_SWJ_Sequence`、
`DAP_SWD_Configure` 和 `DAP_ResetTarget`。JTAG、SWO、vendor 命令暂时继续由 PS
处理，避免首版协议状态空间过大。

## 读写不对称的测量方法

当前写入每笔在 parity 后即可结束；读取必须执行 target-to-host turnaround，
并把数据经 USB IN 返回。优化前先分别记录：

1. SWD core 一个 block 的时钟数和 turnaround 数；
2. CDMA 上传/下载字节数与耗时；
3. USB OUT/IN 回调到主机完成的时间。

只有第 1 项体现 SWD 协议效率，第 2、3 项才能解释 50 MHz 下读 2.9、写 3.4
MB/s 的差异。HFLink 的连续调度重点应放在读路径预启动、响应 BRAM 连续写和
USB IN 缓冲排队，而不是继续增加单个 512 B 包大小。

## 提交节点

- `b4e7c21`：优化 DAPLink RTL、CDMA、cache 和测试工具基线。
- `cee8ccf`：加入 SWD 线级仿真、时钟实验脚本和 OpenOCD 配置。
- 后续 packet engine、PS 适配和每个可验证频率档位分别提交，保留可回退点。
