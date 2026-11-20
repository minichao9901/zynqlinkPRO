# J7 SelectIO 探针集成验证

## 2026-11-20 至 21 日的对照

- 主线起点 `03b6a1da`，JTAG 源 `dfb4e4d4`，SWD 源 `842f2990`。沿用 JTAG 八时隙协议字、SWD 四时隙换向、ARM APACC stream 和驻留队列。J7 的 TCK/SWCLK、TMS/SWDIO、TDI 用三个四时隙 OQ/TQ，TDO/SWDIO 各有独立 IDELAY 和 ISERDES。每个 JTAG 字在两个相关联的 100 MHz 并行时钟边沿输出。ETM 与调试延时元件共享同一 bank 的校准器，ETM 清窗口时保持校准。
- `python -X utf8 tools/selectio_cm3.py` 使用 Vivado 2018.3 UNISIM、同一 Cortex-M3 和相同的物理仿真引脚。HCLK 48 MHz，先以 TCK 100 MHz、采样时隙 21、idle 33 写读 256 字，再经停钟/高阻切至 SWD，SWCLK 100 MHz、时隙 12、idle 2 写读反相的 256 字，回到兼容模式。比较独立目标 SRAM 与返回的每一个字；SWD 双驱动、短时钟、数据错和超时均判失败。JTAG 简单照搬原 29 时隙会得到错误 ACK。参数须在物理线路重新确认。[原语与 CM3 记录](cm3.txt)
- 默认兼容构建的 `tb_cm3_jtag` 通过主线 HSS、RTT 跨 1 KiB、DDR 提交后更新 RdOff 及 posted read 检查。这个用例没有运行融合路径的 RTT/J-Scope。主机侧 DAP 输入、取消、USB epoch 与恢复用例通过。
- [HS3 与 J7 恢复](hs3.md)。主线正式配对临时加载后，比对目标 ELF 的 20,168 字节，CPU ID 411fc231、器件 ID 10036414，RCC_CFGR 0051040a。ETM 主线对照完成 1 秒 DDR 窗口，10 MHz SWD 配置，丢帧、解析错误、校准丢失、USB 读取错误均为零；解码 2 个 gap、1 个 unknown execution，目标 RCC 及 FPB 恢复。[主线采集](baseline-etm.json)
- 第一次 ETM 窗口的原始 15,372,291 字节成功下载，随后原生 deformatter 在新的兄弟 worktree 创建输出目录遭拒。同一输入在主仓库本轮专用输出目录成功解复用，源 ID 2 为 3,894,373 字节。随后使用主仓库本轮专用目录复跑了上列完整采集和解码。
- 构建中 RAW4 的 TRACECLK 在 opt_design 之前仍绑定 BUFIO shape，直接把该端口移到 J16 会失败。布局前、逻辑优化后再绑定 J7 端口。新配对的路由时序、实板速率以及完整 CLI 能力按后续记录验收。
## 100 MHz 双链路的首份实板配对

在同一份 [bit/ELF](../../../prebuilt/selectio-j7-100mhz-bringup/manifest.json) 上，F103ZE 保持 CDC48 的 HCLK 48 MHz。通过 USB 从主机发送每次重新生成的载荷，交替写和读 1 KiB。SWD 使用 tap8、slot20、idle2；JTAG 使用 tap16、slot28、idle33。两条通路均为 3 × 60 秒，逐次比较每一字节，每轮后独立低速读回末轮数据与哨兵。参考时钟从实际 PS 时钟寄存器读回约 200 MHz，线速换算为 99,999,999 Hz；未外接频率计。

| 链路 | 实际 PC 读 MB/s | 实际 PC 写 MB/s | 证据 |
|---|---:|---:|---|
| SWD | 0.1062–0.1064 | 0.1395–0.1398 | [原始三轮](first-swd.json) |
| JTAG | 0.0844 | 0.0834–0.0835 | [原始三轮](first-jtag.json) |

这一实现每个块都以 1 MHz 链路备份并恢复 DP/AP 上下文，GP0/GP1 的寄存器搬运也跟随低速 FCLK0。验证通过的范围为双协议共享引脚、数据正确和低速接管。性能差距保留为待优化项。完成第三轮后测试程序重新加载正式配对，首次等候 Windows 出现 CMSIS-DAP 超时；再调同一备份的恢复入口成功，已复核 4 KiB SRAM、两侧哨兵、AFIO、APB2、RCC、Flash 等待周期和目标运行状态。[独立恢复](first-restore.json)

该配对采用 133.333 MHz 约束，路由 setup +0.101 ns、hold +0.027 ns，bitgen DRC 通过。对 GP1 布线检查点实施的两条 I/O 改接见[原始 Tcl](first-iofix.tcl.txt)。兼容 SWD 回到高电平时钟前先以手动方式保持 SWDIO 低，重建链路后再恢复 AP。先前直接交还的版本会在恢复 SELECT 时返回错误。
