# Zynq-7020 QSPI 启动，应用保留在 OCM

本目录构建 2018.3 SDK 的 FSBL 和只读 Flash 备份辅助程序，主应用 bit/ELF 没有为固化重新链接到 DDR。USB/DAP 缓冲区仍在 DDR，队列未修改。

SDK 原 FSBL 执行于低 OCM，不能直接让加载到地址零的应用覆盖自己；它还把零入口解释成 JTAG 等待。因此采用 OCM stage0 → DDR stage2 → OCM 应用：stage0 使用匹配的 PS 初始化文件配置 DDR，将完整 stage2 复制到 `0x02000000`；stage2 不重复初始化 DDR，按标准 Bootgen 分区加载 PL 和应用，最后跳到应用 OCM 地址零。加载器保留 DDR `0x02000000..0x021fffff`，构建时检查应用的文件载荷不与它相交；应用自身启动时清零 BSS。引导诊断保留在 `0x03ff0000`。

`vendor_fsbl_2018_3` 与 `vendor_qspips_2018_3` 保留 SDK 的原始许可证。实际补丁由 `tools/build_probe_boot.py` 断言匹配后生成，编译源 SHA-256 记录在构建 manifest。补丁只允许无签名、无加密的低 OCM 应用，限制加载边界；保留其他 SDK 检查。这里没有配置安全启动、密钥或熔丝。

QSPI MIO1..6、单片 x4、反馈时钟关闭（MIO8 供现有 USB PHY 复位）、参考时钟200MHz。DDR/USB/FCLK 保留相应硬件配置。`hardware/system.hdf` 与生成的 `ps7_init.c/h/tcl` 纳入版本管理。它们供启动加载器初始化 PS，FPGA bit 沿用本次已通过 STA/实板的优化产物。

构建（Windows SDK 2018.3；所有输出放独立 worktree）：

```powershell
E:/Xilinx/SDK/2018.3/bin/hsi.bat firmware/boot/hardware/generate_bsp.tcl build/qspi_boot/bsp
# 将 SDK GCC 与 gnuwin/bin 加入 PATH，RDI_PLATFORM=win64；BSP 必须串行构建：
make -C build/qspi_boot/bsp -j1
python tools/build_probe_boot.py --bsp build/qspi_boot/bsp `
  --bit prebuilt/20261031_orbtrace_opt_7020_120_candidate/zynqlink_probe.bit `
  --elf prebuilt/20261031_orbtrace_opt_7020_120_candidate/zynqlink_probe_60.elf
```

编译使用 `-Os`、函数/数据分节、GC，固定 FSBL 构建时间字符串。输出 stage0/stage2/programmer ELF、只读 `qspi_read.elf`、Bootgen BIF/BOOT.bin、分区/MD5 检查、来源哈希和链接 map。`fsbl_programmer.elf` 强制加载器采用 JTAG 分支，供真实启动拨码已经是 QSPI 的板子使用 `program_flash`。

只读辅助程序在 DDR `0x03000000`，输出缓冲 `0x04000000`，邮箱 `0x03ff0000`。目前验证的 Flash 为 JEDEC EF4019 / Winbond 32MiB，采用专用13h四字节地址读命令，不改变 Flash 地址模式，也不发写使能、擦除或编程命令。SDK 对未知操作码的通用 RX 对齐路径不适用此五字节头，构建时给备份程序私有驱动增加13h表项；读回经真实 BootROM 头、整片备份/回读及镜像 SHA-256 验证。FIFO 缓冲含完整字填充空间。

固化由 `tools/probe_flash.py` 负责：输入包哈希核对、芯片/拨码/Flash 型号检查、整片原备份、SDK 擦除检查与编程校验、整片独立回读、擦写范围外比对、无暂停系统复位及 OCM 应用交接诊断。先复位 CPU0 再加载 ARM 备份程序，避免此前 Thumb 应用的 CPSR/MMU 状态污染。SDK `rst -system` 自带 suspend=1，自动验证使用同一 XilinxReset 服务的 suspend=0，不需要调试器随后 `con`。

只有实际加载测试通过的启动包才标为已验收。断电/实体按键检查结果、边界和 SHA-256 见对应 `prebuilt/` 启动包及 `docs/validation/orbtrace-qspi-20261031/`。原 Flash 备份在本机 build 目录，不纳入公开 Git。
