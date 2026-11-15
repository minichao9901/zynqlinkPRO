# H743 SWD/JTAG Viewer 通用 MEM-AP 实板复验

2026-11-15（上海时间）。统一验收范围为 H743 的 RTT Viewer，SWD/JTAG 分别请求 50 MHz，工作台是真实本机源码和 Chrome USB 代理。探针、目标 Flash 和用户应用保持原样。

J7 USB/HID `12345678`、COM33、下载线 `210299008529`。物理 MEM-AP0 读到 QSPI BOOT_MODE 1，已知正式 ELF 的 OCM 执行段 85,716 B 与实机一致。正式 bit SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`、探针 ELF `64d00fe597030175920b994e39ff51db8a683dbb8d5f907c0f8d73f8d55044b9`。同一探针实际实测，RTT、HSS、DDR 和 DMA 均空闲入场。

实读 H743 DPIDR `0x6ba02477`、CPUID `0x411fc271`、DEV/REV `0x20036450`。原有 RTT 应用 `stm32h743_rtt_speed/fw.elf` 的完整 1,192 B Flash 装载段与 ELF 全等，SHA-256 `d0079519c3644ceab8bf5514980ac5ed30ac38f335a45d8680174d908a99073e`。完整 2 MiB Flash 独立双读 SHA-256 `7b6a4f9e7b83de0b9cf81236fe38508b5bcd519b7dc85fd9b811befdb77e666b`。应用心跳前进，真实 RCC 对应 CPU480/HCLK240，应用时钟错误数为 0。I-cache 开、D-cache 关、MPU 关，AXI 临时 RAM `0x24040000–0x24044fff` 双读备份。

## 统一入口与修订

首次从干净 `73899de6` 运行 `board.accept --only rtt-viewer --target-elf ...`，匹配 Flash 后两条链路均报 `ELF symbol missing: g_trace`。该符号属于仓库 CDC Golden，现场原应用不含此符号。预检、空闲和终态检测通过，保留原报告。

本轮将 H743 Viewer 的 CPU/HCLK 验证改为物理读取现有应用的 RCC，在已知 25 MHz HSE、PLL1P、待绪和 D1 分频条件下严格要求 480/240 MHz。匹配目标 ELF 各装载段、真实 AXI RAM 读回、D-cache 关闭、保护字节比较和外层恢复保持。其它用例仍沿用原目标时钟验证。没有为了测试替换 Flash 或增加虚拟时钟符号。

修后干净源码 `1642ac91` 的标准入口实板 4/4，包括预检、SWD/JTAG Viewer 两项及终态。实际读回两条均 49,999,999.5 Hz，页面分别报告 `zynqlinkPRO / SWD MEM-AP`、`zynqlinkPRO / JTAG MEM-AP`。单次 3 秒窗分别 117.99 / 112.60 kB/s，标准上行原始记录分别 466,716 / 458,528 B，顺序、下行和恢复通过。

## 同条件吞吐与完整性

对照两种源码 `f4b3a552`（通用化前）和 `1642ac91`（本轮）。同一实机、原应用、已验证 AXI 夹具、8 KiB 上行阻塞环、连续自增 u32、5 ms 轮询、源工作台 USB 代理与 Chrome 156.0.8078.48。在默认终端策略下先后计量三个约 3 秒窗口，再独立计一个连续 60 秒窗口。链路实际 49,999,999.5 Hz。旧版终端显示未被抑制，修后全部窗口中默认保护自动抑制显示。采样时保留默认业务，旁路观察原始接收字节避免 2 MiB 显示缓存截断。

| 版本及链路 | 3 个约 3 s 实得 kB/s | 3 窗中位 kB/s | 独立 60 s kB/s | 全会话实收 B及序号 |
|---|---:|---:|---:|---|
| SWD 旧 Wasm | 45.128 / 70.833 / 62.762 | 62.762 | 75.719 | 5,183,004，0–1,295,750 |
| SWD 通用 MEM-AP | 111.877 / 106.412 / 111.843 | 111.843 | 116.542 | 8,138,872，0–2,034,717 |
| JTAG 旧 Wasm | 0.512 / 0.512 / 0.512 | 0.512 | 0.546 | 38,400，0–9,599 |
| JTAG 通用 MEM-AP | 109.148 / 103.697 / 106.433 | 106.433 | 110.127 | 7,729,472，0–1,932,367 |

每组 Raw 从零到最后一个完整 u32 逐一核对，独立下行读回为 `00 a5 ff 31 32 0a 80 55`，横跨 64 B 环。WrOff 60→4、RdOff 保持 60，其余 56 B 保护字节原样。旧 JTAG 三个短窗只收到部分上行环，60 秒及全会话保留完整到达数据并通过上/下行回绕校验。

桥接的实际 DAP 请求按请求交付 ID 去重，独立于 CDC。旧 JTAG 数据期有 11,034 条 `0x14` 扫描、0 条 `0x06`。新 JTAG 有 9,332 条 `0x06`、0 条 `0x14`。新 SWD 在数据期执行 9,844 条 `0x06`，旧 SWD 两条。新 JTAG 在交换期物理 route 为 `0xe03`、采样 mode 17 和 idle 15，旧 JTAG 的 idle 为 1。路径证据使用页面实际 transport 和真实 USB 代理请求；统计总量及每窗均保存。

旧 CDC Golden 的测量只作历史参考：上一轮 H743 标准 3 秒单窗 SWD 76,389 B/s、JTAG 659 B/s，阶段 JTAG 最好 676.5 B/s。这里把当时的历史点与本次相同原应用的实测 A/B 分开。[上一轮 H743 报告](../h743-arm-jtag-web-20261115/README.md#最终实板结论)

### 相同显示状态的独立 A/B

为区分显示开销，在新夹具会话两边点击官方「暂停显示」。接收和记录保持运行。重新执行三个约 3 秒窗口，并独立验证到上行完整绕环、下行和保护带。此组支持与显示无关的吞吐提升，实际暂停状态和每窗接收量均记录。

| 链路 | 旧版 3×3 s kB/s | 通用 MEM-AP 3×3 s kB/s | 中位变化 |
|---|---:|---:|---:|
| SWD | 81.869 / 84.607 / 84.587 | 111.884 / 111.891 / 114.613 | 84.587→111.891 kB/s，+32.28% |
| JTAG | 0.512 / 0.512 / 0.512 | 109.148 / 109.166 / 106.398 | 0.512→109.148 kB/s，约 213 倍 |

默认显示策略下的 60 秒则为 SWD 75.719→116.542 kB/s、JTAG 0.546→110.127 kB/s。表中两组保留各自的显示条件。两组都未改变探针/目标时钟或 Flash。

## 复跑和证据

```powershell
python -X utf8 toolbox.py project run board.accept -- --board h743 --only rtt-viewer
python -X utf8 toolbox.py --runtime build/h743-viewer-web serve --native-probe --bit prebuilt/qspi-release/probe.bit --zynq-elf prebuilt/qspi-release/application.elf
```

```powershell
$h743ViewerElf = 'build/h743-viewer-mem-ap-20261115/matched-target/stm32h743_rtt_speed.elf'
python -X utf8 toolbox.py project run board.accept -- --board h743 --only rtt-viewer --runtime build/h743-viewer-web --out build/h743-viewer-new --target-elf $h743ViewerElf --jtag-cable-serial 210299008529 --execute
```

原始材料在 `E:\zynqlinkPRO\build\h743-viewer-mem-ap-20261115\`。首次缺符号报告为 `standard-start/`，修后正常入口 `standard-fixed/`，原版定向汇总 `review/summary.json`。默认长窗、暂停显示对照、完整原始流与逐项恢复在 `fixed-sustained/`、`baseline-sustained/`、`fixed-aligned/`、`baseline-aligned/`。`target-before/`、`target-after/` 和 `probe-after/` 保存独立核对。本轮只选择 Viewer，标准全板门槛 `accepted=false`。[证据索引](evidence.json)

- [x] 原应用继续运行，最终 `g_ms` 582,311→582,363，`g_clk_err=0`。全 2 MiB Flash 双读与初值一致。整个 20 KiB AXI 夹具独立双读恢复，SHA-256 `747a7576e40391bdcc93ceccae3c83a9e0c781d802e9ccb67ba915cae402eafb`。RCC/缓存/MPU、VTOR、DEMCR、FPB、DBGMCU/冻结配置及保护选项匹配，CFSR/HFSR 为零。
- [x] 探针的实际 QSPI 启动身份与 OCM 85,716 B 再次通过。最终 FCLK 99,999,999 Hz、GPIO 方向 `0xf`、路由 0，RTT/HSS/DDR/DMA 空闲。两个临时 worktree、浏览器/服务和运行目录已清理，原证据、私有备份、共享 `hw_server` 及已有 ZL-006 未提交修改保留。
- [x] CLI 109 项、Web 196 项、174 个模块语法和共享驱动一致性检查通过。更新 ZL-248、ZL-251 和 ZL-252。本结论限 H743/J7、该 CPU480/HCLK240 非缓存负载和本机代理 SWD/JTAG 50 MHz，第三方适配和其它芯片单独验收。

| 交付位置 | 本轮状态 |
|---|---|
| 本地源码 | 提交 H743 Viewer 的 RCC 验收入口修订和实板证据 |
| 远端 `main` | 只读核对 `d340cc3e`，本轮未推送 |
| 固定 EXE | v1.3.8、`3255b515`、2026-11-14 16:24:18 +08:00，本轮不更新 |
| Pages | 公开首页 HTTP 200、`gh-pages` `97ac02bc`，本轮不发布 |
| Release | 公开 v1.3.8，ZIP SHA-256 `7ed9bcde00d2ae120d13cd1b9a945beb31234fb4f1ada8a7c9502188e8d7199e`，本轮不发布 |
| 探针 QSPI | 保留正式原配对。运行态启动标记复核通过，实体冷启动和固化不属本轮 |

## Viewer 双板收尾复核

- [x] 本轮签收范围为两块板的 Viewer，F103ZE SWD/JTAG 60 MHz、H743 SWD/JTAG 50 MHz 均实际命中 MEM-AP，并完成完整序号、下行跨环与保护带验收。两板首次故障、修后汇总、60 秒窗口和同条件对照均保留。全板压力、H743 WebUSB 直连和发布均不在这次复验范围。[F103ZE 复验](../f103ze-arm-viewer-20261115/README.md)
- [x] 复核两板报告中原列的 51 个原始证据 SHA-256、配套 bit/PS ELF、目标 ELF 和长窗 RAM/FPB 备份。H743 匹配 ELF 另存本机 `matched-target/`，其 SHA-256 与标准结果一致。F103ZE ELF 及正式探针配对由仓库 `prebuilt/` 固定路径复用。
- [x] 复核 H743 最后实板快照，应用心跳前进，Flash/RAM/寄存器恢复，探针路由归零。两板测试服务与浏览器已退出，临时 worktree 已移除，共享 `hw_server`、原 ZL-006 未提交改动和固定安装 `data/` 保留。
- [x] 复核本地修复与归档、ZL-238/248/251/252、远端 `main` 和 `gh-pages` 指针、固定 EXE 的 SHA-256。公开下载包沿用表中任务期间记录的 v1.3.8 元数据，探针沿用已核验的现有 QSPI。
- [ ] **待办** 两份工作目录下的 `zynqlinkPRO-work/runtime/xilinx` 是重复的临时运行副本，确认没有本轮进程使用。执行环境拦截了清理命令，目录保留。共享 `hw_server` 使用 `E:/zynqlinkPRO-work/runtime/xilinx/`，清理目标与该共享目录不同。
