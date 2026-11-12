# H743 工作台烧录续验（ZL-199）

2026-11-12（本地时间），复核隔离候选 `c6657f24`，烧录修复提交为 `b9020e94`。候选 OpenOCD Wasm SHA-256 为 `d8017a5f31244efbc776cf7b24f1992e95aeb19aa5e9e95f86ce814146a3daf0`。

原截图的 `fw.elf` 已在 H743 Trace 工程的 `firmware/cpu60/LwIP_TCP_Echo_Client/fw.elf` 找到。完整 SHA-256 为 `4a6f6a6a6ed8a3daebff627085b8680a23485f8b30ad70ac8feccd8f0cab3420`。工作台解析得到一个区间，起始地址 `0x08000000`，61,208 字节。候选 `node --test web/tools/selftest/openocd-wasm.test.mjs` 通过 10/10。

| 检查 | 本次结果 |
| --- | --- |
| Windows PnP | `0D28:0204` 的 CMSIS-DAP WinUSB 和 HID 接口已枚举 |
| `tools/dap_transport_control.py state` | libusb 看见 WinUSB 接口，但设备初始化失败，随后返回 `DAP not found` |
| `tools/probe_stream.py status --service hss` | hidapi 返回零个可用探针 |
| 候选 `toolbox.py serve` | 当前进程完整性 RID 为 4096，绑定本机 8878 端口失败，`WinError 10013` |
| `tools/verify_probe_ocm_code.py` | Xilinx `hw_server` 绑定失败，未能独立读取本次板上 OCM 或时钟 |

验收停在主机访问预检。未读本次 H743 DEV_ID，未访问目标 Flash、擦写或复位，也未重载探针。待正常桌面会话可打开探针后，确认采集和 DMA 空闲及板上配对，备份目标 Flash，使用同一 ELF 和内置 STM32H7/SWD 10 MHz 路径擦写及读回，并核对原 Flash 恢复和目标运行状态。ZL-199 仍为烧录修复待板验。

## 07:42 后的桌面续验

当前会话 Windows 完整性 RID 为 `12288`，WinUSB、HID、本机 HTTP 及既有 Xilinx `hw_server` 均可访问。通过物理 MEM-AP0 核对在线 Zynq OCM 的 85,844 字节执行段与正式 J7 ELF 一致。在线 ELD1/DDR 特征与上次正式配对记录吻合。本轮未下载 bit/ELF，bit 身份沿用上次加载记录。

| 项目 | 本轮读回 |
| --- | --- |
| J7 bit 文件 SHA-256 | `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6` |
| Zynq ELF 文件 SHA-256 | `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802` |
| 烧录中 FCLK / SWCLK | 119,999,998 Hz / 9,999,999.83 Hz，物理寄存器读回推算 |
| 探针初始状态 | DAP 队列空，采集、DDR、CDMA、RTT、HSS 空闲 |
| H743 初始状态 | `DPIDR=0x6ba02477`，`CPUID=0x411fc271`，`DBGMCU_IDCODE=0x20036450`，`DBGMCU_CR=0`，`DHCSR=0x00030003`，暂停于外部 SDRAM 的 SVCall |

以独立 DAP 路径连续两次读回完整 2 MiB Flash，确认一致后才进入工作台。经 `c6657f24` 实际浏览器页面、本机鉴权 USB、内置 STM32H7、SWD 10 MHz，选择原 `fw.elf` 并勾选读回校验。取消烧录后复位以保留外部 SDRAM 现场。AP2 正确识别 `0x20036450`，Flash 探测通过，进入首个 128 KiB 扇区的擦写。此前的 `Cannot identify target as a STM32H7xx family` 未出现。

首轮实际写入失败。OpenOCD 先报 `timeout waiting for algorithm`，随后报 `flash memory write protected`，打印的状态 `0x2406006c` 落在 AXI 工作区。独立读回确认变化限于 ELF 覆盖范围，ELF 未完整写入。现场 `MPU_CTRL=1`，`CFSR=0x1`，`HFSR=0x40000000`，HardFault 栈中的故障 PC 为算法入口 `0x24060000`，叠栈前异常号为 SVCall。证据指向运行中的 MPU 策略拒绝工作区取指，Flash 写保护字样出现在算法超时之后。[Cortex-M7 故障寄存器定义](https://documentation-service.arm.com/static/61efd6602dd99944d051417b)

以同一 Web 路径回写原首扇区 BIN，26.982 秒完成 131,072 字节写入和扇区校验，保持复位关闭。随后独立连续两次读回 2 MiB，均恢复到原 SHA-256 `077331beb888de9366761c11edacb0d0b805f00ac1cb394429c3a15bd3601631`。64 KiB 工作区、RCC、VTOR、CCR、DEMCR、FPB、DWT 和 `DBGMCU_CR=0` 均与测试前读回一致。工作台回写后 CPU 仍暂停，20 个核心寄存器和一页 SDRAM 栈与原现场存在差异。两次无复位异常返回尝试均未恢复原 SVCall，随后调试寄存器回写也未能重建 IPSR。探针之后从 Windows PnP 枚举消失，最后能确认的是 Flash 已恢复、CPU 已暂停，原应用暂停现场未完整恢复。本轮未主动复位目标、改目标时钟或写探针 QSPI。

ZL-200 的候选在擦除前读取 H7 MPU 状态。启用 MPU 时将当前 OpenOCD 会话的 Flash 工作区大小设为 0 并读回确认，由 `stm32h7x` 经调试端口直接写入。关闭 MPU 时继续走原 64 KiB 工作区路径和独立备份校验。专项覆盖短 MPU 回读、工作区禁用未确认、成功和失败后的工作区恢复。实际 Wasm 通过模拟 CMSIS-DAP 在工作区大小为 0 时写入并读回一个 32 字节 Flash 字，核对 AXI 工作区无写入。10 项 Wasm、159 项 Web、65 项 CLI 及共享驱动一致性通过。候选完整实板擦写仍待复测。

原 Flash、SRAM 备份和逐阶段日志保存在本机 `build/h743-web-flash-accept-20261112/`。该目录的原始数据和工作台令牌未纳入 Git。

探针 USB 于 07:57:43 从 Windows 移除，同一集线器的 4 号端口在 07:58:05 出现“设备描述符请求失败”（问题码 43）。仅重启该设备实例后错误复现。首次只读 JTAG 检查遇到 PL 隔离或复位状态并停止 AXI 读取。之后物理 OCM 仍与正式 ELF 匹配，FCLK 读回约 50 MHz，PL 特征寄存器读取超时。状态变化原因及当前目标状态待核实。本任务网页、工作台服务和 JTAG 客户端已退出，共享 `hw_server` 保留。

## Windows 候选包

| 工作台 | 候选身份与验证 |
| --- | --- |
| ZynqLink | 源码 `bf7ab89d`，EXE SHA-256 `b039b23ae82c70f4a7f371790c4af724cd2e4a0e2030c5803d266e85950c9a35`。冻结进程 RID `8192`，1,817 个文件校验及 F103ZE/H743 离线记录解码、索引、查询和导出通过。候选目录 `build/h743-web-flash-accept-20261112/zynq-candidate/`。 |
| SuperlinkPRO web.13 | 隔离源码 `a513f848`，EXE SHA-256 `f7dfec4f6f8d3f95af96d19eea869549b87fede59e46e816aaec06386433aae3`。首次冻结验收缺 `etm/tools/node-transport` 的锁定依赖，补齐后重建，3,414 个文件校验、冻结服务及 CLI、离线解码导出和下载校验通过。候选目录 `build/h743-release-20261111/super-source/web/tmp/etm-package-37bb84ce/dist/superlinkPRO/`。 |

两套候选均使用本报告所列 Wasm。固定安装目录等待实板复测，GitHub Pages 未发布。

## 15:20 USB 恢复后的完整烧录

重新枚举 CMSIS-DAP WinUSB、HID 和 CDC 后，物理 OCM 85,844 字节再次与正式 J7 ELF 一致，PL 的 ELD1/DDR 特征吻合。探针队列、采集、DDR、CDMA、RTT 和 HSS 均空闲。SWD 10 MHz 烧录期间读回 FCLK 119,999,998 Hz、SWCLK 9,999,999.83 Hz。

目标恢复为运行中的 SDRAM 应用，`MPU_CTRL=1`，`DBGMCU_CR=0x0070003f`。两次独立 2 MiB Flash 备份一致，SHA-256 为 `077331beb888de9366761c11edacb0d0b805f00ac1cb394429c3a15bd3601631`。冻结候选经实际工作台进入 AP2 识别和 MPU 直接烧录路径，使用原 `fw.elf` 及默认「校验」和「烧录后复位运行」选项。复位后独立读回两个 `PT_LOAD` 文件区间（61,056 和 152 字节），共 61,208 字节全相等。区间外 2,035,944 字节与备份相等。64 KiB AXI 工作区哈希一致，Flash 整片 SHA-256 为 `d8ceb22dafabac56f74014eb60fc9a038315d556a003d8d54ee9b724a661231e`。

旧候选在复位后的首次 `poll` 返回失败，页面未报告成功（ZL-201）。独立读回确认 VTOR 已指向新固件 `0x08000000`，核心运行且未锁死，CFSR/HFSR 为零。修订后的 H7 路径在单次复位命令后直接读 DHCSR，短暂读失败时限时重读，拒绝零值、锁死或状态不符。模拟测试覆盖首次读失败、零值及锁死后再读成功，并确认复位仅发一次。

修订后的实际 ZynqLink 工作台再次用原 ELF 完成擦写、扇区读回校验和复位，约 80.166 秒，页面显示“已烧录 59.8 KB，读回校验通过”。两次独立 2 MiB 读回再次确认全部 ELF 字节、覆盖范围外及 64 KiB 工作区一致。最终 `DHCSR=0x01010001`，`VTOR=0x08000000`，CFSR/HFSR 为零，`DBGMCU_CR=0x0070003f`。按用户要求保留原 `fw.elf` 在目标上运行，目标时钟由该固件启动配置决定。最终探针采集、DDR、CDMA、RTT 和 HSS 空闲。

## 日常 Windows 工作台更新

| 工作台 | 本机更新与验收 |
| --- | --- |
| ZynqLink v1.3.1 | 源码 `8e653631`，日常 EXE SHA-256 `ef97581734de9703ae6d3871562652b0507d7d2418870218b3f8e25fb115fa88`。冻结包 1,817 个文件及 F103ZE/H743 解码、索引、查询和导出通过，安装后预检通过。原 `data` 114 个文件逐字节哈希一致，旧程序归档。Windows ZIP SHA-256 `fb45ed886deda5ed07e94b43921521590021675a6c03d5abe460a6855b295fb2`。 |
| SuperlinkPRO 1.1.0-web.13 | 源码 `31af88de`，日常 EXE SHA-256 `b3fe01b302bafdc5225c29a3a0d34a44d79f9b39ed76ecd90190a70c5ed40f6c`。冻结候选及安装后 CLI、HTTP、离线解码和下载检查通过。原 `data` 66 个文件逐字节哈希一致，旧程序归档。Windows ZIP SHA-256 `6b309cf0028ea3657ab27009ea61056284892b78486eec5481d83aae44de615f`。 |

两套日常包均含 AP2 识别及复位后直接读 DHCSR 的确认逻辑。H743 真机擦写使用 ZynqLink，SuperlinkPRO 覆盖共享修订的定向回归和冻结包验证。板验后的本任务工作台进程均已退出，既有 `hw_server` 继续运行。

## GitHub 与 Pages

- ZynqLink 的 `main` 已推送板验提交 `6970dfca`。Pages 已构建静态分支 `bfe0685`，公开站点 manifest 对应 `8e653631`。GitHub v1.3.1 是最新 Release，ZIP 56,108,523 字节，公开资产 SHA-256 与本机包一致。[Pages](https://minichao9901.github.io/zynqlinkPRO/) · [Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.1)
- SuperlinkPRO 的 `main` 已推送 `c9bca36c`，Pages Actions 部署成功。公开下载 manifest 为 `1.1.0-web.13`，源提交、ZIP 字节数和 SHA-256 与本机分发包一致。[Pages](https://minichao9901.github.io/superlinkPRO/) · [部署记录](https://github.com/minichao9901/superlinkPRO/actions/runs/43177323045)
- 两个公开下载端点均返回 HTTP 206，首 4,096 字节与各自本机 ZIP 一致，`Content-Range` 声明的总长度分别为 56,108,523 和 103,222,601 字节。
- GitHub 推送首轮返回 HTTP 408，改用 HTTP/1.1 和缓冲发送后成功。Zynq ZIP 的流式重试遇到连接重置，之后由仓库发布器在同一草稿内完成限速上传，按远端资产 SHA-256 和大小核对后发布。失败证据保留于本轮本机目录（ZL-164）。

## OpenOCD 原版 CFG 对照与内置列表迁移

2026-11-12 续验同一 H743、正式 J7 探针和原 `fw.elf`。探针在线 85,844 字节 OCM 执行段与前文配对一致，ELD1、DDR 特征吻合。实测配置读回 FCLK 119,999,998 Hz、SWCLK 9,999,999.83 Hz。目标开始运行上次写入的应用，`VTOR=0x08000000`、`MPU_CTRL=5`。首轮对照前经 AP2 将 `DBGMCU_CR` 暂置零，以复现旧失败中关键的调试时钟初值。上次暂停在 SDRAM 应用的完整现场不属于本轮覆盖范围。

从 OpenOCD `9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a` 提取原版 `target/stm32h7x.cfg`，SHA-256 `d42bb124e23066b16a8145800ef22f8ed28ea0dff638563b84e3e5c8a76f45ec`。依赖同版本 `target/swj-dp.tcl`、`mem_helper.tcl`。对照入口只选 CMSIS-DAP/SWD、设置 `DUAL_BANK=1` 并在原脚本后选 10 MHz。Wasm 从 `aa5372c4` 取成对 `.mjs/.wasm`，Wasm SHA-256 `1977164ce62a8595753be9dfa741751c0b3f2459a95aa6bd03f25afe72d554fe`，`stm32h7x` 驱动未加 AP2 读 ID 补丁。上游 CFG 仍通过 AP2 初始化 `DBGMCU`。[OpenOCD 原版配置](https://github.com/openocd-org/openocd/blob/9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a/tcl/target/stm32h7x.cfg)

| 入口 | 结果 |
| --- | --- |
| 调试器导入 CFG → 烧录器沿用目标 | 88.463 秒。成功识别、擦写首个 128 KiB 扇区并校验原 ELF 的 61,208 字节。运行中的 MPU 启用，工作台走现有直接写入保护路径。本轮复位关闭，独立读回后复核并恢复 CFG 涉及的调试时钟、看门狗冻结、Trace Funnel 和目标运行状态。 |
| 烧录器内置 STM32H7 | 76.767 秒。使用上游 `stm32h7x_dual_bank.cfg` 加载同一原版 `stm32h7x.cfg`，同一未加补丁的 Wasm。烧录、校验及复位运行均通过，`DHCSR=0x01010001`，`VTOR=0x08000000`，CFSR/HFSR 为零。 |

两轮完整 2 MiB 独立双读均与本轮烧录前一致（原 ELF 已在目标上运行），分别核对两个 `PT_LOAD` 共 61,208 字节及区间外 2,035,944 字节。整片 SHA-256 `d8ceb22dafabac56f74014eb60fc9a038315d556a003d8d54ee9b724a661231e`。最终探针采集、DDR、CDMA、RTT、HSS 空闲。本轮 Flash 修改限定上述目标扇区，使用已有 bit/ELF 配对，未写 QSPI。

ZynqLink 烧录器内置列表现从同版本上游选取 29 个原版 target/board CFG，按同一导入函数解析。板级 CFG 的 HPM FTDI 适配器引用由加载器绑定到原版 CMSIS-DAP 接口脚本，板级文件及其 Flash 参数保留原样。固定上游版本没有 HPM6P00EVK 对应 CFG，移出烧录器内置列表，匹配的外部 CFG 仍可导入。F2/F3/F4/F7 原版 CFG 在 Flash 探测前的基址可为零，烧录器现在先读实测几何再映射 ELF。29 个条目均通过实际 Wasm 离线配置加载，H743 为本轮实板验收对象。原始 Flash/日志留在本机 `build/h743-upstream-cfg-20261112/`。

源码 `bcd87ad8` 的 159 项 Web、65 项 CLI、共享驱动一致性及冻结 EXE 离线回归通过。45 份 CFG/Tcl 文件与固定上游提交逐字节一致，Pages 暂存及冻结 EXE 的 HTTP 读回均完整匹配。候选 EXE SHA-256 `d0288906249ea0e613e039c1f42cfe452e6835e9c16cd6482ce5b3e968aaaf82`，位于 `build/h743-upstream-cfg-20261112/package-source/dist/zynq-etm-bridge/`。本轮源码与候选已就绪，固定 EXE 和线上 Pages 仍为上次正式版。任务测试服务已退出，共享 `hw_server` 保留。
