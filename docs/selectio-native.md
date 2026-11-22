# J7 原生 USB 接口

## 主机接口分配

用 USB 序列号 `12345678` 读取配置描述符。2026-11-20 的正式配对返回四个接口。融合候选增加 MI_04、bcdDevice 2.01 和独立 WinUSB GUID。

| 接口 | 端点 | 功能 |
|---|---|---|
| 0，CMSIS-DAP，WinUSB | 02 OUT、81 IN；87 IN；82 IN | 标准命令/响应，历史 HSS 流，ETM 下载 |
| 1+2，CDC ACM | 85 通知、04 OUT、83 IN | 标准串口。原 RTT UP 转发可显式选用这个口 |
| 3，HID | 06 OUT、86 IN | 已有探针控制和状态 |
| 4，厂商自定义，WinUSB | 01 OUT、84 IN | 原生 CLI 命令、数据、容量和错误。RTT 上行和 HSS 采样各有独立通道编号 |

同一号码的 IN 和 OUT 使用不同方向的硬件队列。所有数据 Bulk 端点的高速最大包为 512 B。IF4 与 IF0 分别使用 MS OS 2.0 功能子集。CMSIS-DAP 的 SWO_UART、SWO_MANCHESTER 和 SWO_STREAM 能力位在历史版本均为 0；旧 HSS 数据使用自己的采样帧格式。融合固件在 PL 具有 AUX 时通过 IF0 声明 UART/Manchester，SWO_STREAM 保持 0。标准主机可通过 SWO_Transport=1 在 IF0 取数；原生 CLI 可选 IF4。

IF4 使用有序帧协议。流读取与队列提交停等确认，高速 SRAM 和回环支持多个请求在途。16 字节小端头依次为 `ZLK1`、通道、操作、状态、保留字节、32 位序号、32 位载荷长度。最大载荷 4,079 B。帧恰好为最大包的整数倍时，额外传一个零字节。HELLO 开始新会话。控制通道操作 5 的 CAP1 记录返回 PS 协议版本、可提交深度、块协议头长度、串行缓冲容量和当前 FCLK0。旧 PS 回复“不支持”时，CLI 退回旧块头与单请求，避免由 PL 特性字猜测固件接口。其后的命令检查序号；重复请求被拒绝。RTT 与采样数据在 IN 完成后释放相应队列槽。物理引脚使用权、内存事务耗时与 USB 端点使用权分别管理。

## 已验证的 USB 边界

双频效率候选的 HELLO 报告可协商的最大帧，并将当前会话设为 4,096 B。控制通道操作 8 的请求与成功回复均为一个小端 u32，可显式选择 4,096 或 16,384 B。16 KiB 档最大协议载荷为 16,367 B，16 B DMA 块头及缓存行对齐后每请求可传 16,320 B SRAM。SDK 的单 dTD 容量是 16 KiB。通道 7 操作 6 将同一块请求映射到探针私有 DDR，供分方向计时。内存通道操作 5 在一次或多次传输后、关闭会话前读取四个小端 u32，依次为 PS 参考时钟 Hz、端口、该队列的 timing 和 tap 寄存器。SWD timing 的低 2 位为速率码，JTAG 低 3 位为分频值。原 4 KiB 实板成绩列在下文。

Windows 自动为 MI_04 加载 WinUSB。其 DeviceInterfaceGUID 为 `{9DC2A831-F0DC-4F2E-9739-4E94B89DC8BB}`。主线 PL 加上新 PS 固件的接口试验中，IF4 对 0 至 4,079 B 的边界载荷逐字节回环成功。三轮各 60 秒，新载荷停等回环双向合计 18.26、18.20、18.36 MB/s，并在 IF0 插入 2,098、2,092、2,109 次 CMSIS-DAP 能力查询。重复帧号均被拒绝。这个测试包含 PC 生成图案与回环校验，未访问目标 SRAM。[真实描述符及吞吐](validation/selectio-integration/native-usb.json)

主线 PL 与后续启用原生流路由的 PS 配对，在 SWD 实际约 50 MHz 的 F103ZE 上，从 IF4 采集 Flash 首字 1 秒，收到 52,224 B，状态报告生成 10,002 组、跳拍 0。此处验证原生传输通路；100 MHz 融合 PHY 的验证见集成报告。

## 命令

性能验证固件的通道 7 操作 7 测量探针端 CDMA 与 SWD 载荷 BRAM 的短突发。请求为三个小端 u32，依次为字节数（4–1024 且按字对齐）、重复次数（1–256）、时钟选项（0 使用当前 FCLK0，1 临时选择约 133.333 MHz 并恢复）。回复依次为七个小端 u64（定时器 Hz、上传总／最小／最大 tick、下载总／最小／最大 tick），再接三个 u32（FCLK0 Hz、SelectIO 参考 Hz、队列签名）。测量期间独占 CDMA，忙时返回状态 2。CLI 为 `python -X utf8 tools/selectio_dma_latency.py --out build/dma-latency`。

在融合工作树运行。info 与 usb-test 只使用 MI_04。后者校验每个响应。

```powershell
python -X utf8 toolbox.py selectio --serial 12345678 info
python -X utf8 toolbox.py selectio --serial 12345678 usb-test --seconds 60
python -X utf8 toolbox.py selectio read --help
python -X utf8 toolbox.py selectio write --help
python -X utf8 toolbox.py selectio rtt --help
python -X utf8 toolbox.py selectio scope --help
```

RTT 传入目标固件实际控制块或可扫描地址，HSS 传入 `地址:字节宽度:类型`，周期单位为 24 MHz tick。RTT 输出保留原始字节，Scope 输出保留 512 字节 HSS 帧。两者均经过原生接口；兼容路由的命令与采样率见仓库主线 CLI 文档。
