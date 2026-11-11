# H743 变量显示、编辑与 p/x 实板验收

2026-11-11（北京时间）。zynqlinkPRO 源码工作台在隔离 Edge 中运行，通过鉴权本机 USB 服务使用实际探针，调试后端为正式 OpenOCD Wasm。H743 的 CPUID 为 `0x411fc271`，设备 ID 为 `0x20036450`，SWD DPIDR 为 `0x6ba02477`。实板通过以下三项，范围为暂停目标的 32 位无符号标量。[证据](evidence.json)

| 项目 | 页面及实板结果 |
| --- | --- |
| 变量格式 | `accept_watch_u32` 初始为 `42`，切至 Hex 显示 `0x0000002a`，写入后切回十进制显示 `305419896`。 |
| 修改与回读 | 在变量表双击数值，键入 `0x12345678` 并按 Enter。页面更新为 `0x12345678`，同会话另读四字节得到 `78 56 34 12`。变量前后相邻字节全部一致。再次经编辑器写入 `42` 并读回 `2a 00 00 00`。 |
| `p/x` | 变量表保持十进制时，`p accept_watch_u32` 输出 `305419896`，`p/x accept_watch_u32` 输出 `0x12345678`。 |

## 配对与准备

接续时已恢复 APU 访问。按正式入口从 JTAG 加载 RAM 配对，加载前的故障保留在[先前记录](../watch-edit-wasm-promotion-20261110/README.md#2026-11-11-h743-实板补验准备)。本次 bit 为 `prebuilt/release-20261106/probe.bit`，SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`。PS ELF 为同目录 `application.elf`，SHA-256 `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802`。开始和结束均以 Zynq 物理 MEM-AP0 独立对拍 85,844 字节执行段。Wasm SHA-256 为 `1977164ce62a8595753be9dfa741751c0b3f2459a95aa6bd03f25afe72d554fe`。实际 FCLK 为 119,999,998 Hz，SWD 分频回读为 `0x000caa11`，计算 SWCLK 为 9,999,999.833 Hz。频率来自寄存器读回与计算。

目标 `DBGMCU_CR` 原值为 0，初期通过 SWD AP0 的直接读以及 Wasm MEM-AP 读出现 0 或上一次数据，1 MHz 与 10 MHz 下均有异常。JTAG 探测未读到有效 TAP ID。本轮用 SWD AP2 的 `0xe00e1000` 稳定确认 H743 设备 ID，在同一端口备份 `DBGMCU_CR` 后临时置为 `0x00600007`，再确认 CPUID、暂停和内存可读。AP0 的 `0x5c001000` 别名仍可能读 0，身份以 AP2 为准。默认工作台接管低功耗现场的行为仍待复核，见 ZL-199。[OpenOCD H7 配置](https://github.com/openocd-org/openocd/blob/master/tcl/target/stm32h7x.cfg)

本次使用临时数据 ELF 提供三个 SRAM 类型符号。目标暂停后 PC 为 `0xc000b6c6`。写入夹具前两次核对并备份 `0x24060000` 起的 32 字节窗口，保留 20 个核心寄存器、时钟和调试配置快照，读取完整 2 MiB Flash 的 SHA-256。夹具初始化共 12 字节，测试变量位于 `0x24060004`，两侧为可核对的保护字。数据 ELF 仅用于页面符号与类型解析。

## 恢复和清理

退出页面连接后，以独立 CMSIS-DAP 路径回写原 32 字节窗口并逐字节复读，备份及恢复后 SHA-256 均为 `cd7681366c456b8c46feadba23ba71e79be16c01c5c0fb3117082be41143153c`。20 个核心寄存器、RCC、Flash ACR、DEMCR、CCR、VTOR、FPB 控制及八个比较器一致，CFSR/HFSR 均为 0。完整 2 MiB Flash 的前后 SHA-256 均为 `077331beb888de9366761c11edacb0d0b805f00ac1cb394429c3a15bd3601631`。

H743 恢复运行且 `C_DEBUGEN=0`，恢复运行后读到 `DHCSR=0x00010000`，随后由 AP2 写回并确认 `DBGMCU_CR=0`。探针保留本次加载的正式 RAM 配对，DDR 捕获未活动，DAP 待处理请求、响应和 USB 发送均为 0。硬件写入限于探针 RAM 配对加载及 H743 的临时 SRAM 和调试控制，目标 Flash 和探针 QSPI 的写入次数均为 0。

脚本、ELF、浏览器配置、临时运行时、备份与原始日志全部位于同一个系统临时目录。恢复验证后将该目录的 2,162 个文件、217,472,559 字节移入回收站，确认原路径不存在，本任务服务、浏览器和 hw_server 均退出。仓库仅归档本报告、精简证据和问题索引。ZL-198 的 H743 标量范围已验收。
