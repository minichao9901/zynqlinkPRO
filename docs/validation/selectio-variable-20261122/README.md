# SelectIO 可变参考与裁剪镜像

范围为离线仿真与 Vivado 2018.3 实现，目标器件 XC7Z020-CLG400-2。融合、JTAG/SPI、SWD/SWO/ETM 三套保持 A 布局，PS 侧命令、CDMA 与载荷 BRAM 主机端在 FCLK0，逐笔事务与 PHY 并行口同域。镜像与各自 PS ELF 及 PS 初始化脚本配套。本轮没有目标板数据。

## 时钟与换档

FCLK0 按 133.333 MHz 实现。FCLK1 单独给 SelectIO，采用约 1600 MHz IO PLL 和整数除数 N。FCLK2 固定约 200 MHz，供 ETM 和 IDELAYCTRL。SelectIO MMCM 固定乘 24，TX、quad、宽 RX 和 octet 路分别除 6、12、3、24。原参考方案仍由普通 --selectio 生成，新方案用 --selectio-variable。

固件对 50–100 MHz 选不超过请求上限的最高合法频点。采用相同线频的多个配置时优先保留较快的 quad 域。FCLK1 除数限制 32–63，确保当前已约束的 quad 和接收串行时钟上限。调用方对各速度仍可分别配置 tap 和 ACK/data slot。换档需在队列和引脚空闲时进行。AXI 写入停 PHY 后，读回停机状态并保持 MMCM 复位，再改分频。重新锁定后恢复 PHY。UART/SWO 流正在使用共享采样时拒绝改变分频。50↔100 两档使用同一分频，只改变波形。固定 FCLK2 的 ETM 采样路径独立。

初次构建使用 BD 的 100 MHz FCLK0 默认值，Vivado 生成的 IO PLL 为 1800 MHz，虽然两路参考在默认频率附近可用，不能匹配调频表。最终配置把 FCLK0 目标指定为 133.333333 MHz，离线核对 IO PLL 反馈系数为 48，FCLK1/FCLK2 从相应整数分频得到 50/200 MHz。运行时配置读取 SLCR 实际值，BD 生成时核对 PLL 和两路参考，路由验证核对 A 布局和派生时钟。

首轮放置被 REQP-1578 拒绝，原融合版的 MMCM 输入经过共享参考上的 BUFG，迁移后需在 PS 端显式打开 FCLK1 全局缓冲。JTAG 裁剪版独立使用 FCLK2 驱动 IDELAYCTRL，也打开该输出的全局缓冲。修正后的融合版已通过放置前 DRC。[失败原始证据](first-placement.txt)

## 台架口径

- Cortex-M3 DesignStart HCLK128，SWDIO 模拟返回延时 16 ns，idle 0。50 和 72.727 MHz 使用 slot22，100 MHz 使用 slot24。使用实际 Xilinx 7 系列时钟及 SelectIO 原语。
- SRAM 窗口为两批各 256 字，所有字逐一核验。RTT 窗口为 8 KiB 环和 2 KiB 块，四包全部校验并计到最后一次 RdOff 经 DP 应答确认，随后核对目标 SRAM。
- 逐笔台架记录最后一位 ACK 至下一次 SWCLK 上升沿。批次记录各 ACK DRAIN 的 quad 周期数和整个窗口的引脚额外停钟。启用提前边沿的情况可以先发出合法释放边沿，然后在该边沿之后继续等待读回或协议决策。两个计数的测量边界不同。
- 裁剪前后的同频对照均为 100 MHz。JTAG 用等长的 256 字窗口，HCLK128、TDO 模拟返回 0.8 ns、slot21、idle33。与 SWD 台架的载荷大小、段内空闲周期和协议开销不同。

## 三频结果

| SWCLK / slot | quad 周期 | ACK 最后一沿到下一沿，OK | ACK 段累计等待，512 字读 / 写 | SRAM 读 / 写 MB/s | RTT 到末次 RdOff MB/s |
|---|---:|---:|---:|---:|---:|
| 50 MHz / 22 | 10 ns | 50 ns | 20.72 / 20.80 µs | 4.114 / 4.151 | 3.935 |
| 72.727 MHz / 22 | 13.75 ns | 13.749–13.751 ns | 28.49 / 28.60 µs | 5.520 / 5.846 | 5.250 |
| 100 MHz / 24 | 10 ns | 10 ns | 25.90 / 26.05 µs | 7.307 / 7.868 | 6.901 |

上表使用产品 SWD RTL。逐笔注入 OK、WAIT、FAULT 和奇偶校验错全部通过，写波形、SWDIO 换向、WAIT 只重试原事务及错误后的停止也通过。实际参考从 20 ns 改为 27.5 ns 时，检查引脚停发、拒绝未停机的 MMCM 复位、重新锁定，以及固定 5 ns 校准参考始终有效。

72.727 MHz 档每笔的 ACK DRAIN 仍为四拍，绝对等待由 40 ns 增至 55 ns。100 MHz 的 slot24 每笔为五拍，即 50 ns。72.727 和 100 MHz 的已有提前边沿在 ACK 后立即出第一沿，因此引脚看上去连续，内部回采等待仍体现在随后分段上。全窗口累计停钟见原始计数，其中含读尾、批次交接及台架控制时间。MB/s 是数字台架的有效数据速度，RTT 测量到目标偏移确认。

在 100 MHz，JTAG 的 256 字批次读 / 写，融合和 JTAG 裁剪均为 5.064 / 5.063 MB/s（原始读 5.063917、写 5.063448）。SWD 的 SRAM、RTT 时长、边沿和 ACK DRAIN 计数在两种构建参数下一致。

50 MHz 提前边沿对照在新时钟树下也通过。最后一个 ACK 到下一沿从 50 ns 降至 20 ns。512 字读 / 写各省约 10.4 µs，RTT 四包的引脚停钟从 122.650 µs 降到 79.720 µs。该对照使用 XSim 单独生成的候选。

DAP 安全回归和 24 个定向 Python 测试通过。旧全套 probe_host 测试的首项仍因工具期待 0.7-nonce32 而固件返回 0.8-nonce32 提前退出，两边版本字符串未由本轮改动。

[仿真原始计数](simulation.txt)

## 100 Mbit/s SWO

100 Mbit/s 所需的采样预算来自 SelectIO 时钟。50 和 100 MHz SWD 档均为 N=32，窄接收 400 Msample/s、宽接收 800 Msample/s，具有融合版既有高速解码条件。72.727 MHz 档为 N=44，分别为 290.909/581.818 Msample/s，以当前配置约 72.727 Mbit/s 为上限，固件拒绝越界请求。这里列出时钟与解码预算，尚无新镜像的目标板 SWO 信号验收。JTAG/SPI 镜像关闭 SWO。

## 融合镜像

融合版完成 Vivado 布线和 bitgen。时序为 setup / hold **+0.062 / +0.023 ns**，使用 26,240 LUT、28,320 寄存器和 67.5 个 BRAM tile。路由核对 GP0、GP1、HP0、HP1 均使用 7.5 ns 的 FCLK0，SelectIO 和 ETM 参考周期分别为 20 ns 与 5 ns。配套 ELF 已链接，加载入口通过 --dry-run 文件预检。

[STA](full/timing_verified.rpt) · [利用率](full/utilization.rpt) · [实际时钟连接检查](full/routed-checks.txt) · [镜像配对清单](../../../prebuilt/selectio-variable-20261122/full/manifest.json)

## 复现

在仓库根目录使用 Vivado 2018.3 与 SDK 2018.3。每套实现选择独立的 ZYNQLINK_FPGA_OUT，并保持 FCLK0 的 7.5 ns 约束。

```powershell
python -X utf8 tools/run_vivado.py -mode batch -source fpga/build_dma.tcl -tclargs --selectio --selectio-variable --etm400
python -X utf8 tools/run_vivado.py -mode batch -source fpga/build_dma.tcl -tclargs --selectio --selectio-variable --selectio-jtag
python -X utf8 tools/run_vivado.py -mode batch -source fpga/build_dma.tcl -tclargs --selectio --selectio-variable --selectio-swd --etm400
```

候选 ELF 使用 tools/build_xusbps_daplink.py 的 --selectio --selectio-variable --j7-adapter --compact-code --opt s --experimental-zero-idle，以及对应实现目录的 --timing verified_clock.json。裁剪镜像分别加 --selectio-slice jtag 或 --selectio-slice swd。PS 初始化 Tcl 取对应构建生成的 system_processing_system7_0_0。

```powershell
$bench = @('--swd-only','--target-clk-ns','7.8125','--idle','0','--return-ns','16','--wire-budget','--swd50-windows')
python -X utf8 tools/selectio_cm3.py @bench --variable-clock 32 --half-rate --swd-slot 22 --out build/vclk-sim-50
python -X utf8 tools/selectio_cm3.py @bench --variable-clock 44 --swd-slot 22 --out build/vclk-sim-72727
python -X utf8 tools/selectio_cm3.py @bench --variable-clock 32 --swd-slot 24 --out build/vclk-sim-100
python -X utf8 tools/selectio_cm3.py @bench --variable-clock 32 --swd-slot 24 --slice swd --out build/vclk-sim-swd-slice100
python -X utf8 tools/selectio_cm3.py --variable-clock 32 --jtag-only --target-clk-ns 7.8125 --jtag-slot 21 --out build/vclk-sim-jtag-full
python -X utf8 tools/selectio_cm3.py --variable-clock 32 --jtag-only --target-clk-ns 7.8125 --jtag-slot 21 --slice jtag --out build/vclk-sim-jtag-slice
```

可变参考的例子为 --clock 73000000，实际档位约 72.727 MHz。原生读写和批量测速 CLI 支持该参数。已有接口的时钟回读字段仍使用串行时钟作为计算基数，探针寄存器观察另报 FCLK1、FCLK2 和 quad 的结果。

逐笔时序用 --swd50-faults 替换 --wire-budget --swd50-windows，在相同 FCLK1 分频、SWD 档和 slot 下执行。50 MHz 的提前边沿单独用 --early-swd50，对应仍是仿真候选。
