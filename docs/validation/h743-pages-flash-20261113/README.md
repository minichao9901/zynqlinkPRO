# H743 在线烧录连接验收

GitHub Pages v1.3.4 使用实际 Chrome WebUSB、内置 STM32H7、SWD 10 MHz 复现。目标在 SDRAM 运行，`VTOR=0xc0318800`、`MPU_CTRL=1`、`DBGMCU_CR=0`。AP2 正确读出 `0x20036450`，AP0 却读到 `CPUID=0xffffffff`，OpenOCD 无法检查 Cortex-M7。页面接着调用 `poll`，只显示 background polling/TAP 状态。命令跟踪确认当时未调用 Flash 探测或擦写。

保留官方 CFG 和 Wasm。按配置里的 Flash 驱动及同一 DAP 的 AP2 检测 STM32H7，在现有 `examine-start` 中先使能并读回 DBGMCU 调试时钟，再执行原检查事件。内核检查状态在轮询前显式核对。内置配置及导入的同类配置复用连接逻辑。只读识别的 MEM-AP 路径仍不执行核心检查。

使用用户截图中的 `E:/superlinkPRO/web/tools/target-firmware/stm32h743_rtt_speed/fw.elf`，SHA-256 为 `d0079519c3644ceab8bf5514980ac5ed30ac38f335a45d8680174d908a99073e`，ELF 的一个 Flash 段覆盖 `0x08000000` 起 1,192 字节。按用户确认，用候选网页的实际烧录按钮经 Chrome WebUSB 以 10 MHz 擦写和校验一个 128 KiB 扇区并复位，页面显示「已烧录 1.2 KB，读回校验通过」。烧录前从零值开始复验 `DBGMCU_CR`。MPU 开启时按原有路径经调试端口编程。

J7 探针处于 QSPI 模式，物理 MEM-AP0 的 85,828 字节 OCM 程序与 `0.7-nonce32` ELF 一致，初始 FCLK 由寄存器推算为 119,999,998 Hz。原始数据、命令记录和 Flash 快照留在本机 `build/h743-pages-*`。

烧前和烧后分别独立双读 2 MiB Flash。烧后 1,192 字节与 ELF 全等，区间外 2,095,960 字节及 64 KiB AXI 工作区与烧前一致。复位后 `VTOR=0x08000000`、`DHCSR=0x01010001`、CFSR/HFSR 为零，目标运行用户指定固件。最终探针队列、采集、DDR、CDMA、RTT、HSS 为空闲。轮询状态误导的旧现象见 ZL-201，本次停在擦写前的内核检查问题登记为 ZL-208。
