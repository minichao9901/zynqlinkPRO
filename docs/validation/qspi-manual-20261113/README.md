# QSPI 固化与可执行手册重包验收

2026-11-13，用户将 XC7Z020 探针切到 QSPI 拨码并断电重上后，实读 BOOT_MODE 为 1。预检确认 RTT、HSS、调试、采集、DDR 和 DMA 空闲。JEDEC ID 为 EF4019。使用正式 J7 的 [QSPI 包](../../../prebuilt/qspi-release-20261106/README.md)。

| 项目 | 实测结果 |
|---|---|
| 板上固化 | `probe-flash --skip-backup`，受限辅助器成功写入 4,281,040 字节，逐字节读回一致。BOOT SHA-256 为 `fd8d0411388767d4ec37aa690b3ae375f7df64c071cd221fd80fa02954dda6bf`。独立读回后无暂停复位，启动交接成功。 |
| 验收边界 | 用户要求省略原镜像备份。初次预设备份在只读阶段停止，SDK 已落盘一个 32 MiB 文件。实际固化使用跳过备份模式，未比对 BOOT 擦写范围外的字节。 |
| 实体冷启动 | 用户确认断电重上电。CMSIS-DAP、HID 与 COM33 重新枚举。只读 JTAG 物理 MEM-AP0 核对 85,844 字节 OCM 执行代码，与正式 PS ELF 一致。FCLK 由寄存器推算为 99,999,999 Hz。 |
| 配对 | bit SHA-256 为 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF 为 `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802`。 |
| 可执行手册 | 真实 Chromium 逐条运行生成 BSP、编译启动程序、打包和核对清单。新 BOOT.bin 与实板读回的正式 BOOT 逐字节相同。新编译的 QSPI 读写辅助 ELF 另有哈希，这次实板使用正式包内的原辅助 ELF。 |

板上最终仍为 QSPI 启动，探针采集和数据流空闲。没有操作目标 MCU。原始记录位于本机 `build/qspi-acceptance-20261113/`，新镜像位于 `build/qspi-repack/f40958a9043f/image/`。共享 hw_server 保留。73 项 CLI 测试通过。关联 ZL-205。
