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
