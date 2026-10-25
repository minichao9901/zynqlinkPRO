# RTL TransferBlock 修复与验收

2026-10-25，Zynq-7020 + 在线 F103，F103 临时配置 HCLK=64 MHz。

## 本轮结果

`DAP_TransferBlock (0x06)` 的普通 AP 读写已在 RTL packet 引擎执行，
经 PS/CDMA 上传命令、下载结果。其它 DAP 命令仍保留原实现，尚未把所有
CMSIS-DAP 协议搬进 RTL。

OpenOCD 20 KiB SRAM dump/load，三次独立会话，每会话各方向 100 轮：

| SWCLK | 读 MB/s | 写 MB/s | 数据、SRAM 恢复 |
|---|---:|---:|---|
| 50 MHz | 2.838 | 3.459 | 全部通过 |
| 60 MHz | 3.261 | 4.072 | 全部通过 |

关闭诊断并重新下载后的最后一次 60 MHz / 100 轮复测：
读 **3.282 MB/s**，写 **4.063 MB/s**，数据和恢复均通过。

这次解决了新协议路径的正确性问题。50 MHz 读速仍未达到 3 MB/s，
也没有超过旧 `dma50_20261025` 基线的 3.052 MB/s；应保留旧版作性能对照。
60 MHz 新结果相对前版 3.183/4.047 MB/s 只有小幅变化，不声称大幅提速。

## 拔掉 LA 后复测

用户报告拔掉 LA 后，重新加载同一个发布包 `packet_20261025` 的 bit/ELF。
F103 HCLK=64 MHz、20 KiB、三会话各方向 100 轮、随机模式 SHA256 和脚本不变。
以下单位均为 MB/s，聚合速率按总字节数除以总耗时计算：

| SWCLK / 方向 | 接 LA 的前次结果 | 拔掉 LA 后 | 变化 |
|---|---:|---:|---:|
| 50 MHz 读 | 2.838 | 2.895 | +2.0% |
| 50 MHz 写 | 3.459 | 3.477 | +0.5% |
| 60 MHz 读 | 3.261 | 3.370 | +3.3% |
| 60 MHz 写 | 4.072 | 4.104 | +0.8% |

所有会话的数据比对及 SRAM 恢复比对均通过，没有改变实现。60 MHz 各会话
读 3.352–3.385、写 4.088–4.112 MB/s；50 MHz 读仍未达到 3 MB/s。
结果略有改善，但两次测试之间的主机调度等波动未被排除，且未做重新接回 LA
的交替对照，不能把这几个百分点全部归因于探头负载。

原始记录：`results/optimization/packet_no_la_50/results.json`、
`results/optimization/packet_no_la_60/results.json`；下载日志标签
`no_la_packet_boot`。发布包保持原来的含 LA 验收记录，保留前后可比性。

## 已修复的问题

1. 接手时复现响应 `06 01 00 00`：count=1，但成功 status 被填为 0。
   CMSIS-DAP 成功状态应为 1。旧的原型测试也错误地期望 0，现已纠正。
2. AP 写块末尾增加 DP RDBUFF 完成检查，并对该读事务检查 parity。
3. 错误响应按实际已完成字数填 count；读响应只携带已完成的数据，
   不再用请求字数填充未完成结果。
4. 启动后的 packet 失败不再整包回退重放。目标 TAR 或外设可能已经发生
   改变，重放会重复写入或把数据写向后续地址。上传前失败仍可用旧 batch 路径。
5. 固件编译读取 `build/fpga_dma_global/verified_clock.json`，约束可接受的
   SWCLK 请求。应先构建 FPGA，再编译配套 ELF。无时序文件时默认上限 60 MHz。

保留了 DeepSeek 的 `6d8362b` 修复：AXI 地址从 6 位扩为 7 位，避免
0x40/44/48 与旧寄存器地址发生截断混叠。这是此前调试中的另一关键问题。

当前 routed netlist：FCLK 180 MHz 不通过；163.636 MHz 下
setup=+0.111 ns、hold=+0.045 ns，通过。50/60 MHz SWCLK 使用约
100/120 MHz FCLK。固件实测拒绝 90 MHz 请求、接受 60 MHz；该时序上限
不代表 F103 板级链路在 70/80 MHz 已经过验证。

## 正确性证据

- `fpga/sim/tb_packet_contract.sv`：同步 BRAM、成功状态、posted AP read、
  写后 RDBUFF、WAIT 重试耗尽、部分 FAULT、最终 RDBUFF parity、
  截断写包拒绝、1023 字读边界，全部为自动断言。
- `fpga/sim/tb_packet_axi.sv`：真实 AXI wrapper、共享 BRAM、packet/core mux；
  验证 packet 寄存器不会触发 legacy core，结果经真实 BRAM 端口读回。
- 实机 50/60 MHz：1、2、127、128、255、256、500、770、1000、1001、1022 字
  随机写读通过；1023 字读的 4096 B 响应及随后命令通过；混合 0x05
  posted-read 映射通过。
- 60 MHz 100 轮随机 20 KiB，每轮完整写读比对通过，最后恢复原 SRAM 并比对通过。
- JTAG 回读 `PACKET_STATUS=0x03030002`：771 个响应字、done=1、busy/error=0；
  此次是 770 字读，经 packet 路径完成。

## 读写不对称的新证据

LA：`results/optimization/packet_contract_read60.csv`，500 MSa/s，CH0=SWCLK、
CH1=SWDIO，1 ms 窗口。请求头周期均值约 16.67 ns；2 ns 采样分辨率导致
周期中位数呈 16 ns，不能据此把实际频率误报为 62.5 MHz。
连续有效 AP read 启动间隔中位数约 816 ns，帧间相邻上升沿间隔约 58 ns。
该短窗口还出现约 648 us 的批次间空档；不能将单次空档当作全程均值。

另用 `--usb-trace` 只开启 USB 事件时间戳，不开每次 MMIO 诊断。
同一轮跟踪中，相同的 770 字块：

| 中位时间 | 读 | 写 |
|---|---:|---:|
| 0x06 从 EXEC 到 DONE，含 DMA/RTL/封装 | 656.4 us | 664.9 us |
| DONE 到提交 USB IN | 0.309 us | 0.285 us |
| USB IN 提交到完成 | 86.4 us / 3084 B | 8.67 us / 4 B |

因此块命令内部执行已近似对称，端到端不对称还包含 USB 结果传输、主机
排队及包间周转。跟踪测试混有启动/恢复阶段，不能把全部命令耗时直接
相加当成纯 60 MHz 测速；正式速率使用关闭诊断的结果。

后续优化应继续量化 USB/主机队列、0x05 尾块与 0x06 的周转，而不是仅靠
缩短 SWD 单字间隔来解释全部损失。

## 复现

```powershell
iverilog -g2012 -s tb_packet_contract -o build/tb_packet_contract.vvp fpga/rtl/dap_transfer_block_engine.v fpga/sim/tb_packet_contract.sv
vvp build/tb_packet_contract.vvp
iverilog -g2012 -s tb_packet_axi -o build/tb_packet_axi.vvp fpga/sim/xpm_memory_tdpram.sv fpga/rtl/swd_core.v fpga/rtl/swd_batch_engine.v fpga/rtl/dap_transfer_block_engine.v fpga/rtl/swd_controller.v fpga/sim/tb_packet_axi.sv
vvp build/tb_packet_axi.vvp
python tools/run_vivado.py -mode batch -nojournal -log build/fpga_packet_contract.log -source fpga/build_dma.tcl
python tools/build_xusbps_daplink.py --project xusbps_daplink_dma --opt 3
python tools/deploy_dap_capture.py build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf build/fpga_dma_global/system_wrapper_verified.bit --tag packet_contract_final
python tools/benchmark_sram_optimized.py --tag packet_contract_60 --target-clock 64 --speed 60000 --sessions 3 --loops 100
python tools/stress_sram.py --tag packet_contract_stress60 --speed 60000 --iterations 100 --target-clock 64
```

USB 跟踪：编译加 `--usb-trace` 后重新下载，空闲时运行
`python tools/capture_usb_trace.py --clear`，执行短测，然后：

```powershell
python tools/capture_usb_trace.py --output results/optimization/packet_usb_trace60.bin
python tools/analyze_usb_trace.py results/optimization/packet_usb_trace60.bin --output results/optimization/packet_usb_trace60.json
```

采集/分析工具从当前 ELF 查找符号地址，不再假设 count/hz 的固定排列。
应保存跟踪 ELF，再重编译和下载不带诊断的生产 ELF。

本机证据：`results/optimization/packet_contract_50/results.json`、
`packet_contract_60/results.json`、`packet_contract_final60/results.json`、
`packet_contract_stress60/results.json`、`packet_contract_validate50.json`、
`packet_contract_validate60.json`、`packet_usb_trace60.json`。

可复用包：`releases/packet_20261025/`，含 bit、ELF、构建清单、校验值、
源码快照和本轮验证摘要。该包为 JTAG RAM 加载版本。
