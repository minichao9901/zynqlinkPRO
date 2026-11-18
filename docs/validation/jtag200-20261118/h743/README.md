# H743 ARM JTAG 实板对照

2026-11-18，ZL-067、ZL-264。J7 HS3 `210299008529`，CMSIS-DAP `12345678`，STM32H743 rev. V，ARM TAP `0x6ba00477`、DBGMCU `0x20036450`。66 MHz 使用历史 [bit/ELF 配对](../../../../prebuilt/h743-jtag66-20261109/manifest.json)，物理 MEM-AP0 验证了 86172 B 的 Zynq OCM 执行段。

RCC 确认被测目标为 CPU 480 MHz、HCLK 240 MHz。AXI SRAM `0x24050000`，512 字/块、USB 队列深度 32、每轮每方向 64 块，使用 1 KiB TAR 回绕。下表为持续窗口中位数，单位 MB/s。TCK 取自 FCLK 和分频寄存器读回。

| TCK MHz | idle / 采样模式 | 写 | 读 | 时长 / 轮数 |
|---|---|---:|---:|---|
| 60 | 4 / 17 | 4.3733 | 4.4615 | 5.06 秒 / 84 轮 |
| 66.667 | 3 / 16 | — | 5.0238 | 60.02 秒 / 2258 轮 |
| 66.667 | 5 / 16 | 4.6131 | — | 60.02 秒 / 2082 轮 |

与[历史 60 秒数据](../../h743-jtag66-20261109/README.md)的读 5.0443、写 4.7756 相比，分别低 0.41% 和 3.40%。读测试使用低速预写的固定图案，写测试交替两种图案并核对最终读回。前两次混合测试在 idle3 写到第 181 字后返回 ACK `0x00`，idle5 完成 19 组后在第 181 字返回 ACK `0x07`。单方向通过的范围与混合长稳分开记录。

每轮开始前双读并备份 4 KiB SRAM，测后恢复且独立读回本区与两侧哨兵。最终恢复 HSI 默认时钟、原电压档和内核运行态，CR3 的 SCUEN 从 1 变为 0，锁定原 LDO 供电配置直至复位。没有写入 H743 Flash 或探针 QSPI。首次试配未锁 LDO 时 VOSRDY 等待失败，补做了 RCC、RAM、哨兵和运行态核对。复测由 [脚本](../../../../tools/jtag200_h743_baseline.py) 执行，逐轮数据见同目录 JSON。

## SelectIO ARM MEM-AP 块路径

沿用同一 H743 的 CPU480/HCLK240 和 AXI SRAM 页，改用 256 字块，在 Zynq A9 本地计时，包括 MMIO、发起 PL 块传输和逐字校验。历史值是主机 USB、队列 32 的独立读写窗口。新配对从 [0e734e9a](../../../../prebuilt/jtag-only-200mhz-arm-h743-20261118/manifest.json) 构建，133.333 MHz 主时钟约束下路由 WNS +2.118 ns、WHS +0.047 ns，物理 MEM-AP0 校验了 2392 B 的实际 OCM 执行段。频率来自探针 IO PLL、FCLK1 分频和物理时序档位读回。

| TCK MHz | idle | 窗口 | 读 MB/s | 写 MB/s |
|---|---:|---|---:|---:|
| 50 | 5 | 10 秒只读 | 2.700 | — |
| 80 | 1 | 10 秒只读 | 3.322 | — |
| 100 | 4 | 60 秒只读 | 3.894 | — |
| 160 | 6 | 60 秒只读 | 4.348 | — |
| 160 | 6 | 60 秒交替 | 4.347 | 4.609 |
| 200 | — | TAP 识别未通过 | — | — |

100 MHz 使用 tap16、时隙37、TMS/TDI 均提前一时隙。idle 1–8 的短读相差不足 0.001 MB/s。100 MHz 混合试验在 idle 4/24/40/96 均在第一个块报错，确认写吞吐为零。160 MHz 使用 tap24、时隙35，未提前 TMS/TDI。60 秒混合轮从两种反相图案交替写入并逐字读回，每方向验证了 133,961,728 B。200 MHz 试了 tap 0/8/16/24/31，包含在 50 MHz 先进入 Shift-DR、升至 200 MHz 再移位的对照。该结果将失败范围缩小到高速移位路径，尚待定位板级原因。[原始断点扫描](raw-selectio.json) · [块测试与恢复](selectio-arm.json)

XSim 的四位 ARM TAP 加五位边界 TAP 链在 100/200 MHz、idle 5、128 字下分别通过约 5.62/8.36 MB/s 的块读写，含完整协议和 SelectIO 原语。目标使用协议模型；实板结果以上表为准。六档原始波形和原 RISC-V 流水回归均通过。[仿真摘要](xsim.txt)

结束后使用历史配对在 JTAG 10 MHz 独立读回原 4 KiB SRAM、两端 guard、RCC 和内核运行态。切回历史配对时，常规加载器最初访问纯 JTAG 映像不存在的采集寄存器而拒绝加载。加载器补充物理 MEM-AP0 双签名识别并检查波形、时钟及块运行状态，两次实板切换和五项加载器单元测试通过。H743 Flash 和 Zynq QSPI 未写入。

## 66.667 MHz 同频对照和计时分解

SelectIO 使用与上一轮 ARM 实板相同的 bit，配套 ELF 加入 66.667 MHz 块档和计时。读回 `FCLK1_CTRL=0x00103000`，IO PLL 倍频 48，FCLK1 除 48，CLKDIV 33.333 MHz，每个 serializer 字两个完整 TCK。选定 tap16、采样时隙32，TMS/TDI 沿用默认发射相位。切换配对后独立核对 H743 的 CPU480/HCLK240。地址仍为 `0x24050000`，SelectIO 使用 256 字/块及 A9 单块计时，历史配对使用 512 字/块、主机 USB 队列 32、1 KiB TAR 回绕。没有外部频率计读数。[同频配对](../../../../prebuilt/jtag-only-200mhz-arm66-profile-20261118/manifest.json) · [逐轮计时](selectio-66.json)

| 配对 / 测法 | idle | 窗口 | 读 MB/s | 写 MB/s |
|---|---:|---:|---:|---:|
| 历史配对本轮复测，独立读/写 | 读 3 / 写 5 | 每方向 60 秒 | 5.024 | 4.613 |
| SelectIO 只读 | 3 | 10 秒 | 2.961 | — |
| SelectIO 只读 | 5 | 10 秒 | 2.961 | — |
| SelectIO 交替读写 | 5 | 10 秒 | 2.960 | 3.075 |

idle3 实读 29,542,400 B，全部逐字校验。按 1 KiB 块分解，扫描请求到完成 **263.58 µs**，其中 12,149 个 TCK 的周期预算为 **182.24 µs**，其余 **81.35 µs** 包含 serializer 补齐、回采排空、段间停钟和启动/完成握手。A9 再用 **80.06 µs** 逐字读取 BRAM 和比对，其他开销 **2.22 µs**。整块 **345.87 µs**。单算 PL 扫描速度为 **3.885 MB/s**，低于目标 **5.024 MB/s** 对应的 **203.83 µs/KiB**。idle 1、3、5、8 基本等速，idle 12 降至 2.830 MB/s。

恢复历史配对时，首次 USB 枚举尚未完成。保留失败记录，通过同序列号重新连接后使用备份恢复和读回，原 4 KiB RAM、两端哨兵、RCC、电压档和内核运行态全部一致。脚本已补限时等待该探针的 USB 重新枚举。H743 Flash 与 Zynq QSPI 没有写入。

XSim 在相同的 256 字、idle3 下复现 **12,149 个 TCK 和 263.40 µs** 的 PL 用时，距实板扫描用时 0.07%。30 ns 的 `CLKDIV` 下，6,076 拍用于发送（182.28 µs），789 拍等待回采（23.67 µs），1,915 拍在段间停钟及首尾握手（57.45 µs）。停钟中，DR 准备状态占 526 拍（15.78 µs）。idle5 多出的 526 个 TCK 把 263 个 CLKDIV 拍从回采等待移到发送，PL 用时相同。仿真没有 A9 数据校验或真实 H743 内存等待，支持先降低 ARM 块扫描的段间停钟和回采排空，再减少逐字 AXI 读取和比对占用。[XSim 分解](selectio-66-xsim.txt)

复测入口为 `python -X utf8 tools/jtag200_h743_block.py --compare-66 --pair prebuilt/jtag-only-200mhz-arm66-profile-20261118 --out <新的证据目录> --serial 12345678 --cable-serial 210299008529 --seconds 10 --execute`。

## 连续 ARM DRW 流水

ARM 流水保留原来的 `DP CTRL/STAT`、`SELECT`、`CSW`、`TAR` 建链和块尾 `RDBUFF`、`CTRL/STAT`。连续段按当前 H743 扫描链发送固定 DR 帧，发射与回采同时推进。回采的 ACK 属于当前 JTAG 扫描，数据来自上一笔已接受的 AP 访问。遇到 WAIT 时让已开始的帧回到 RTI，目标按协议丢弃该帧的更新，流水停止并返回错误。仿真验证 WAIT 后无重放、最后一字不符时报错、AP sticky fault 由末尾检查捕获。[Arm ADIv5 规范表 B3-8](https://documentation-service.arm.com/static/5f900abff86e16515cdc063b)

块描述符选择两 TCK/serializer 字和奇数 idle。流水可把原始数据留在 RX BRAM 供 A9 逐字复核，也可预装一次基准图案，由 PL 逐字比对。混合测试通过反相位交替写入两种图案。两种模式都完整保留读回数据。

66.667 MHz、idle3、1 KiB 同用例，仿真仍发出 12,149 个 TCK，读用时从 263.40 µs 降至 186.48 µs。扣除 182.24 µs 的物理发钟时间，整块额外时间约 4.24 µs，达到该扫描序列线速预算的 97.7%。idle5 交替读写各 194.16 µs。原始波形档、旧 ARM 路径和 RISC-V 路径仿真通过。[仿真分解](stream-xsim.txt)

补测 66.667 MHz、idle1 的流式仿真为 5.726 MB/s；100 MHz、idle3 为读 8.236、写 8.235 MB/s。H743 实板有效 idle 仍以连续测试判定。

从 `6ca21b98` 构建的配对在 133.333 MHz 约束下路由 WNS +2.116 ns、WHS +0.067 ns。首次上板预检时，旧 CMSIS-DAP 仍可枚举，Windows 显示下载器 `USB\VID_0403&PID_6014\210299008529` 的 `IsPresent=False`，XSCT 报可用目标为空。终止在预检，目标 RAM 和 Flash 写入次数均为零。[预检记录](stream-first-preflight.json) · [路由配对](../../../../prebuilt/jtag-only-200mhz-arm-stream-20261118/manifest.json)

### HS3 直连后的实板短测

HS3 `210299008529` 直连后恢复枚举，探针从 `BOOT_MODE=0` 先临时加载历史配对，CMSIS-DAP 恢复可用。随后临时加载新配对，物理 MEM-AP0 核对 **3016 B** 执行段，重新读回确认 H743 CPU480/HCLK240。当前目标使用 AXI SRAM `0x24050000`、1 KiB、TCK 66.667 MHz，tap16，采样时隙32。[加载身份](stream-direct-load.json) · [实板证据](stream-direct.json)

idle3 和 idle5 在时隙 32、33、34 上均在第二个流式 DRW 帧出现 WAIT。idle9 的两轮独立 A9 逐字读取并比对通过，2 秒从同配对的 2.959 提高到 3.503 MB/s。该轮计时中 PL 扫描 **4.881 MB/s**，根据 93,755,410 个 TCK 和实际档位计算的线速上限为 **4.973 MB/s**，达到 **98.15%**。因此低 idle 下的实板限制需计入目标 AP 等待。

PL 校验的 60 秒只读窗口已经提交给 A9，XSCT 轮询期间收到 `unknown or ambiguous address space AP0`。Windows 随后确认 HS3 缺失，切回历史配对在预检无可用目标。本轮尚未进入写入阶段，长测邮箱、RCC 和内核运行态待重新连接后取证。4 KiB 备份和两端哨兵保留在 `build/jtag200/h743-stream-board-direct`。脚本增加按序号取回既有 A9 测量结果的入口，并补齐 idle7、11、13 读档扫描。[恢复失败证据](stream-direct-restore-attempt.json)

### 重上电后的持续实板验收

重上电后原 A9 邮箱随旧探针配对一起消失。H743 已回到原时钟和运行态，RAM 和哨兵内容随本次外部重上电改变，第二轮使用新的 4 KiB 双读备份。HS3 `210299008529`、CMSIS-DAP `12345678` 恢复。实际 bit/ELF 经物理 MEM-AP0 执行段核对，H743 CPU480/HCLK240 经目标 RCC 独立复核。[重上电取证](stream-power-cycle.json) · [验收配对](stream-steady-load.json)

在 `0x24050000` 以 1 KiB 块运行，主机下发已读回的图案，PL 或 A9 逐字比对。TCK 由探针时钟寄存器和分频计算。线速预算取实际发送的 TCK 数及验证载荷，计入建链与末尾检查帧。

| TCK MHz | 路径与窗口 | idle | 读 MB/s | 写 MB/s | 每方向校验量 | 整体吞吐占发钟预算 |
|---|---|---:|---:|---:|---:|---:|
| 66.667 | 旧 SelectIO + A9，2 秒只读 | 3 | 2.959 | — | 5,908,480 B | — |
| 66.667 | 连续扫描 + A9，2 秒只读 | 7 | 3.598 | — | 7,182,336 B | — |
| 66.667 | 连续扫描 + PL，60 秒只读 | 7 | 5.0125 | — | 299,974,656 B | 96.68% |
| 66.667 | 连续扫描 + PL，60 秒交替读写 | 9 | 4.8331 | 4.8331 | 各 144,733,184 B | 97.01% |
| 100 | 连续扫描 + PL，10 秒只读 | 17 | 6.2795 | — | 62,593,024 B | 96.77% |

66.667 MHz 用 tap16、采样时隙32，100 MHz 用 tap16、时隙37、TMS/TDI 各提前一时隙。66.667 MHz 下 idle1、3、5 的连续只读返回 WAIT，混合在 idle5/7 返回 WAIT。100 MHz 在 idle3、5、9 的筛查主要返回 WAIT，部分采样点返回 ACK 错误。100 MHz 通过的是 10 秒只读窗口。历史 H743 66.667 MHz 经 CMSIS-DAP USB 队列的最佳读/写为 5.0443/4.7756 MB/s，本次选择探针本地持续校验模式。[完整结果与失败点](stream-steady.json)

末轮反相图案由恢复后的历史配对在 JTAG 10 MHz 独立读回，且相邻 3 KiB 一致。完成后恢复新备份的 4 KiB 与两端哨兵，前后 SHA-256 均为 `248a55d02bc9b70b40dee28beed9bf66e17641583e0274d46fb3936820132a2c`。核对 RCC、电压和内核运行态，探针停留在历史配对。H743 Flash 和 Zynq QSPI 写入均为零。[历史配对重载及 OCM 核对](stream-steady-restore.json)

## 100 MHz 写入及更高频率边界

100 MHz 连续扫描在 CPU480/HCLK240 下以 1 KiB 实际写入不同图案，先完成只读验证，再扫 TMS/TDI 发射相位和 idle。tap16、时隙37、提前 TMS/TDI 的只读达 6.279 MB/s，首个写试返回错误。试探其他设置依然出现写错误。首次失败后的 66.667 MHz AP 恢复也回 WAIT，改为在 50 MHz 先发 JTAG ABORT、清 sticky 状态并确认 H743 身份，再以固定页做一块写读恢复。已从历史配对独立确认 SRAM、两侧哨兵和目标状态恢复一致。逐组状态见记录。[首次写试](upper100-first.json) · [相位和 idle 扫描](upper100-phase.json)

为进一步测限，只增加 Zynq PS 的 FCLK1 分频档位。保留经过布线的同一个 FPGA bitstream。XSim 使用实际 SelectIO 原语验证新档位的周期和扫描位、旧档位和协议流水。[XSim 记录](upper-xsim.txt)
