# Kingst LA 使用说明（MIPI16 + KingstVIS socket）

本工作区用 Kingst **MIPI16** 抓 SWD 波形。LA 的“设备模式/通道/电平”只能在 GUI 里设一次，之后的采集、导出、切片可以用脚本全自动做。

实测环境：KingstVIS 3.6.6，设备 MIPI16，socket 端口 23367。

## 一、接线

| LA 通道 | 接到 |
|---|---|
| CH0 | SWCLK |
| CH1 | SWDIO |
| GND | 板子 GND（必须共地） |

可选：CH2 接 nRESET，做复位参考。

## 二、GUI 里必须人工设置一次

参考截图/实测可用的配置：

- 设备：**MIPI16**，模式：**正常模式**
- 采样率：**500 MHz**
- 深度：**200 MSa**（对应 400 ms 窗口）
- I/O 电平：**3.3V CMOS**，Vth **1.65 V**
- 通道：至少使能 CH0、CH1（通道左侧的齿轮里能看到 3.3V CMOS / Vth）

通道使能状态存在 `%LOCALAPPDATA%\kingst\vis.config` 的 `<chnEnable>` 里。如果它是空的（`<chnEnable/>`），所有通道都不会采，导出的 CSV 只有一行常量——这是之前一直“采不到”的原因之一。改完配置要**重启 KingstVIS**。

备份/恢复：

```powershell
copy "$env:LOCALAPPDATA\kingst\vis.config" "$env:LOCALAPPDATA\kingst\vis.config.bak"
# 恢复
copy "$env:LOCALAPPDATA\kingst\vis.config.bak" "$env:LOCALAPPDATA\kingst\vis.config"
```

## 三、socket 自动采集流程

工具：`tools/la/la_capture_export.py`（封好了 set/start/export/重试），或直接调用 `tools/la/kingst_la.py` 里的 `Vis` 类。

最小可用序列：

```python
from kingst_la import Vis
v = Vis()
v.cmd("set-sample-rate 500000000")   # 500 MHz
v.cmd("set-sample-time 0.05")        # 0.05 s = 25 MSa（也可 set-sample-depth 200000000）
v.cmd("set-threshold-voltage 1.65")
v.cmd("set-trigger --reset")         # 关键：不复位触发器，start 可能一直等
v.cmd("start", timeout=20)           # 阻塞到采完
v.cmd('export-data "E:/.../cap.csv" --time-span 0 0.002')  # 只导 2 ms 窗口
v.close()
```

命令行等价：

```powershell
python tools\la\la_capture_export.py --rate 500000000 --time 0.05 --threshold 1.65 `
  --out results\daplink\la\cap.csv
```

## 四、导出窗口：千万不要导整段

500 MHz × 400 ms 的整段 CSV 实测 **1.94 GB**，导出要几分钟，还会把 VIS 卡住。正确做法：

- 采集可以采 0.4 s，但 `export-data` 一定要带 `--time-span`，一般导 **1–2 ms** 就够看十几包 SWD；
- 已经导出了大 CSV，可以用 `tools/la/la_slice_csv.py` 流式切出活跃窗口：

```powershell
python tools\la\la_slice_csv.py results\daplink\la\socket_cap.csv results\daplink\la\slice2ms.csv 3000000
```

它会扫描前 N 行、按 1 ms 统计 CH0 跳变密度，挑最活跃的 2 ms 写成小 CSV。

## 五、配合 SWD 持续流量

抓包时让 SWD 一直跑，成功率最高：

```powershell
# 后台跑：循环 dump 16 KiB，持续 15 分钟
& 'E:\Share\env-windows\openocd-nightly\bin\openocd.exe' `
  -s 'E:\Share\env-windows\openocd-nightly\share\openocd\scripts' `
  -f tools\openocd_dap.cfg -d0 -c "script E:/zynqlinkPRO/tools/ocd_live_traffic.tcl"
```

然后另开一个进程采集（采集期间不要同时跑别的 OpenOCD 命令）。

## 六、分析脚本

| 脚本 | 用途 |
|---|---|
| `tools/la/la_activity.py <csv>` | 找有跳变的通道、边沿数、边沿间隔 |
| `tools/la/la_swd_timing.py <csv>` | SWCLK 周期、frame/burst 划分、gap 统计 |
| `tools/la/la_swd_burst.py <csv>` | 最大 burst 的每字间隔 |
| `tools/la/la_swd_frames.py <csv> [N]` | 逐 frame 打印 bit 流，解码 SWD 包头 |
| `python tools/la/kingst_la.py decode <csv> --ch-clk 0 --ch-dio 1 --gap 0.2e-6` | 正式 SWD 解码：ACK/数据/校验 |

## 七、实测样例（2026-10-25）

文件：`results/daplink/la/manual_1ms.csv`（500 MHz，1 ms 窗口，CH0/SWCLK + CH1/SWDIO）。

```
CH0: 79498 edges，中位间隔 10 ns → SWCLK 54 MHz
CH1: 18521 edges（数据）
每读一个 AP word：WAIT(13 clk) → WAIT(13 clk) → OK(47 clk)
1 ms 内解码：13 笔 OK、26 笔 WAIT、1 笔 FAULT（WAIT:OK = 2:1）
每字周期 ≈ 2.45 µs = 时钟 1.35 µs + 事务间空隙 1.1 µs
```

结论：SWD 协议/数据正确，F103 在 54 MHz 下每字回 2 个 WAIT；RTL 每笔事务之间还有约 300 ns 空隙（占每字 45%），这是后面优化的重点。详细分析见 [Codex交接总结.md](Codex交接总结.md) 第 5.3 节。

## 八、常见问题

| 现象 | 原因/处理 |
|---|---|
| CSV 只有表头 + 一行常量 | 通道没使能（`vis.config` 的 `chnEnable`）、探头没接/没共地、输入电平模式不对 |
| `start` 一直不返回 | GUI 里挂着触发器；先 `set-trigger --reset` 再 `start` |
| `export-data` 返回 NAK `save file failed` | 重试 3–5 次；或换目录；先 `stop` 再导 |
| 导出的 CSV 巨大（GB 级） | 没带 `--time-time`，用 `--time-span 0 0.002` 只导窗口 |
| VIS 卡住、socket 全部超时 | 先发 `stop`；不行就重启 KingstVIS（配置在 `vis.config`，采集数据若没导出会丢） |
| 触发抓不到 | 用自由采集 + 持续 SWD 流量，别依赖触发 |

## 九、一句话流程

GUI 里设好 MIPI16/正常模式/500 MHz/200 MSa/3.3V CMOS/Vth 1.65 并使能 CH0、CH1 → 后台跑 `ocd_live_traffic.tcl` → `la_capture_export.py` 采集 → `export-data --time-span 0 0.002` 导 2 ms → `kingst_la.py decode` 解码。
