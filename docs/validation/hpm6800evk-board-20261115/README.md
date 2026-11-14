# HPM6800EVK 精简实板验收

2026-11-15（上海时间）。范围为 JTAG 25 MHz 的七项常规功能及三轮跨页软件动作，J-Scope 的单路和八路各确认 60 秒。用户排除实体 USB 数据拔插，标准入口保留对应待验。该板无 ARM ETM。交付限本地源码、报告和可复查索引。

## 现场身份与镜像

- J7 USB/HID `12345678`、COM33、XSCT 下载线 `210299008529`。COM34 属 CH340。物理 MEM-AP0 读到 QSPI BOOT_MODE 1 和正式 `0.8-nonce32` ELF 的 85,716 B OCM 执行段一致。正式 bit SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF SHA-256 `64d00fe597030175920b994e39ff51db8a683dbb8d5f907c0f8d73f8d55044b9`。探针未重启及未加载临时配对。
- 真读 HPM6880 hart0 TAP `0x1000563d`、DTMCS `0x7071`，通告 idle 7，原生工具配置下限 8，工作点采样相位 0。实际工作 FCLK 49,999,999 Hz、折算 TCK 24,999,999.5 Hz，依据探针分频寄存器读回。目标运行，`g_ticks` 持续递增。CPU0、MCHTMR0、AHB SYSCTL 控制分别为 `0x3020100`、`0x1010000`、`0x5040203`。
- 入场两次独立读取原应用前 128 KiB，SHA-256 `e02c28713f8804d31ef4b3ffa4289b9ddb0da57920deefaceff7aba3e82b4c4b`。保护范围含最后一个受影响扇区之后的 72 KiB。原 `dbgstress/fw.elf` SHA-256 `f76305dbb023612d114585fb6152a95949a5768988014084a051341a238124da`。启动头 144 B、所有代码和初始化数据匹配。SDK 链接脚本在 `0x80000400` 放 16 B NOR 配置并在相同 PT_LOAD 内附 3,056 B 对齐填充，实板该段全为 `ff`。
- 从双读备份派生本机专用 `hpm6800evk-dbgstress-live.elf`（SHA-256 `7cf8c56f4d7616166815f7a5a4306c423000f41c777ed625e4fb599c8e068261`）。逐一比较 PT_LOAD，唯一改动是 ELF 文件偏移 `0x400–0xfff` 的 3,072 B，与原实板字节全等，ELF 头、节布局、ROM boot header、符号和 DWARF 保留。标准入口五个文件 PT_LOAD 全字节身份检查保持开启。复核清单及可执行派生脚本见本机证据目录。

## 首轮故障和处理

SDK OpenOCD 原生配置显式选 CMSIS-DAP／HPM6800EVK 及 SDK 搜索路径。只读几何实证 `hpm_xpi` 是 16 MiB、4 KiB 扇区，已核对前 15 个扇区未保护，hart 清理后仍运行。实际 Web 入口解析得到 `0x80000400` 的 3,216 B 和 `0x80003000` 的 45,008 B。Web 对部分覆盖扇区先获取原字节，再合并 ELF 区域。原生以同一会话、两个原字节扇区块对齐实际覆盖范围，写入并验证扇区 0、1、3–13，总计 53,248 B。携带原非空字节的第 2 扇区保留在 57,344 B 完整回读/回滚保护区。首轮原生作业 3.900 s、Web 作业 30.445 s、独立软复位确认启动 4.474 s。两种作业均包含擦除、编程与各自校验。额外 128 KiB 工作 ILM 和核心通用/CSR 寄存器复核还原。擦、写、校验未单独计时。

首轮标准 RTT Viewer 的 917,504 B 原始文件中，偏移 913,408 和 913,468 处各被替换一个 32 位字。两处恰为 16 KiB 环内 `0x3000` 和 `0x303c`，两个值是待写的下行测试数据。夹具错误地将 64 字节下行放在上行环范围内。修订将 HPM 的上行固定 `0xf0401000–0xf0404fff`、下行 `0xf0405000–0xf040503f`、示波输入 `0xf0405100–0xf040511f`，运行夹具的 ILM 为 `0x00010000–0x000100ff`。原应用 ELF 的主数据、非缓存区与栈在 AXI/DLM，ILM 向量位于 `0x0–0x417`，没有已分配的 AHB 节；夹具仍按用例独立备份及回读恢复。保留原始失败及严格字节检查。

首轮压力第 1 轮启动调试并实际单步。实体拔插按本轮范围跳过，原生恢复发出 resume 时，DCSR.step 仍置位，hart 继续一步后再次暂停。原版正确阻塞第 2/3 轮及终态。独立串行会话读到 DCSR `0x4000b707`（cause=4、step=1）、PC `0x80006456`，八个触发器和 tselect 与开测相同。只清 step 后继续原 PC，DMSTATUS `0x4303a2` → `0x430ca2`，应用心跳 2,370,496 → 2,372,715，首 128 KiB 全等。无目标复位。新验收代码保存 step 位并在 DAP 交接恢复，其他 DCSR 字段、PC 与触发器独立保留。测试覆盖成功及异常退出。网页普通 Continue 单独复验正常：从 `0x4000b707` 继续后再次暂停读到 `0x4000b6c3`，应用心跳前进。

## 最终性能及功能

标准入口使用干净源码 `2445794c3c953c9bcf98fe7ded130b34c4eb849f`、本机源码工作台 v1.3.8（OpenOCD Wasm）及隔离 Edge。最终复验前，实读应用 CPU 600 MHz 和 MCHTMR 24 MHz。缓存控制 `0x7f03`，I-cache 与 D-cache 均开启。AXI 的 `0x01240000–0x0127ffff` 为 PMA 配置的非缓存区，RTT/J-Scope 测试使用独立 AHB RAM。

| 项目 | JTAG 25 MHz 实测 |
|---|---|
| SRAM | 2 KiB 暂停态，跨 1 KiB 与 1/2/4 B 非对齐，原生读/写 1.230/1.251 MB/s，网页单次命令往返读/写 5.81/5.88 kB/s。保护带和恢复通过 |
| Flash | 同 13 个 4 KiB 扇区，原生 3.856 s，网页 31.654 s，独立软复位及启动 4.510 s。两个作业各自含擦除、编程、校验，分阶段耗时未单独采集 |
| 调试 | 暂停/运行、指令单步、硬触发器、监视及恢复通过。源码级三个动作与回栈由下节的定向实板证实 |
| RTT Viewer | 3 秒窗约 229,795 B/s，942,080 B 整段从序号 0 连续，上/下行跨环，下行 8 B、WrOff=4。工作台默认渲染保护在吞吐窗自动介入，原始记录持续 |
| RTT 转发 | 两轮网页 1.549/1.552 MB/s，原生 1.562 MB/s。两轮探针 STOP 数和实收逐笔相等，分别为 6,574,080 / 6,690,816 B，另各有 15,360 B 数据留在原目标环。连续序号与新会话通过，511/512/513 B 的网页导出与预期字节完全一致 |
| J-Scope 单路 | 204 ticks、60.242 s、7,087,351 组、117.647 kS/s、1 跳，USB 丢包、帧序缺口、读错及 STOP 尾差均零 |
| J-Scope 八路 | 1,012 ticks、60.236 s、1,428,522 组、23.715 k组/s、12 跳（0.000840%），USB 丢包、帧序缺口、读错及 STOP 尾差均零 |

J-Scope 两路的正式窗都核验了 DEF、采样值、计数、导出 CSV 和原始 JSP 回放。单/八路本机队列高水位为 19,968/36,352 B。八路 860 ticks 的短窗跳拍 6.2515%，完整保留，之后 1,012 ticks 短窗无跳拍并进行正式长窗。

历史 [11-09 HPM](../hpm6800-workbench-acceptance-20261109/README.md) 的 SRAM 流水线深度与事务不同，Web 20 KiB 运行态表也与本次 2 KiB 暂停态单命令不同。RTT Viewer 同为本机桥接的 AHB 非缓存环历史中位 222.046 KiB/s，当前约 224.4 KiB/s，窗与重复数不同。历史公开 Pages 的 784.4 KiB/s 使用直连 WebUSB。RTT 转发历史 1.559 MB/s 为直连 Web Serial，原生匹配条件历史对照 1.553 MB/s。J-Scope 原生 174/920 ticks 的历史窗为 10 秒，网页最终阶段按 60 秒及实际完整性判据选档。

烧录同口径首次及最终两次均为 13 扇区，同一实际 TCK、两个原生输入块 SHA 一致，全部读回和启动均通过。最终定向复跑原生/网页/启动为 3.910/31.369/4.400 s。两次最终网页比首次 30.445 s 高 3.97% / 3.03%，相互相差 0.91%。网页预览和实际 `programFile` 分开计时，三轮预览 0.123/0.182/0.183 s，实际作业调用 30.431/31.652/31.365 s。三轮烧录实现相同，现有日志无法区分作业内的单扇区擦除、写入、回读或 USB/Wasm 往返各花多少时间，保留该差异。

## 跨页与汇总

统一入口报告对 HPM6800EVK 记录 **9 通过、0 失败、3 待验、1 不适用、0 阻塞**。三轮跨页软件动作 **9/9** 通过。每轮正常连接、工作态取证、退出和恢复都在同一个隔离浏览器会话内执行。

| 轮次 | 实际顺序 | 对应实体待验 |
|---|---|---|
| `jtag-stress-1` | 转发切页 → Viewer 空闲断开 → 调试 → J-Scope 活动断开 | 调试暂停中拔插 J7 数据 |
| `jtag-stress-2` | 转发活动断开 → J-Scope → Viewer 切页 → 调试空闲断开 | J-Scope 采样中拔插 J7 数据 |
| `jtag-stress-3` | 调试活动断开 → 转发空闲断开 → J-Scope 切页 → Viewer | Viewer 收数中拔插 J7 数据 |

原版 `--review` 合并同一 clean SHA 的全套及 Flash 定向复跑，保留 `accepted=false`。用户范围已全部通过，标准报告三项待验仅归因于排除的三次实体动作。ARM ETM 不适用。本机机器可读索引同时保留首次实际故障、修复及复测。

### 源码调试的独立更正

逐项复核发现原版把从 `engine_leaf` 入口触发的「单步进入（指令级）」判为源码步入通过（ZL-249）。保留原版汇总及这一实际返回值。同一 `2445794c` 现场另用正常网页动作和已匹配 ELF 的 DWARF，逐项证实 `main.c:98` 的直接指令 `0x800056fa` 调用 `model_checksum`：步入 `model.c:161`（`0x800063dc`），步过下一源码行 `model.c:162`（`0x800063e0`），展开 CFI 调用栈核对 `main` 的返回 PC 与 SP，再源码步出至 `0x800056fe`，恢复调用者 SP。使用原运行应用，调试用例释放硬触发器并恢复运行。

修订 `6eb9c1a36212d15073bccc28da84e51d06c80864` 只改统一入口的源码调试用例及其测试，以相同真实调用、DWARF 源码落点、回栈、PC/SP 和实际源码动作判定调试。该提交的干净标准 `--only debug` 实板再次通过预检、调试和终态；这个报告单独归档。其源码 SHA 与整套不同，未混入原版汇总，亦未因此额外重跑擦写。

## 复跑和收尾

用本机隔离鉴权工作台，明确传入已核验的 QSPI 配对，使用精确匹配的运行 ELF。HPM SDK 参数指向 v1.11.0 配套树。

```powershell
python -X utf8 toolbox.py project run board.accept -- --board hpm6800evk
python -X utf8 toolbox.py --runtime build/hpm-web serve --native-probe --bit prebuilt/qspi-release/probe.bit --zynq-elf prebuilt/qspi-release/application.elf
```

```powershell
$hpmTargetElf = 'build/hpm6800evk-board-20261115/hpm6800evk-dbgstress-live.elf'
python -X utf8 toolbox.py project run board.accept -- --board hpm6800evk --runtime build/hpm-web --out build/hpm-new --target-elf $hpmTargetElf --jtag-cable-serial 210299008529 --seed 680014 --openocd E:/sdk_env_v1.11.0/tools/openocd/openocd.exe --openocd-scripts E:/sdk_env_v1.11.0/hpm_sdk/boards/openocd --allow-flash --execute
python -X utf8 toolbox.py project run board.accept -- --review build/hpm-new --out build/hpm-review
```

原始材料保存在 `E:\zynqlinkPRO\build\hpm6800evk-board-20261115\`。其中 `first-standard/` 是保留的首次失败，`final-standard/` 是修后全套，`final-flash-repeat/` 是同提交定向复跑，`review/summary.json` 是未经改动标准汇总。`initial-target.json`、`matched-elf.json`、`native-geometry.log`、`web-prepared.json`、`hart-recovery.json`、`before-retest/`、`after-retest/`、`probe-after/` 及私有 Flash/RAM 备份可独立复核。 [证据及 SHA 索引](evidence.json)

同版严格源码补证保存于 `strict-source-supplement-confirmed/result.json`，修后标准定向报告为 `final-strict-debug/summary.json`，其后整片/应用及空闲复核为 `after-strict-debug/result.json`。

- [x] 最后在 HPM 整片 16 MiB 独立读回。最终复验前、Flash 复跑后及严格调试后 SHA-256 均为 `496a76af612db150c8c1d960ee8cffc54ee6219a187876cf0624cb0b440b0bb4`。前 128 KiB 两次读回均与入场原件全等，未擦的第 2 扇区单独核对。工作区 128 KiB ILM、临时 AHB/ILM 地址和寄存器都有各用例恢复证据。
- [x] 原应用软复位后运行，最后 `g_ticks` 3,523,361 → 3,523,872，陷阱计数 0；CPU、SYSCTL、缓存/PMA 和八个硬触发器与复验前一致。探针按 HPM 业务档收尾，FCLK 49,999,999 Hz、TCK 24,999,999.5 Hz，GPIO `0xf`/路由 `0`，RTT/HSS、DDR/DMA 和本轮 USB/HID/COM 空闲。
- [x] 问题表更新 ZL-215、ZL-245–ZL-247、ZL-249。只清理本轮工作台、令牌与隔离检出，原始报告及备份保留，保留共享 `hw_server`、其他板卡的证据及既有 ZL-006 工作区改动。

| 交付位置 | 本轮状态 |
|---|---|
| 本地源码 | 统一入口修订与验收报告均纳入本地提交 |
| 远端 `main` | 只读核对 `d340cc3e`，本轮未推送 |
| 固定 EXE | 现有 v1.3.8，源码 `3255b515`，构建 2026-11-14 16:24:18 +08:00，SHA-256 `03d32e5b288336d805b491476186ef0fbe18129b9c683a26c7810c7fd5a54ca6`，本轮不更新 |
| Pages | 公开首页 HTTP 200，`gh-pages` `97ac02bc`，本轮不发布 |
| Release 下载包 | 公开 v1.3.8，ZIP digest `7ed9bcde00d2ae120d13cd1b9a945beb31234fb4f1ada8a7c9502188e8d7199e`，本轮不发布 |
| J7 QSPI | 沿用正式镜像，最终物理 OCM 85,716 B 一致、BOOT_MODE 1；实体冷启动与固化均在本轮范围外 |
