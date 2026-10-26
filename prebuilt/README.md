# 预编译固件（bit + ELF）

直接可用的 Zynq-7020 DAPLink 固件。**仅通过 JTAG 加载到 RAM，不写 Flash**：
掉电或复位后需要重新加载。

| 文件 | 说明 |
|---|---|
| `zynqlink_packet.bit` | PL 比特流（含 SWD 批量引擎、CDMA、命令/响应 BRAM） |
| `zynqlink_packet.elf` | PS 固件（XUsbPs CMSIS-DAP v2 + CDC） |
| `ps7_init.tcl` | PS 时钟/DDR 初始化（加载 ELF 前必须执行） |
| `SHA256SUMS` | 校验值 |

## 当前配对（2026-10-27，codex/main-continuous-scheduler）

包含连续完成握手、读收尾/ACK状态合并、混合Transfer写压缩，以及既有USB/执行引擎恢复。
默认idle≥1，SWCLK上限60MHz；零空闲只允许显式实验构建。FCLK120MHz routed
setup+0.300ns、hold+0.050ns，bitgen/DRC通过。

F103@96MHz，20KiB线性SRAM，新版两段合计每频率20会话：

| SWCLK | OpenOCD读/写 MB/s | 标准CMSIS线性API读/写 MB/s |
|---|---:|---:|
| 50MHz | 3.632 / 3.641 | 3.847 / 3.791 |
| 60MHz | 4.265 / 4.305 | 4.562 / 4.485 |

完整数据及原始SRAM恢复通过。50MHz raw为4.066/4.017MB/s，**线性双向4MB/s目标尚未达成**。
详见[`交接与验收`](../docs/交接-20261027-连续握手与50MHz优化.md)。
`build_manifest.json`记录当前bit/ELF和RTL哈希；`SHA256SUMS`校验当前文件。

## 历史冻结对照配对（2026-10-26）

该冻结 bit/ELF 包含 packet 连续启动/写预取、读响应直接 DMA、USB 队列所有权修复，
以及 core/batch/packet 软复位恢复。固件 SWCLK 上限显式限制为 **60 MHz**。
最终 bit 的 routed FCLK 上限为 138.46 MHz（setup +0.488ns / hold +0.016ns）；
150 MHz setup=-0.068ns，不算通过。下方 main 的 75 MHz 是历史配置。

最后同环境对照，F103@96MHz、20KiB、每配置6会话×300次读写：

| SWCLK | main 读/写 MB/s | 本分支读/写 MB/s |
|---|---:|---:|
| 50MHz | 3.242 / 3.349 | 3.326 / 3.417 |
| 60MHz | 3.765 / 3.958 | 3.899 / 4.068 |

全部数据和 SRAM 恢复校验通过。此前本分支另一组60MHz结果为3.987/4.116，
性能存在主机调度波动，不把高样本当保证值。恢复验证：packet/batch各100轮，
分别74/46次确认引擎忙；最终57,600条队列请求通过。

文件校验见 `SHA256SUMS`，构建信息见 `build_manifest.json`。
完整交接：`docs/交接-20261026-main连续执行与恢复.md`。

关闭 OpenOCD 后可用 `python tools/dap_transport_control.py recover` 恢复USB和执行引擎，
再正常连接目标；stock OpenOCD不会自动发出该请求。历史持续降速尚未稳定复现，
不声称全面解决。更高SWCLK与跨包硬件描述符队列没有作为本轮完成项。

## 版本（2026-10-26 21:09，main `6a628c9`）

包含本轮 SWD 高速化与健壮性修复：

- WAIT/FAULT 后 ACK 被重采的 RTL bug 修复（AP 访问偶发 NO ACK 的根因）；
- 固件把 OpenOCD 的 `idle_cycles=0` 钳到 1（否则 `dap init` 直接 JUNK 失败）；
- `delay_fast` 复位值改为 0（SWCLK = FCLK/2，之前是 FCLK/6，慢 3 倍）；
- USB 响应发送前 DCache flush、USB 会话切换时清空 DAP 队列；
- 删除无效的 `rx_early` 数据采样模式。

综合结果：FCLK 上限 150 MHz（setup +0.148 ns / hold +0.026 ns），
`DAP_MAX_SWCLK_HZ = 75 MHz`。

## 加载

需要 JTAG 探针（Digilent HS3 等）+ Xilinx `xsct`（Vivado/SDK 2018.3 自带）：

```powershell
# 方式 A：xsct 在 PATH 里
xsct tools/download_dap_fpga.tcl prebuilt/zynqlink_packet.elf prebuilt/zynqlink_packet.bit

# 方式 B：用仓库封装（需要 pip install pefile）
python tools\run_xsct.py --sdk E:\Xilinx\SDK\2018.3 tools\download_dap_fpga.tcl `
    prebuilt\zynqlink_packet.elf prebuilt\zynqlink_packet.bit
```

脚本会依次执行 `ps7_init`、`fpga -f`、`dow`、`con`，最后打印 PC。

加载成功后 USB 会出现：

- `VID:PID = 0D28:0204`（CMSIS-DAP v2，bulk 接口）
- 一个 CDC 串口（默认波特率 115200，用于日志）

## OpenOCD

```powershell
openocd -s <openocd>/share/openocd/scripts `
  -f tools/openocd_dap.cfg `
  -c "init" -c "adapter speed 60000" -c "reset halt"
```

`tools/openocd_dap.cfg` 已包含接口与目标配置；速度建议 50/60 MHz（64 MHz 可用，
65 MHz 以上写内存开始失败）。

## 实测（STM32F103CB，HCLK=96 MHz，20 KiB，60 轮）

| SWCLK | OpenOCD | 读 | 写 |
|---|---|---:|---:|
| 60 MHz | 补丁版 | **3.70–3.86 MB/s** | **4.04–4.06 MB/s** |
| 60 MHz | nightly | 3.19 MB/s | 3.99 MB/s |
| 64 MHz | 补丁版 | 3.77 MB/s | 3.88 MB/s |

- 20 KiB 读写逐字节校验通过（`data_match` / `restore_match`）；
- 与历史最好水平（读 3.72 / 写 3.95–4.03）一致；
- 目标固件：`firmware/target/stm32f103_scope`（`build-cb` 为 96 MHz，另有
  60/64/72 MHz 变体）；
- 测速必须用 `--no-reset`：`reset halt` 会把目标停在复位向量，F103 还在
  HSI 8 MHz，吞吐只有约 1.5 MB/s。
