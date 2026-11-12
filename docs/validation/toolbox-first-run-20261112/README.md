# CLI 入门流程实测（2026-11-12）

按 [入门手册](../../toolbox-cli-first-run.md) 从主机检查、正式 J7 临时加载、启动源码工作台，走到 H743 烧录、读回校验及复位。两个 PowerShell 终端使用同一仓库。改代码后重开独立 Web 运行目录，客户端命令沿用同一目录。

| 检查 | 实际结果 |
|---|---|
| 主机环境 | Python 3.13.5，安装命令确认依赖齐全，仓库 869 个依赖文件通过哈希核对。 |
| 探针预检 | XC7Z020，`PS_IDCODE=0x23727093`，当时 `BOOT_MODE=0x0`。Trace、调试、DDR、CDMA、RTT、HSS 空闲。 |
| 探针 JTAG 临时加载 | 正式 J7 的 bit SHA-256 为 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF 为 `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802`。FPGA 读到特征字 `0x4450007f` 和包签名 `0x53545232`。物理 MEM-AP0 的 85,844 字节 OCM 执行代码完全匹配。刚加载后按时钟寄存器计算的 FCLK 为 133,333,332 Hz。 |
| 启动工作台 | `serve --j7 --port 0 --open-browser` 实际启动源码服务并打开浏览器，`ping` 返回 `ready: true`。 |
| 固件预览 | `target-flash --prepare-only` 返回 `prepared: true`。用户原 `fw.elf` 的 SHA-256 为 `4a6f6a6a6ed8a3daebff627085b8680a23485f8b30ad70ac8feccd8f0cab3420`，目标 Flash 地址 `0x08000000`，有效载荷 61,208 字节。 |
| 目标身份 | 内置原版 STM32H7 CFG 的 AP2 给出 `DEV_ID=0x450`、`REV_ID=0x2003`，Flash 2 MiB。身份检查保留 Cortex-M 检查事件的延后设置。 |
| 烧录和页面结果 | 已备份当前 Flash，用户确认允许覆盖并结束运行中的 SDRAM 会话。实际源码页面用 OpenOCD Wasm，日志确认 10,000 kHz 配置，MPU 启用时走调试端口直接写入。结果为一扇区、61,208 字节、`verified: true`、`reset: true`。页面显示「读回校验通过」，CLI 可通过原 job ID 查到完成结果。 |
| 独立复核 | 烧前和烧后各双读 2 MiB。两个文件载荷区间分别与 ELF 逐字节一致，区间外 2,035,944 字节保持原值，64 KiB AXI 工作区哈希一致。整片 Flash SHA-256 从 `4fb79dd810f84e360d51cbfd27b95e5437450b73805d51b7b5e8e0722dd4621e` 变为 `840ec9ddcc499edf5438470840b274db759c5c245a40aa177ad41f6e0946d312`。复位后 `DHCSR=0x01010001`，`VTOR=0x08000000`，CFSR 和 HFSR 为零。 |
| 探针 QSPI | 正式 BOOT 包离线校验通过，SHA-256 为 `fd8d0411388767d4ec37aa690b3ae375f7df64c071cd221fd80fa02954dda6bf`。二次只读预检为 `BOOT_MODE=0x0`，引擎及转发空闲。用户选择保留 JTAG 模式，QSPI 写入与断电冷启动留到下次。 |

首轮真实浏览器检查发现文件参数被解包成字节数组，修正为浏览器 `File` 后，预览通过。旧页面的 H743 读身份在本现场返回 `devId: null`。修复复用原版 CFG 的 AP2 和只读命令，未改 Wasm 驱动或原版 CFG，复验返回 `0x450`。对应 ZL-199、ZL-204、ZL-205。

70 项 CLI 测试、159 项 Web 测试、162 个 Web 模块语法检查及共享驱动一致性检查通过。本机保存加载日志、Web 操作结果与完整 Flash 备份于 `build/first-run-*`。源码工作台的本次进程已退出，共享 `hw_server` 保留。
