# 预编译固件（bit + ELF）

直接可用的 Zynq-7020 DAPLink 固件。**仅通过 JTAG 加载到 RAM，不写 Flash**：
掉电或复位后需要重新加载。

| 文件 | 说明 |
|---|---|
| `zynqlink_packet.bit` | PL 比特流（含 SWD 批量引擎、CDMA、命令/响应 BRAM） |
| `zynqlink_packet.elf` | PS 固件（XUsbPs CMSIS-DAP v2 + CDC） |
| `SHA256SUMS` | 校验值 |

## 加载

需要 JTAG 探针（Digilent HS3 等）+ Xilinx `xsct`（Vivado/SDK 2018.3 自带）：

```powershell
python tools\run_xsct.py tools\download_dap_fpga.tcl `
    prebuilt\zynqlink_packet.elf prebuilt\zynqlink_packet.bit
```

或者直接用 xsct：

```tcl
connect
targets -set -filter {name =~ "APU"}
rst -system
fpga -file prebuilt/zynqlink_packet.bit
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
dow prebuilt/zynqlink_packet.elf
con
```

加载成功后 USB 会出现：

- `VID:PID = 0D28:0204`（CMSIS-DAP v2，bulk 接口）
- 一个 CDC 串口（默认波特率 115200，用于日志）

## OpenOCD

```powershell
openocd -s <openocd>/share/openocd/scripts `
  -f tools/openocd_dap.cfg `
  -c "init" -c "adapter speed 60000" -c "reset halt"
```

`tools/openocd_dap.cfg` 已包含接口与目标配置；速度建议 50/60 MHz。

## 实测（F103 目标，HCLK=64 MHz，20 KiB）

| SWCLK | 读 | 写 |
|---|---:|---:|
| 50 MHz | 2.9 MB/s | 3.5 MB/s |
| 60 MHz | 3.3–3.4 MB/s | 4.1 MB/s |

配合打了流水线补丁的 OpenOCD（`docs/openocd流水线补丁.md`），60 MHz 读可到 3.7 MB/s。
