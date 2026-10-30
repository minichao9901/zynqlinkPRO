# zynqlinkPRO

本轮 ZynqDAP + F103ZE 的 Web/CLI、TRACECLK、软件滤波、RTT/J-Scope 与压力验收，统一见
[F103ZE Web CLI ETM验收记录](docs/F103ZE-Web-CLI-ETM统一验收-20261031.md)。
当前ETM加载配对见[`prebuilt/20261031_filtered_tpiu/`](prebuilt/20261031_filtered_tpiu/)，
统一命令入口为[`toolbox.py`](toolbox.py)，用法见[CLI手册](docs/toolbox-cli-ai.md)。

Zynq-7020（xc7z020）上的高性能 **CMSIS-DAP v2 / DAPLink** 固件：
PS 跑 XUsbPs USB + CMSIS-DAP 协议，PL 里做 SWD 批量引擎和 CDMA 数据搬运，
支持50/60MHz SWCLK；F103@96MHz的20KiB OpenOCD读/写实测为
50MHz下3.632/3.641MB/s、60MHz下4.265/4.305MB/s。

- 预编译固件：[`prebuilt/`](prebuilt/)（bit + ELF，JTAG 加载即用）
- 最新验收：[`连续握手与50MHz优化`](docs/交接-20261027-连续握手与50MHz优化.md)
- 打补丁的 OpenOCD（块读流水线，读 +18%）：[`docs/openocd流水线补丁.md`](docs/openocd流水线补丁.md)

网页工作台：[`web/README.md`](web/README.md)（从 superlinkPRO 页面拷贝并删掉 SPI/QSPI、SPI 转发、SWO、I2C、ADC/DAC），
ETM 执行轨迹页直接 iframe superlinkPRO 原始 ETM 工作台，由 [`etm-service`](etm-service/README.md) 提供 Zynq 采集和 OpenCSD 解码，
操作见 [`Zynq-ETM-Trace 操作说明`](docs/Zynq-ETM-Trace操作说明.md)。

ETM 命令行：[`trace.cmd`](trace.cmd) / [`etm-service/trace.py`](etm-service/trace.py)，用法与限制见
[`Trace CLI 使用说明`](docs/Trace-CLI使用说明.md)。

全部 Web 功能的统一 CLI：`python -X utf8 toolbox.py --help`；启动、命令表及
串口/调试/RTT/J-Scope/烧录/ETM流程见 [Web CLI 使用说明](docs/toolbox-cli-ai.md)。

ORBTrace/并行 ETM 背景：[`并行 ETM 与 PS USB`](docs/orbtrace-usb.md)、[`LUT 资源分析`](docs/orbtrace-area-native32.md)。
后续优化见 [`资源与性能合并方案`](docs/探针资源与性能优化方案-20261030.md)。
本次实验配对在 [`prebuilt/20261030_orbtrace_native32/`](prebuilt/20261030_orbtrace_native32/)，
FCLK 100 MHz / 调试时钟上限 50 MHz，19,228 LUT；已生成并通过现有约束 STA，尚待实板验收。

## 直接使用（推荐）

见 [prebuilt/README.md](prebuilt/README.md)。简要步骤：

```powershell
# 方式 A：xsct 在 PATH 里（Vivado/SDK 2018.3 自带）
xsct tools\download_dap_fpga.tcl prebuilt\zynqlink_packet.elf prebuilt\zynqlink_packet.bit

# 方式 B：用仓库封装（需要 pip install pefile；--sdk 指向本机 SDK）
python tools\run_xsct.py --sdk E:\Xilinx\SDK\2018.3 tools\download_dap_fpga.tcl `
    prebuilt\zynqlink_packet.elf prebuilt\zynqlink_packet.bit

# OpenOCD 连接（60 MHz）
openocd -s <openocd>/share/openocd/scripts -f tools/openocd_dap.cfg `
  -c "init" -c "adapter speed 60000" -c "reset halt"
```

> 该固件是 **JTAG RAM 加载**版本：掉电/复位后需要重新加载，不会写 Flash。

## 从源码编译

### 1. 环境

- Vivado / SDK **2018.3**（含 `xsct`、`arm-none-eabi-gcc`）
- Python 3.10+，`pip install pyusb libusb-package pyserial pefile`
- （可选）OpenOCD 0.12 用于测速

### 2. 生成 bitstream

```powershell
# 标准 Vivado 2018.3
vivado -mode batch -nojournal -log build\fpga_build.log -source fpga/build_dma.tcl

# 可选封装：本机 Vivado 启动缺 DLL 时用（需改 tools/run_vivado.py 里的安装路径）
python tools\run_vivado.py -mode batch -nojournal -log build\fpga_build.log `
    -source fpga/build_dma.tcl
```

产物：`build/fpga_dma_global/system_wrapper.bit`。

### 3. 生成 BSP 并编译固件

用 Vivado 打开 `build/fpga_dma_global/zynqlink_dma.xpr`，
`File > Export > Export Hardware`（勾选 include bitstream）导出 `.hdf`，然后用 `xsct`
生成 BSP：

```powershell
xsct tools/create_bsp.tcl build/system.hdf build/sdk usb_bsp
```

然后编译 ELF（`--bsp` 指向生成的 BSP；`--gcc` 可指定交叉编译器）：

```powershell
python tools\build_xusbps_daplink.py --project xusbps_daplink_dma --opt 3 --max-swclk-hz 60000000 `
    --bsp build\sdk\usb_bsp
```

产物：`build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf`。

### 4. 加载

```powershell
xsct tools\download_dap_fpga.tcl `
    build\xusbps_daplink_dma\O3\xusbps_daplink_dma.elf `
    build\fpga_dma_global\system_wrapper.bit

# 或
python tools\run_xsct.py --sdk E:\Xilinx\SDK\2018.3 tools\download_dap_fpga.tcl `
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

- [Probe RTT→CDC 与 RTL HSS](docs/probe-rtt-hss.md)（已提供 `prebuilt/zynqlink_probe.*`，F103CB 实板验收）

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


