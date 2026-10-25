# 纯 DAPLink 移植进度

新工程位于 [firmware/xusbps_daplink](<firmware/xusbps_daplink>)，来源是旧工程的 `usb_bsp_xusbps_daplink_2`，保留 CMSIS-DAP、CDC ACM、SWD/RTL 接口；RTT bridge、`swd_host` 和 RTT 主循环已全部移除。

**当前状态（2026-10-25）：OpenOCD nightly（0.12.0+dev-gcb0c224，异步 bulk + DAP_TransferBlock）配 4096B 包已打通。F103 的 reset/halt/step/断点/20KiB SRAM dump/load 正常，数据回读一致。**

## 打通过程中修掉的问题

### 1. 必须先下载 PL bitstream

板子上电时 FPGA 没有配置，`mrd 0x40000000` 直接报 `Cannot access FPGA: Bitstream is not programmed`。SWD RTL 在 PL 里，只下 ELF 时 `DAP_Setup()` 写的是不存在的寄存器，OpenOCD 连不上。

正确顺序（[tools/download_dap_fpga.tcl](<tools/download_dap_fpga.tcl>)）：

```tcl
rst -system → ps7_init → ps7_post_config → fpga -f system_wrapper.bit
→ rst -processor → dow xusbps_daplink.elf → con
```

bitstream 在 [build/bitstream/system_wrapper.bit](<build/bitstream/system_wrapper.bit>)（SHA-256 `C0438D83…E521`），本次**没有改 RTL、没有重新综合**，只重新下载。

### 2. 4096B 包：OpenOCD 老版本的 8 位 count

OpenOCD ≤ v0.12 用 `DAP_Transfer` 打包，count 只有一个字节，4096B 包时 `N=(4096-4)/5=818`，低字节变成 50，报 `transfer count mismatch: expected 818, got 50`。老版本下必须把 `DAP_PACKET_SIZE` 降到 1024。

**OpenOCD master 改用 `DAP_TransferBlock`（16 位 count）+ 异步 bulk 后，4096B 包可以正常工作**，现在 [DAP_config.h](<firmware/xusbps_daplink/DAP/Include/DAP_config.h#L101>) 已改回 4096。

### 3. 大块传输回退到逐 word 路径（已修）

固件原来对 `rsp_words > 1024` 的块传输直接回退到 `DAP_SWD_TransferBlock_Legacy`。4096B 包时 OpenOCD 经常发 1023 字的块，正好触发回退，batch 引擎白放着。

现在 [DAP.c](<firmware/xusbps_daplink/DAP/Source/DAP.c#L1381>) 在 batch 内部按 1000 字（读，受 1024 字响应 BRAM 限制）/ 500 字（写，受 1024 字命令 BRAM 限制）分块，连续跑多段 batch。跑完后 `DAP_SWD_Stats.xfer_block_legacy_depth = 0`，说明不再回退。

验证：1023 字的 AP 块读（1000+23 两段）返回 **0 mismatch**，3.01 ms。

### 4. 整 512B 倍数的响应需要 ZLP（已修）

255 字块读的响应是 1024 字节，正好是 512 的整数倍；不发 ZLP 时主机一直等自己的 4096 字节缓冲，直到超时（实测 3 秒）。现在 [dap_main.c](<firmware/xusbps_daplink/dap_main.c>) 的响应发送在 `len % 512 == 0` 时改用 `XUsbPs_EpBufferSendWithZLT`，同一个 255 字块读降到 **0.97 ms**。

## 实测（OpenOCD nightly，4096B 包）

| 项目 | 结果 |
|---|---|
| 20 KiB SRAM dump | 16.2 ms ≈ **1.27 MB/s**（1.21 MiB/s） |
| 20 KiB SRAM load | 13.9 ms ≈ **1.47 MB/s**（1.40 MiB/s） |
| 128 KiB flash dump | 100–106 ms ≈ **1.28 MB/s** |
| 裸块读 1023 字 | 3.01 ms ≈ 1.36 MB/s |
| 1024B 包 + 老 OpenOCD 对照 | 读/写都约 1.14 MB/s |

即 4096B 包 + 异步 + 块传输比老组合快约 11%（读）/ 29%（写），但没有出现预期中的数倍提升。

## 为什么没有数倍提升

之前记录的“块读 4.6 MB/s”是**测量假象**：那次 raw 测试没有先写 SELECT/给 DP 上电，AP 块读返回的是 `0x01000000` 之类的错误数据，错误响应瞬间返回，算出来的速度当然高。

现在用正确的 DP 初始化后再测：IDCODE 正确、CSW/TAR ACK 正常、1023 字块读数据全对，真实速度就是 1.3–1.5 MB/s。瓶颈已经从 USB 转到 **F103 的 SWD 接口**：

- 每字约 2.7 µs（≈17 MHz 等效），50 MHz SWCLK 下目标会插 WAIT；
- 1023 字块读 3.01 ms，其中固定开销约 0.5 ms；
- USB 侧 4 KB 传输 + 异步已经足够快（连续流 40 MB/s 量级）。

## 已知问题

1. **`adapter speed` 仍然无效**：固件把 `SWD_CFG.delay_fast` 固定写 0（SWCLK 50 MHz），`DAP_SWJ_Clock()` 只改 bit-bang 的 `clock_delay`。本次试过让 `DAP_SWJ_Clock` 真正写 `SWD_CFG`：20–50 MHz 可用，但 **≤15 MHz 时 DP 直接读不到 IDR**，说明 RTL 的慢时钟路径有问题（turnaround/idle 计数或 SWDIO 采样相位），已回退，需要看 `swd_core.v` 的时序再改。
2. 目标本身限速：F103 在 50 MHz SWCLK 下只能跑到约 1.3–1.5 MB/s；换更快的目标才能看出 DAP 的真实上限。
3. `verify_image` 会占用 `stm32f1x.cfg` 的 work area（0x20000000）跑 CRC 算法，验证该区域要用 dump + 主机比较。

## 复现

```powershell
python tools\build_xusbps_daplink.py --opt 3
python tools\run_xsct.py tools\download_dap_fpga.tcl `
  build\xusbps_daplink\O3\xusbps_daplink.elf build\bitstream\system_wrapper.bit
& 'E:\Share\env-windows\openocd-nightly\bin\openocd.exe' `
  -s 'E:\Share\env-windows\openocd-nightly\share\openocd\scripts' `
  -f tools\openocd_dap.cfg -c "init" -c "reset halt" -c "reg pc" -c "exit"
```

测速脚本：[tools/dap_sram_bench20.tcl](<tools/dap_sram_bench20.tcl>)、[tools/dap_block_1023.py](<tools/dap_block_1023.py>)；汇总在 [results/daplink/dap_bringup_summary.json](<results/daplink/dap_bringup_summary.json>)。
