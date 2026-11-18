# J7 段间握手与 HPM5301 DMI 边界复测

2026-11-18。探针为 Zynq-7020/J7，Digilent HS3 序列号 210299008529。PL 仍为纯 JTAG。优化前后均沿用 80 MHz Hazard3 MCU RTL、原 AHB/SRAM 和 0.8 ns TDO 传播模型，使用真实 Xilinx 7 系列 MMCM、OSERDES、ISERDES 和 IDELAY 仿真。每个块 128 个 32 位字，AXI 提交至完成计时，写入后检查目标 SRAM，读回后逐字验证。

## 同口径 A/B

| 200 MHz、idle 20 | 读块耗时 | 写块耗时 | 读 / 写 MB/s | 独立 TCK |
|---|---:|---:|---:|---:|
| 原流水 | 94.725 µs | 94.770 µs | 5.405 / 5.403 | 9,125 |
| 缩短握手并保持电平 | 59.505 µs | 59.550 µs | 8.604 / 8.598 | 9,125 |

时间差 35.220 µs，读块耗时减少 37.2%。每块仍为 142 段，45.625 µs 用于 9,125 个 TCK。扣除 TCK 的读块开销由 49.100 降到 13.880 µs，减少 71.7%。去掉固定的每段前导与排空，合并同模式、同方向的连续 DRW 状态跳转，最后在块完成时等待物理输出排空。SBA 末尾状态核对保留，故障注入覆盖写入不重放。50/66.667/80/100/160/200 MHz 的原始波形模式继续通过回归。

[原 Hazard3 频点](../pipeline/hazard3-200-idle-fine.json) · [缩短握手](hazard3-after-shortening.json) · [最终保持电平版](hazard3-final-hold.json)

## 实板定位

以同一 USB 现场、J7–J5 接线与 1 KiB ILM 备份为对照。50 MHz 的块读完整匹配，首个 SBDATA 原始字为 0xF2003348BC，数据位解码为备份中的 0x800CD22F。初版在停顿期间固定拉高 TMS/TDI，200 MHz/tap24/时隙38–39 的流水首个 DMI 字是 0xC1。延后采样读出状态看似成功的 0x60，但首个 SBDATA 变成 0x10，解码为 0x4，与备份不符。这两种结果在 idle 20 和 256 均能出现。

在原始波形路径，连续的同一组 TAP/DMI 命令于 tap24/时隙39 成功，拆段且将间歇电平置高时重现 0xC1，连续读取 DMSTATUS 失效。把每个停顿保持为上一拍有效 TMS/TDI 后，在原始波形路径的整组命令三次复验均通过。只在进入 Shift-IR 边界预置下一拍有效电平也能恢复；在 reset 后、Update-IR 后和 DMSTATUS 后，预置下一拍不够，保持上一拍可以恢复。这个对照将问题定位到段边界的 TMS/TDI 电平切换。实板没有对单根线做示波器量测，具体是哪根线及其模拟机理仍待测。

原始错位包含伪造的状态低两位，不能用来推断目标实际 DMI BUSY。对照期间只读取目标 RAM。

[停顿置高流水](hpm-forced-high.json) · [单边界复放](hpm-single-boundaries.json) · [停钟时的电平对照](hpm-stopped-clock-controls.json) · [整组停顿保持上一拍](hpm-raw-hold-all.json)

## 保持电平版复验

最终版在段尾未满的时隙及整段停钟时保持上一拍 TMS/TDI。XSim 验证了实际序列器输入的停钟电平，Hazard3 的 59.505 / 59.550 µs 保持一致。布线 WNS +2.091 ns、WHS +0.052 ns。缩短握手但置高的故障对照版本 WNS +2.023 ns、WHS +0.064 ns，两版使用独立 SHA-256。

- HPM5301 在 200 MHz/tap24/时隙39/idle256，首帧回到 0x0、首个 SBDATA 恢复 0xF2003348BC。三轮 1 秒读块全部逐字校验通过，共 6,024,192 B，零 BUSY 或无效响应，Zynq 本地只读中位吞吐 2.010 MB/s。
- 同 tap/时隙使用 idle20 时，首帧仍然正确；随后 DMCONTROL 的响应为 0x4000000003，DMI 状态低两位为 3。50 MHz 恢复以及原始重放对照保留，区分真正 BUSY 与置高导致的无效原始响应。HPM5301 的 DMI 等待边界仍待寻优；Hazard3 的 idle20 结果使用独立模型。
- 上板前双读备份 1 KiB ILM 和两侧哨兵。本轮实板只读 RAM；恢复原 J7 bit/ELF 并以 50 MHz 重新独立读回，全量和哨兵一致，调试控制恢复。备份及恢复 SHA-256 为 a358670a636c1bad3d5014b5328db1a9be9290e9dda10271c59a12d74903c88c。未擦写 Flash/QSPI。引脚实频未用示波器量测。

[保持电平版实板记录](hpm-hold-final.json) · [独立读回](final-ram-readback.json) · [优化故障对照配对](../../../../prebuilt/jtag-only-200mhz-handshake-20261118/manifest.json) · [最终配对](../../../../prebuilt/jtag-only-200mhz-handshake-hold-20261118/manifest.json)

可用 tools/jtag200_hazard_sim.py 的 --fine 重跑时隙和 idle 细扫。tools/jtag200_hpm_dmi.py 的 snapshot、diagnose、boundary、boundary-controls 和 verify 支持复现，硬件执行需显式 --execute。实板只读长期窗口使用 diagnose --steady。
