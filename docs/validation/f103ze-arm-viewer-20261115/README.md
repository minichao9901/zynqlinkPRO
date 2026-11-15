# F103ZE SWD/JTAG Viewer 通用 MEM-AP 实板复验

2026-11-15（上海时间）。验收只覆盖 F103ZE 的网页 RTT Viewer。两条链路请求 60 MHz，确认实际接管、连续上行、跨环下行、吞吐和恢复。使用本机源码工作台和隔离 Chrome、实际本机 USB 代理。现场未写目标 Flash 或探针 QSPI。

入场确认 J7 USB/HID `12345678`、COM33、下载线 `210299008529`。F103 CDC 独立枚举为 COM5 `F103CDC0001`。正式探针 QSPI 启动 BOOT_MODE 1，物理 MEM-AP0 核对 OCM 执行段 85,716 B。bit SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF `64d00fe597030175920b994e39ff51db8a683dbb8d5f907c0f8d73f8d55044b9`。USB 队列、RTT/HSS/DDR/DMA 空闲。

F103ZE DPIDR `0x1ba01477`、CPUID `0x411fc231`、DEV/REV `0x10036414`。CDC48 源 ELF `e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f` 的 20,168 B 装载段与板上相同，应用报告 48 MHz 且心跳前进。完整双读的 512 KiB Flash SHA-256 `48f226217497607c696a156addbb363925577499b00ee64f187bd5eea7a94499`。Golden 的 SWJ_CFG 为 2，从匹配源码确定。JTAG 用例临时打开并恢复 AFIO/APB2，MAPR 的 SWJ 位不可用来读回原配置。

## 首次回落与代码修复

干净 `3a99c312` 的标准 `board.accept --only rtt-viewer` 两条功能项均通过，但页面均报告 `OpenOCD Wasm / WebUSB`，接管失败。在各自 3 秒取样，SWD 实得约 153.9 kB/s，JTAG 约 0.824 kB/s。原报告与独立短窗诊断均保留。

两条链路 Wasm 实际回报小端、MEM-AP0、AP IDR `0x14770011`、AP CFG `0x00000000`、CSW `0x23000052`。JTAG 对应 `stm32f1x.cpu`。接管时两个实际包均为 `05 00 03 08 f0 00 00 00 0f 0b`，回包 `05 03 01 11 00 77 14 03 f0 0f e0`。末字 `0xe00ff003` 是 AP BASE `0xf8`。源代码读取 CFG `0xf4` 时用了 BASE 的 CMSIS-DAP 选择位，按设计触发「MEM-AP 寄存器与 OpenOCD 不一致」并回退。

`a77a339a` 将 CFG 读取改用 `0x07`（AP read、A2=1、A3=0）。修订的测试按真实 A[3:2] 计算 AP 寄存器，令 CFG 和 BASE 不同。原身份、AP 属性、地址及失效回退判据继续保留。修后标准入口双链路均命中，真实 59,999,999 Hz，3 秒窗口 SWD/JTAG 分别 102.1 / 120.7 kB/s，标准用例连同预检和终态为 4/4。

## 同条件吞吐和完整性

本机 USB 代理和 Chrome 156.0.8078.48，8 KiB 上行阻塞环、连续自增 u32、5 ms 轮询和默认终端显示策略。对照 `f4b3a552` 使用通用化前的 SWD Wasm / F103 专用 JTAG 路径，修后 `a77a339a` 使用通用 SWD/JTAG MEM-AP。各链路 3×3 s 后另外连续计 60 s，时钟从独立物理 AP0 读取，窗口内维持 59,999,999 Hz。长窗取样使用本机实际网页旁路记录原始接收数据，正常 Viewer 的录制、显示和游标行为仍在运行。

| 链路及版本 | 3 个约 3 s 实得 kB/s | 3 窗中位 kB/s | 连续 60 s kB/s | 全会话连续 B |
|---|---:|---:|---:|---:|
| SWD 旧 Wasm | 65.49 / 111.87 / 111.89 | 111.87 | 109.99 | 7,598,464 |
| SWD 修后 MEM-AP | 111.87 / 109.14 / 109.16 | 109.16 | 117.22 | 8,171,624 |
| JTAG 旧 F103 MEM-AP | 114.62 / 111.90 / 111.87 | 111.90 | 115.18 | 8,097,932 |
| JTAG 修后通用 MEM-AP | 95.50 / 103.70 / 103.70 | 103.70 | 114.36 | 7,925,984 |

以上旧 SWD 首窗渲染未抑制，之后自动抑制。其他行的完整显示状态按每个窗口保留。对照时修后 SWD 长窗 +6.58%，JTAG −0.71%。先前 JTAG 历史代理 137.80 kB/s 在本次旧源码也未重现，历史直连 WebUSB 不用于本机代理对照。相同终端自动抑制状态下另逆序复跑 3×3 s，检验较低的首组三窗。

旧 SWD 的首组长窗脚本在完成连续性、下行及现场验证后，因观察器错误地要求 Wasm 一条 `0x06` 都不发而标记失败。实际该会话共五条 `0x06`，不影响已记录的完整字节、时钟和路径。保留原样报告，纠正观察判据后的旧 SWD 逆序短窗复跑通过。

| 链路 | 先跑修后 3×3 s kB/s | 后跑旧版 3×3 s kB/s | 旧版 → 修后中位 kB/s |
|---|---:|---:|---:|
| SWD | 114.62 / 114.59 / 114.59 | 109.16 / 114.61 / 103.69 | 109.16 → 114.59 |
| JTAG | 106.42 / 111.89 / 111.88 | 111.90 / 111.88 / 111.88 | 111.880 → 111.884 |

原始有序性从每次夹具的序号 0 验到文件最后一个完整 u32。修后长窗两条链路各有约 9,874 / 9,577 条实际数据期 CMSIS-DAP `0x06` 命令（扣除初始连接请求）。JTAG 数据期相位 16、idle 15，释放后相位回到 17，无残留路由。SWD/JTAG 下行均独立在 SWD 回读目标 SRAM，已确认 `00 a5 ff 31 32 0a 80 55` 横跨 64 B 环，WrOff 60→4、RdOff 保持 60，其余 56 B 保护带不变。

## 独立上下行请求剖析

在正式计时之外另各跑 3 秒并保持相同渲染抑制。两条修后采到实际握手请求 `05 00 03 08 f0 00 00 00 0f 07`。旧 SWD 上行主要由 Wasm 合并为 452 个 `0x05` 请求，其中 351 个含 255 个传输操作。控制块/游标读 50、游标写 50。修后 SWD 的同类上行有 434 个 `0x06`，控制块读 48、独立地址和控制设置 530、游标写 48。旧/新 JTAG 上行块为 439/435，独立设置 538/531，游标写均为 49。剖析中修后 SWD 的额外请求来自每块分别设置 AP/TAR 后再读，逆序短窗与连续 60 秒未证实持续退化。保留首组短窗的实测差值。

## 复跑与现场

```powershell
python -X utf8 toolbox.py project run board.accept -- --board f103ze --only rtt-viewer
python -X utf8 toolbox.py --runtime build/f103-viewer-web serve --native-probe --bit prebuilt/qspi-release/probe.bit --zynq-elf prebuilt/qspi-release/application.elf
```

```powershell
python -X utf8 toolbox.py project run board.accept -- --board f103ze --only rtt-viewer --runtime build/f103-viewer-web --out build/f103-viewer-new --f103-restore-swj 2 --jtag-cable-serial 210299008529 --execute
```

原始材料在 `E:\zynqlinkPRO\build\f103ze-arm-viewer-20261115\`，`standard/` 和 `diagnostic-r3/` 保留首次回落，`standard-fixed/` 与 `review/summary.json` 保存标准定向结果，`final-sustained/` 和 `baseline-sustained/` 保存原始完整长窗和逐项恢复。逆序对照在 `fixed-warm/`、`baseline-warm/`，独立请求证据在 `fixed-profile/`、`baseline-profile/`。仅选择 Viewer 的标准汇总保持全板 `accepted=false`，其它用例不属于本轮。[证据索引](evidence.json)

- [x] 逐项核对临时夹具 RAM、核心寄存器和 FPB，JTAG 条目另恢复 AFIO/APB2、SWJ_CFG 及采样相位。独立双读 512 KiB Flash 仍为入场 SHA-256，RCC、DEMCR、VTOR、FPB 和可读 MAPR 相同。原应用全程可恢复运行，最终心跳 251,140,382 → 251,155,863。
- [x] 停测后 J7 路由为 0、GPIO 方向 `0xf`，FCLK 恢复入场 99,999,999 Hz。RTT/HSS/DDR/DMA 空闲，两个 worktree 和本轮浏览器、服务、令牌目录清理，共享 `hw_server` 和其它板卡报告保留。ZL-238、ZL-248 和 ZL-251 同步更新，H743 的实板结论待换板。

| 交付位置 | 本轮状态 |
|---|---|
| 本地源码 | MEM-AP CFG 修订及验收报告 |
| 远端 `main` | 只读核对 `d340cc3e`，本轮未推送 |
| 固定 EXE | 现有 v1.3.8，源码 `3255b515`，构建 2026-11-14 16:24:18 +08:00，本轮不更新 |
| Pages | 公开首页 HTTP 200，`gh-pages` `97ac02bc`，本轮不发布 |
| Release | 公开 v1.3.8，ZIP SHA-256 `7ed9bcde00d2ae120d13cd1b9a945beb31234fb4f1ada8a7c9502188e8d7199e`，本轮不发布 |
| 探针 QSPI | 正式原配对，最终 BOOT_MODE 1 和 85,716 B OCM 已复核，实体冷启动和固化不属本轮 |

后续已完成 H743 Viewer 定向复验。两板的证据哈希、恢复、交付及临时目录状态见[双板收尾复核](../h743-viewer-mem-ap-20261115/README.md#viewer-双板收尾复核)。
