# zynqlinkPRO

Zynq-7020（xc7z020）上的高性能 **CMSIS-DAP v2 / DAPLink** 固件：
PS 跑 XUsbPs USB + CMSIS-DAP 协议，PL 里做 SWD 批量引擎和 CDMA 数据搬运，
支持 50/60 MHz SWCLK，F103 目标实测读 3.3–3.4 MB/s、写 4.1 MB/s。

- 预编译固件：[`prebuilt/`](prebuilt/)（bit + ELF，JTAG 加载即用）
- 打补丁的 OpenOCD（块读流水线，读 +18%）：[`docs/openocd流水线补丁.md`](docs/openocd流水线补丁.md)

## 直接使用（推荐）

见 [prebuilt/README.md](prebuilt/README.md)。简要步骤：

```powershell
# JTAG 加载 bit + ELF（需要 xsct / Vivado 2018.3）
python tools\run_xsct.py tools\download_dap_fpga.tcl `
    prebuilt\zynqlink_packet.elf prebuilt\zynqlink_packet.bit

# OpenOCD 连接（60 MHz）
openocd -s <openocd>/share/openocd/scripts -f tools/openocd_dap.cfg `
  -c "init" -c "adapter speed 60000" -c "reset halt"
```

> 该固件是 **JTAG RAM 加载**版本：掉电/复位后需要重新加载，不会写 Flash。

## 从源码编译

### 1. 环境

- Vivado / SDK **2018.3**（含 `xsct`、`arm-none-eabi-gcc`）
- Python 3.10+，`pip install pyusb libusb-package pyserial`
- （可选）OpenOCD 0.12 用于测速

### 2. 生成 bitstream

```powershell
python tools\run_vivado.py -mode batch -nojournal -log build\fpga_build.log `
    -source fpga/build_dma.tcl
```

产物：`build/fpga_dma_global/system_wrapper.bit`。

### 3. 生成 BSP 并编译固件

用 Vivado 打开 `build/fpga_dma_global/zynqlink_dma.xpr`，
`File > Export > Export Hardware`（勾选 include bitstream）导出 `.hdf`，然后在 SDK 中
`File > New > Board Support Package` 基于该 hdf 生成 `usb_bsp`；或用 `xsct`：

```tcl
xsct tools/create_bsp.tcl build/system.hdf build/sdk usb_bsp
```

然后编译 ELF（`--bsp` 指向生成的 BSP 目录）：

```powershell
python tools\build_xusbps_daplink.py --project xusbps_daplink_dma --opt 3 `
    --bsp <sdk_workspace>/usb_bsp
```

产物：`build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf`。

### 4. 加载

```powershell
python tools\run_xsct.py tools\download_dap_fpga.tcl `
    build\xusbps_daplink_dma\O3\xusbps_daplink_dma.elf `
    build\fpga_dma_global\system_wrapper.bit
```

## 性能

F103（HCLK=64 MHz）20 KiB SRAM 基准，三会话 ×100 轮，数据与 SRAM 恢复校验通过：

| SWCLK | 读 | 写 |
|---|---:|---:|
| 50 MHz | 2.90 MB/s | 3.48 MB/s |
| 60 MHz | 3.37 MB/s | 4.10 MB/s |

对比：旧 batch 路径 50 MHz 3.05/3.37；HFLink 标称 60 MHz 下载 3.87 MB/s。
读的剩余瓶颈是 USB IN 往返与主机排队，不是 SWD——用流水线 OpenOCD 可到 3.7 MB/s。

## 目录

| 路径 | 内容 |
|---|---|
| `prebuilt/` | 预编译 bit + ELF |
| `fpga/` | RTL（`rtl/`）、BD 脚本、构建脚本、仿真 |
| `firmware/xusbps_daplink_dma/` | PS 固件（CMSIS-DAP v2 + CDC + DMA 批量） |
| `tools/` | 构建、下载、测速、LA 分析脚本 |
| `docs/` | 设计/调试/测试记录 |
| `reference/` | 原始工程与第三方参考（不随仓库发布） |

## 文档

- [RTL TransferBlock 修复与验收](docs/RTLTransferBlock修复与验收.md)
- [RTL 批量与 DMA 优化](docs/RTL批量与DMA优化.md)
- [SWD 采样相位与升频](docs/SWD采样相位与升频优化.md)
- [LA 微时序分析](docs/LA微时序分析.md)
- [RTL 协议层重构计划](docs/RTL协议层重构计划.md)
- [OpenOCD 块读流水线补丁](docs/openocd流水线补丁.md)
- [流水线与块大小实验](docs/流水线与块大小实验.md)
- [LA 使用说明](docs/LA使用说明.md)

## 说明

- 固件通过 JTAG 加载到 OCM/DDR 运行，不修改 Flash；适合开发与测试。
- 目标板测试使用 STM32F103（HCLK 64 MHz）；其它目标请自行验证时序。
- 仓库不含 Xilinx BSP 二进制，需按上面的步骤从导出的 HDF 生成。

