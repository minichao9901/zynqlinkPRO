# J7 原生 USB 接口

## 主机接口分配

融合分支的独立端点版使用同一个 USB 2.0 高速复合设备，`bcdDevice=0x0202`，原生 ABI 为 2。IF1/IF2 通过 IAD 组成一个 CDC ACM 功能。EP0 为标准控制通道。

| 接口 | OUT | IN | 用途 |
|---|---|---|---|
| IF0，CMSIS-DAP v2 | `0x01` | `0x81` | 标准调试命令和响应 |
| IF0，CMSIS-DAP v2 的第三个端点描述符 | — | `0x82` | 标准 `SWO_Transport=2` 原始码流，支持 UART/NRZ 和 Manchester |
| IF1，CDC ACM 控制 | — | `0x83` Interrupt | COM 通知 |
| IF2，CDC ACM 数据 | `0x04` | `0x84` | 物理 UART |
| IF3，WinUSB `ff/53/02` | `0x05` | `0x85` | 原生控制、状态、START、STOP |
| IF3 | `0x06` | `0x86` | 高速 SRAM 与探针私有 DDR 测试 |
| IF3 | `0x07` | `0x87` | 原生 RTT 数据、DOWN 和终端事务 |
| IF3 | — | `0x88` | J-Scope/HSS，取流请求走 `0x05` |
| IF3 | — | `0x89` | ETM 采集后 DDR 下载数据 |
| IF3 | `0x0A` | `0x8A` | 四线 SPI；配置、全双工载荷和状态 |
| 预留 | `0x0B` | `0x8B` | EP11 |

Bulk 的高速最大包为 512 B，CDC 通知为 64 B。IF0、IF3 分别声明 MS OS 2.0 WinUSB 功能子集。新 Web 通过 WebUSB 使用 IF3，标准调试或 SWO 可另外声明 IF0。物理 COM 由系统串口驱动管理，网页通过 Web Serial 使用。状态设置由原生控制端点处理。端点 DMA 描述符、帧缓冲和数据队列位于 PS DDR。

## 原生 ABI 2

- 原生 Bulk 使用 16 B 小端 `ZLK1` 帧头。字段为 magic、通道、操作、状态、保留、32 位序号和 32 位载荷长度。整 512 B 的帧附加一个零填充字节。帧上限从 4 KiB 协商到 16 KiB，实际载荷上限应扣除头及填充；SRAM 可流水提交最多四个请求。
- `HELLO` 回 `SIO2`，并以请求序号加一初始化每条 OUT 的序号。一次会话由一个主机管理。CAP 操作返回 `CAP2`、ABI、块协议头大小、队列深度和参考频率。每条 IN 独立持有已提交帧直到 USB 完成。
- 通道 0 为控制。通道 1 的大块读写及通道 7 的私有 DDR 压测走 EP6；内存会话建立、结束和计数走 EP5。通道 2 的 RTT UP 拉取走 EP7，通道 8 的终端 SRAM 事务也走 EP7。通道 3 的 HSS 拉取在 EP5 提交、从 EP8 返回。通道 4 走 EP10。通道 6 的并发 RTT/HSS 各走 EP7、EP8，其控制响应走 EP5。通道 9 的 ETM 控制可走 EP5，ETM 数据从 EP9 下载。
- RTT 和 HSS 使用独立的拉取请求及 IN 完成计数，同一流每次保留一个取流请求在途。并发可先发两个拉取，再独立读取数据端点。STOP 后用各流的最终计数和状态核对收尾。独立 HSS 还检查终端 STAT 帧。SWO 和 ETM 的数据端点使用各自已有的原始流格式。
- RTT/HSS 可以各自排队向主机交付。目标 AP、采集时钟和 J7 引脚的仲裁由探针固件管理。
- ABI 2 的控制通道 0 操作 3 接收单字节 CDC 绑定或释放。SPI 从机收数走 IF3 的通道 4 和 EP10。H743 复验入口见 [SPI ABI 2 用例](selectio/README.md#abi-2-的-spi-从机接收)。

## 历史 ABI 1 的 USB 边界

双频效率候选的 HELLO 报告可协商的最大帧，并将当前会话设为 4,096 B。控制通道操作 8 的请求与成功回复均为一个小端 u32，可显式选择 4,096 或 16,384 B。16 KiB 档最大协议载荷为 16,367 B，16 B DMA 块头及缓存行对齐后每请求可传 16,320 B SRAM。SDK 的单 dTD 容量是 16 KiB。通道 7 操作 6 将同一块请求映射到探针私有 DDR，供分方向计时。内存通道操作 5 在一次或多次传输后、关闭会话前读取四个小端 u32，依次为 PS 参考时钟 Hz、端口、该队列的 timing 和 tap 寄存器。SWD timing 的低 2 位为速率码，JTAG 低 3 位为分频值。原 4 KiB 实板成绩列在下文。

Windows 自动为 MI_04 加载 WinUSB。其 DeviceInterfaceGUID 为 `{9DC2A831-F0DC-4F2E-9739-4E94B89DC8BB}`。主线 PL 加上新 PS 固件的接口试验中，IF4 对 0 至 4,079 B 的边界载荷逐字节回环成功。三轮各 60 秒，新载荷停等回环双向合计 18.26、18.20、18.36 MB/s，并在 IF0 插入 2,098、2,092、2,109 次 CMSIS-DAP 能力查询。重复帧号均被拒绝。这个测试包含 PC 生成图案与回环校验，未访问目标 SRAM。[真实描述符及吞吐](validation/selectio-integration/native-usb.json)

主线 PL 与后续启用原生流路由的 PS 配对，在 SWD 实际约 50 MHz 的 F103ZE 上，从 IF4 采集 Flash 首字 1 秒，收到 52,224 B，状态报告生成 10,002 组、跳拍 0。此处验证原生传输通路；100 MHz 融合 PHY 的验证见集成报告。

在支持 SPI→CDC 的 ABI 1 配对上，控制通道 0 操作 3 另有三字节 SPI 绑定 `[3, mode, mosi_tap]`。绑定后在 CDC DTR 有效时申请引脚。操作 4 的八字状态中，首字为 3 表示 SPI 接收绑定。数据走原有 CDC `0x83 IN`。 [历史命令](selectio/README.md#历史-abi-1-的-spi-从机接收转发)

## 命令

RTT＋HSS 的通道 6 启动计划可在变量地址表后附加一个小端 u32 请求频率，50/100 MHz 客户端继续使用原表长。

性能验证固件的通道 7 操作 7 测量探针端 CDMA 与 SWD 载荷 BRAM 的短突发。请求为三个小端 u32，依次为字节数（4–1024 且按字对齐）、重复次数（1–256）、时钟选项（0 使用当前 FCLK0，1 临时选择约 133.333 MHz 并恢复）。回复依次为七个小端 u64（定时器 Hz、上传总／最小／最大 tick、下载总／最小／最大 tick），再接三个 u32（FCLK0 Hz、SelectIO 参考 Hz、队列签名）。测量期间独占 CDMA，忙时返回状态 2。CLI 为 `python -X utf8 tools/selectio_dma_latency.py --out build/dma-latency`。

在融合工作树运行。新配对的 `info` 与 `usb-test` 使用 MI_03。后者校验每个响应。

```powershell
python -X utf8 toolbox.py selectio --serial 12345678 info
python -X utf8 toolbox.py selectio --serial 12345678 usb-test --seconds 60
python -X utf8 toolbox.py selectio read --help
python -X utf8 toolbox.py selectio write --help
python -X utf8 toolbox.py selectio rtt --help
python -X utf8 toolbox.py selectio scope --help
```

RTT 传入目标固件实际控制块或可扫描地址，HSS 传入 `地址:字节宽度:类型`，周期单位为 24 MHz tick。RTT 输出保留原始字节，Scope 输出保留 512 字节 HSS 帧。两者均经过原生接口；兼容路由的命令与采样率见仓库主线 CLI 文档。
