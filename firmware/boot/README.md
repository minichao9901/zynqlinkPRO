> J7 正式启动包固定在 `prebuilt/qspi-release/`，包含 BOOT、配套 bit/ELF 和验收清单。参见[当前镜像及更新流程](../../prebuilt/qspi-release/README.md)。

# Zynq-7020 QSPI 启动，应用保留在 OCM

本目录构建 2018.3 SDK 的 FSBL 和只读 Flash 备份辅助程序，主应用 bit/ELF 没有为固化重新链接到 DDR。USB/DAP 缓冲区仍在 DDR，队列未修改。

SDK 原 FSBL 执行于低 OCM，不能直接让加载到地址零的应用覆盖自己；它还把零入口解释成 JTAG 等待。因此采用 OCM stage0 → DDR stage2 → OCM 应用：stage0 使用匹配的 PS 初始化文件配置 DDR，将完整 stage2 复制到 `0x02000000`；stage2 不重复初始化 DDR，按标准 Bootgen 分区加载 PL 和应用，最后跳到应用 OCM 地址零。加载器保留 DDR `0x02000000..0x021fffff`，构建时检查应用的文件载荷不与它相交；应用自身启动时清零 BSS。引导诊断保留在 `0x03ff0000`。

`vendor_fsbl_2018_3` 与 `vendor_qspips_2018_3` 保留 SDK 的原始许可证。实际补丁由 `tools/build_probe_boot.py` 断言匹配后生成，编译源 SHA-256 记录在构建 manifest。补丁只允许无签名、无加密的低 OCM 应用，限制加载边界；保留其他 SDK 检查。这里没有配置安全启动、密钥或熔丝。

QSPI MIO1..6、单片 x4、反馈时钟关闭（MIO8 供现有 USB PHY 复位）、参考时钟200MHz。DDR/USB/FCLK 保留相应硬件配置。`hardware/system.hdf` 与生成的 `ps7_init.c/h/tcl` 纳入版本管理。它们供启动加载器初始化 PS，FPGA bit 沿用本次已通过 STA/实板的优化产物。

构建（Windows SDK 2018.3；所有输出放独立目录）：

```powershell
python -X utf8 toolbox.py project run boot.bsp -- --out build/qspi-bsp-new
python -X utf8 toolbox.py project run boot.build -- --bsp build/qspi-bsp-new/bsp `
  --bit prebuilt/qspi-release/probe.bit `
  --elf prebuilt/qspi-release/application.elf --out build/qspi-loader-new
python -X utf8 toolbox.py project run boot.package -- `
  --loader-dir build/qspi-loader-new --bit prebuilt/qspi-release/probe.bit `
  --elf prebuilt/qspi-release/application.elf `
  --ps-init firmware/boot/hardware/ps7_init.tcl --output-dir build/qspi-package-new
python -X utf8 toolbox.py probe-flash --image-dir build/qspi-package-new --dry-run
# 以下会写探针QSPI；先确认独占板卡且BOOT_MODE=1：
python -X utf8 toolbox.py probe-flash --image-dir build/qspi-package-new --out build/qspi-program-new
```

编译使用 `-Os`、函数/数据分节、GC，固定 FSBL 构建时间字符串。输出 stage0/stage2/programmer ELF、只读 `qspi_read.elf`、Bootgen BIF/BOOT.bin、分区/MD5 检查、来源哈希和链接 map。`fsbl_programmer.elf` 强制加载器采用 JTAG 分支，供真实启动拨码已经是 QSPI 的板子使用 `program_flash`。

只读辅助程序在 DDR `0x03000000`，输出缓冲 `0x04000000`，邮箱 `0x03ff0000`。目前验证的 Flash 为 JEDEC EF4019 / Winbond 32MiB，采用专用13h四字节地址读命令，不改变 Flash 地址模式，也不发写使能、擦除或编程命令。SDK 对未知操作码的通用 RX 对齐路径不适用此五字节头，构建时给备份程序私有驱动增加13h表项；读回经真实 BootROM 头、整片备份/回读及镜像 SHA-256 验证。FIFO 缓冲含完整字填充空间。

固化由 `tools/probe_flash.py` 负责：输入包哈希核对、芯片/拨码/Flash 型号检查、整片原备份、SDK 擦除检查与编程校验、整片独立回读、擦写范围外比对、无暂停系统复位及 OCM 应用交接诊断。先复位 CPU0 再加载 ARM 备份程序，避免此前 Thumb 应用的 CPSR/MMU 状态污染。SDK `rst -system` 自带 suspend=1，自动验证使用同一 XilinxReset 服务的 suspend=0，不需要调试器随后 `con`。

只有实际加载测试通过的启动包才标为已验收。断电/实体按键检查结果、边界和 SHA-256 见对应 `prebuilt/` 启动包及 `docs/validation/orbtrace-qspi-20261031/`。原 Flash 备份在本机 build 目录，不纳入公开 Git。

## 受限写入后端

默认CLI后端是 `qspi_program.elf`，限JEDEC EF4019、BOOT偏移0和低16MiB。写使能前验证显式arm key、BOOT头、长度、DDR镜像CRC32和保护状态；退出4字节模式后读取扩展地址寄存器，只有bank0才使用标准20h/02h擦写，不写状态寄存器、不整片擦除。每扇区擦除后全量blank-check，每页编程后读回；busy轮询及主机等待均有上界。只读13h路径不依赖当前地址模式。

主机仍先备份整片32MiB，最后重新加载独立只读helper整片回读，核对BOOT SHA和擦写范围外所有字节，再做无暂停QSPI复位启动。备份仅保存在本机输出目录，不公开提交。C模型覆盖错误key/器件/长度/头/CRC、保护与bank拒绝、256B与4KiB边界、busy超时和读回错误；模型通过不能代替板测。

旧SDK后端用 `--backend sdk` 显式选择；SDK 2018.3的本机原生写入库崩溃仍为ZL-167待定位。构建端的 `sdk_runtime.py` 仅复制SDK运行库到隔离目录，不修改SDK或系统安装。HSI生成后检查输出、串行make后检查QSPI头文件及库，Bootgen检查实际BOOT存在，避免旧bat静默成功。
