# H743 J-Scope、RTT 转发与 Chrome HID 授权实机验收

2026-11-13 至 11-14，Windows、Chrome 156.0.8078.48、J7 探针与 STM32H743。H743 运行用户提供的 `fw.elf`，SHA-256 为 `d0079519c3644ceab8bf5514980ac5ed30ac38f335a45d8680174d908a99073e`。经物理调试口读回 RCC 及固件时钟变量，CPU 480 MHz、HCLK 240 MHz。测流时 J-Scope 的 DEF 及原生 CLI 状态报告 SWD 59,999,999 Hz。RTT 请求同一 60 MHz 档位，状态以整数 MHz 显示 59。时钟值来自设备与寄存器读回。

先用既有 QSPI 0.7-nonce32 复现并完成长窗口 Web/CLI 对比，再用 [经 JTAG 加载的 0.8-nonce32 配对](../../../prebuilt/j7-probe-hid-20261114/manifest.json)检查描述符和流采集回归。Web 候选是在同一 GitHub Pages 地址用本地候选 JavaScript 做对照。Windows 冻结 EXE v1.3.6 用于复现，候选本机桥接结果来自源码服务。

## HID 名称和授权（ZL-211）

- 对照版只更新 HID 接口名称和 `bcdDevice`。HIDAPI 能读到名称，Chrome 的 `productName` 仍为空。关闭并重开专用测试配置后，USB 授权存在，HID 授权为空。
- USBPcap 只抓本探针的 EP0。Windows 从 HID 读取名称时，把 1024 字节应用缓冲区转成了 1026 字节的 `GET_DESCRIPTOR(STRING)` 请求。固件在计算短描述符实际长度前直接丢弃请求。请求出现约 5 秒取消；小请求能收到 32 字节名称和 18 字节序列号。
- 修复按描述符实际长度与 `wLength` 的较小值发送。未知索引停驻 EP0。实测 2、1026、4094 字节三档，名称和序列号返回正确。Windows `HidD_GetProductString` 与 `HidD_GetSerialNumberString` 用 64/512/1024/2048/4092 字节缓冲区均通过。WebUSB BOS、落地页、WinUSB 描述符及 CMSIS-DAP 包长 4096 字节通过。
- 首次打开测试配置并各确认一次 USB 和 HID，Chrome 显示 `zynqlinkPRO HID`。配置保存了该名称和序列号。关闭全部测试窗口再重开同一配置和站点，`getDevices()` 直接列出 USB、HID 两路。顶栏连接时两路 `requestDevice()` 调用次数均为 0。重新加载同一探针配对、USB 重新枚举后再次通过，并从 Web HID 读出版本 `0.8-nonce32`、构建时间 `Nov 14 2026 00:08:09`。
- 每个 Chrome 配置及站点来源分别保存授权。工作台启动时先枚举已授权设备，避免初始枚举尚未完成时误出设备框。

Windows 和浏览器实现参见 [HidD_GetProductString](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidsdi/nf-hidsdi-hidd_getproductstring) 与 [Chromium HID 权限保存条件](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/hid/hid_chooser_context.cc#162)。

```powershell
python -X utf8 tools/verify_webusb_landing.py --hid-name "zynqlinkPRO HID" --out build/hid-descriptors-check.json
```

## J-Scope（ZL-097、ZL-210）

同一组相邻的 `u32` 变量 `g_loops@0x24000008`、`g_ms@0x2400000c`。24 MHz 计时基准，10 µs 采样周期，暂停 CDC，实际采集标志 `0x21`。Web 点击开始/停止并导出 JSP，CLI 通过 HID 控制和原生 USB EP87 取数。独立解析两路原始帧，核对字段宽度、计数、包号、时间戳、单调性和 STOP 后硬件最终报告。

| 探针与入口 | 窗口 | 结果 |
|---|---:|---|
| 0.7，线上 v1.3.6 | 1 × 5 s | 收到 500,898 组，硬件最终 501,090 组，缺 192 组及 5 × 512 字节。已收到的包序号连续 |
| 0.7，WebUSB 候选与 CLI | 各 1 × 60 s | Web 99,978.32 组/s，CLI 99,969.55 组/s。探针分别跳拍 1,301 / 1,827 组，已经生成的样本与字节全部交付，两路包缺口均为 0 |
| 0.7，WebUSB 候选 10 µs | 5 × 5 s | 尾部全对齐。四轮零跳拍，一轮探针跳 807 组 |
| 0.7，WebUSB 候选 12 µs | 2 × 30 s | 83,333.33 组/s，两轮跳拍、尾差和包缺口均为 0。另三轮 5 s 中有一轮跳 123 组 |
| 0.8，最终 WebUSB 候选与 CLI | 各 3 × 5 s | 各轮 100,000 组/s，跳拍、尾差、格式错误和包缺口均为 0 |
| 0.8，本机源码服务 | 1 × 5 s | 501,387 组全部收到，100,000 组/s，零跳拍 |

EP87 发送 512 字节整包，原先 4096 字节 WebUSB 读在尾部可能持续等待短包。改为 512 字节整帧并发读，本轮每次挂 33 笔。先验证最终样本与字节数，再释放采样接口和剩余空读。探针内部跳拍仍单独报告。Zynq 旧 DEF 的 span 字段存的是变量数，网页继续逐项核对地址和类型。

长流后曾观察到本机源码服务和冻结 v1.3.6 在 HSS START 前确认目标类型返回 `-7`，探针两个引擎未运行而 HID 状态仍报 `-4`。DAP 队列复位未恢复，重新从已有 QSPI 自主启动后恢复。0.8 清洁会话复验通过，热切换原因仍待定位（ZL-212）。

## RTT 转发（ZL-213）

H743 RTT 通道 0，控制块 `0x24000014`，COM33、2048 字节探针批次。Web 用 Web Serial 记录，直接 CLI 用 pyserial。吞吐以实际保存字节和墙钟窗口计算，单位 MB/s 为十进制。

- 0.7 线上 v1.3.6 首轮停止后，启动按钮仍禁用。修复等待探针 STOP 排空及各异步状态退出后的按钮渲染。候选单页连续启动、停止四轮，每轮约 3.907–3.908 MB/s。
- 0.7 长跑浏览器同一生产会话保留四个 15 秒窗口，合计 234,463,232 字节，各窗口 3.9073–3.9077 MB/s。CLI 连续 60.009 s 得到 234,487,808 字节，3.90753 MB/s。所有窗口逐字节符合生产端重复字符串。有限重复字符串无法识别整周期遗漏。
- 另用可验缺口的 15,744 字节递增序列验证 Web 与 CLI，两个输出都逐字节一致，探针转发计数与目标读指针相符。核对整个 16 KiB AXI 临时区恢复。
- 0.8 本机候选源码服务同页反复启停三轮成功，约 3.53–4.11 MB/s。匹配的短窗口原生 CLI 为 3.756 MB/s。两路各自窗口内的重复字符串均完整匹配，探针读写错误为 0。

## 回归与现场

Web 静态检查覆盖 168 个模块，164 个 Web 测试通过。JTAG 核对 0.8 的 OCM 执行区 85,716 字节。验收后自主复位回原 0.7 QSPI，核对启动标记及 OCM 85,828 字节。H743 的 2 MiB Flash 双读与试前一致，SHA-256 为 `7b6a4f9e7b83de0b9cf81236fe38508b5bcd519b7dc85fd9b811befdb77e666b`。核心运行，VTOR=`0x08000000`，故障状态为零；HSS 与 RTT 均空闲。

原始记录保存在本机 `build/`，主要目录为 `stream-v136-public-hss`、`stream-v136-cli-hss-long`、`stream-candidate-web-hss-long`、`stream-candidate-web-rtt-long`、`stream-v136-cli-rtt-long`、`stream-rtt-fixture`、`stream-probe-0.8-r2-*`、`stream-probe-0.8-chrome-r2`（名称对照失败）、`stream-probe-0.8-chrome-r3`（成功）和 `stream-probe-0.8-chrome-reenumerated`。单探针测试串行执行。GitHub Pages、Releases、固定 EXE 仍为 v1.3.6。
