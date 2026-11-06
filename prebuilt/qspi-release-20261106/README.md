# J7 QSPI 启动交付 · 2026-11-06

当前 J7 / F103ZE 限定启动包。正式 bit/PS ELF 与 [RAM 配对](../release-20261106/README.md) 完全相同，本轮未改 RTL、未重新综合或重编主应用。BOOT 使用专用 QSPI PS 初始化和 OCM stage0 → DDR stage2 → OCM 主应用的启动链。

| 文件 | SHA-256 |
|---|---|
| BOOT.bin | `fd8d0411388767d4ec37aa690b3ae375f7df64c071cd221fd80fa02954dda6bf` |
| probe.bit | `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6` |
| application.elf | `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802` |

BOOT 4281040 B，实际擦写范围 `[0, 4284416)`。整片32MiB备份、受限辅助器写入、逐扇区/逐页校验、独立整片回读与范围外逐字节比较通过。无暂停复位启动及用户实际断电重上电均通过，冷启动后不下载bit/ELF，物理MEM-AP0的85844 B主应用执行段匹配。WebUSB、SWD10、JTAG1/10与24MHz ETM 100ms回归通过。[验收报告](../../docs/validation/qspi-release-20261106/README.md) · [验收身份](acceptance.json) · [全部文件哈希](flash_manifest.json)。

QSPI引导空闲FCLK约100MHz；请求10MHz调试档后读回FCLK约120MHz。133.333333MHz仍为该bit的实现约束，不能把约束当作运行时钟。ELD1默认五路零tap。目标MCU保持CDC48/TRACECLK24MHz及运行，未烧录目标Flash。

```powershell
# 不接触硬件，只验证包身份并显示计划：
python -X utf8 toolbox.py probe-flash --dry-run
# 确认独占板卡、QSPI拨码并重上电（BOOT_MODE=1）后执行；会写探针Flash：
python -X utf8 toolbox.py probe-flash --out build/qspi-program-new
```

CLI默认使用本目录和受限Zynq辅助器；只接受EF4019、偏移0、低16MiB BOOT，先验证key/头/CRC/保护/bank0，再用标准20h/02h擦写，不整片擦除、不写保护配置。备份保留在输出目录，不公开提交。旧SDK后端为显式 `--backend sdk`，本机其原生库崩溃仍属ZL-167，不能把本后端成功解释为SDK已修复。

构建步骤见 [启动链说明](../../firmware/boot/README.md)。来源基线、实际编译输入/选项、BSP和全部工具身份分别记录在build_manifest与acceptance中。QSPI初始化文件不同于RAM包的JTAG初始化文件，使用时按整套manifest配对。历史Golden/recovery未覆盖；H743/HPM及更高Trace频率没有新增验收。
