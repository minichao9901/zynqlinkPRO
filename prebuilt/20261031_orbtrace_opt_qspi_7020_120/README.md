# 7020 / 120MHz 优化版 QSPI 启动包

配对为本次优化 RTL + 60MHz-capable 固件，应用继续执行于 OCM，缓冲使用 DDR。后续 ETM 滤波改动未合入。bit/ELF 与已完成 50/60MHz SOTA 复测的文件相同。

| 文件 | SHA-256 |
| --- | --- |
| `probe.bit` | `f02a15db0b576f631c08448b19ea3844d1b45ef00ee6801d243caee398960230` |
| `application.elf` | `4fbf5f7816644ea946a684e1ff3f30425e57eea6e5b64cd0d0d6839f284e6bdb` |
| `BOOT.bin` | `389c0d2cd52f6087aae038dc6bf35acfff0f0d65b74b98949fbdb5deab9525eb` |

BOOT.bin 长度4,264,656字节，实际擦写范围 `[0, 0x412000)`。SDK 编程校验通过；独立整片32MiB回读中，镜像逐字节相等，擦写范围以外数据与原备份相等。原备份 SHA-256 `eba1c30c082caf617f92177e67030ad5c7a0fd567762957f149f19e913413e19`，本机 `E:/zynqlinkPRO_orbtrace_opt/build/qspi_boot/backup/original_flash_32MiB.bin`。

无暂停软件系统复位已经通过：BOOT_MODE=1，stage0/stage2 从 QSPI 加载后记录应用入口0、PS分区存在，USB重新枚举，FCLK读回119,999,998Hz。复位后 SWD60 2KiB/depth32 短测读4.839、写4.746MB/s，数据和SRAM恢复正确。实体按键/断电验证以最终验收记录为准。

PL STA：xc7z020clg400-2，120MHz，WNS +0.499ns / WHS +0.020ns / TNS与THS零。完整资源、时序和OCM布局报告保留在本目录。应用代码71300字节、OCM占用120976字节；没有缩小 USB/DAP 队列。

`build_manifest.json` 记录编译源、构建选项、BSP及加载器哈希，`flash_manifest.json` 绑定本目录实际文件。编译源在 `firmware/boot/`，构建入口 `tools/build_probe_boot.py`。验收日志见 `docs/validation/orbtrace-qspi-20261031/`。

在已集成的总CLI中固化：

```powershell
python -X utf8 toolbox.py probe-flash
# 只检查文件、显示计划，不操作硬件：
python -X utf8 toolbox.py probe-flash --dry-run
# 已固化镜像的回读与复位启动检查，不擦写：
python -X utf8 toolbox.py probe-flash --verify-only
```

可用 `--image-dir` 指定另一已构建的完整启动包；不能只更换一个bit或ELF而继续使用旧BOOT.bin。拨码须为QSPI并已重新上电，连接Zynq的FTDI/JTAG，保持电源稳定。默认命令自动备份整片后固化，输出目录包含原备份和结果；完成后保留QSPI拨码，复位键即可启动。
