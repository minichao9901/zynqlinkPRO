# H743 在线烧录连接验收

GitHub Pages v1.3.4 使用实际 Chrome WebUSB、内置 STM32H7、SWD 10 MHz 复现。目标在 SDRAM 运行，`VTOR=0xc0318800`、`MPU_CTRL=1`、`DBGMCU_CR=0`。AP2 正确读出 `0x20036450`，AP0 却读到 `CPUID=0xffffffff`，OpenOCD 无法检查 Cortex-M7。页面接着调用 `poll`，只显示 background polling/TAP 状态。命令跟踪确认当时未调用 Flash 探测或擦写。

保留官方 CFG 和 Wasm。按配置里的 Flash 驱动及同一 DAP 的 AP2 检测 STM32H7，在现有 `examine-start` 中先使能并读回 DBGMCU 调试时钟，再执行原检查事件。内核检查状态在轮询前显式核对。内置配置及导入的同类配置复用连接逻辑。只读识别的 MEM-AP 路径仍不执行核心检查。

使用用户截图中的 `E:/superlinkPRO/web/tools/target-firmware/stm32h743_rtt_speed/fw.elf`，SHA-256 为 `d0079519c3644ceab8bf5514980ac5ed30ac38f335a45d8680174d908a99073e`，ELF 的一个 Flash 段覆盖 `0x08000000` 起 1,192 字节。按用户确认，用候选网页的实际烧录按钮经 Chrome WebUSB 以 10 MHz 擦写和校验一个 128 KiB 扇区并复位，页面显示「已烧录 1.2 KB，读回校验通过」。烧录前从零值开始复验 `DBGMCU_CR`。MPU 开启时按原有路径经调试端口编程。

J7 探针处于 QSPI 模式，物理 MEM-AP0 的 85,828 字节 OCM 程序与 `0.7-nonce32` ELF 一致，初始 FCLK 由寄存器推算为 119,999,998 Hz。原始数据、命令记录和 Flash 快照留在本机 `build/h743-pages-*`。

烧前和烧后分别独立双读 2 MiB Flash。烧后 1,192 字节与 ELF 全等，区间外 2,095,960 字节及 64 KiB AXI 工作区与烧前一致。复位后 `VTOR=0x08000000`、`DHCSR=0x01010001`、CFSR/HFSR 为零，目标运行用户指定固件。最终探针队列、采集、DDR、CDMA、RTT、HSS 为空闲。轮询状态误导的旧现象见 ZL-201，本次停在擦写前的内核检查问题登记为 ZL-208。

160 项 Web 自测、73 项 CLI 自测及 165 个模块语法检查通过。线上 v1.3.5 的构建时间为 `2026-11-13 14:35:50 UTC`，源码提交 `984fe0af0093db2c0fde41e33b18da895511d6e5`。匿名 Chromium 打开烧录页及版本窗口通过。线上首页、连接修订模块、CFG 导入模块、官方 STM32H7 CFG 和 Wasm 的 SHA-256 与暂存清单一致。实机完整烧录使用发布前同一源码的 WebUSB 页面。[Pages 部署](https://github.com/minichao9901/zynqlinkPRO/actions/runs/43444302102)

## Windows v1.3.5 实板验收

- Windows 包使用与 Pages 相同的源码。冻结预检、F103ZE/H743 离线 Trace 验收及 1,887 个文件的校验通过。固定 EXE 已替换，原有 213 个数据文件的长度、修改时间和 SHA-256 逐项一致。EXE SHA-256 为 `9966c4ea690f4002c1b40d68d06c90700ad5ea6c2b663cb895df1ccb9c7b7cbe`，内置 Web 构建时间为 `2026-11-13 14:44:27 UTC`。
- 由固定 EXE 启动独立验收会话，使用本机 USB 服务、Chrome、内置 STM32H7 和 SWD 10 MHz，载入同一份 `fw.elf`。本轮初始目标已从 Flash 运行，`DBGMCU_CR=0x0070003f`、`MPU_CTRL=0`。记录确认擦写 1 个 128 KiB 扇区、扇区读回校验通过，且仅发送一次 `reset run`。
- 烧前和烧后各对 2 MiB Flash 做两次独立读回。ELF 的 1,192 字节完全一致，区间外 2,095,960 字节、64 KiB AXI 工作区保持烧前内容。整片 Flash SHA-256 为 `e4cdeaf5ff24468578c0dab03e3e8ce57899491e72e21c79390bb2b5ffd7b7bd`。复位后 `VTOR=0x08000000`、`DHCSR=0x01010001`，CFSR、HFSR 为零。J7 QSPI 配对继续使用 `0.7-nonce32`，探针传输及采集退出到空闲。验收进程已结束，共享 `hw_server` 保留。
- GitHub Release v1.3.5 指向 `984fe0af`。上传连接中断后查询同一草稿，确认资产完整并核对服务器 SHA-256 后发布。匿名从 Pages 指向的最新版本链接完整下载 56,195,148 字节，下载文件与发布资产、本地包和 `SHA256SUMS.txt` 的 SHA-256 均为 `e840bd2c08bfd7383dd264c25e7eb6a0b2b0d5aa8c674919a5ddddf380052b47`。[Release v1.3.5](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.5)
