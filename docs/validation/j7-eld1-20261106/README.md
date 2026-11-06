# J7 ELD1 逐线校准实板

2026-11-06（上海时间）。J7 直通配对和新 ELD1 配对在同一会话、同一 F103ZE、同一 296 B SRAM 负载下对照。ELD1 bit 新增五路 VAR_LOAD IDELAYE2，分别连接 D0/D1/D2/D3/CLK，布线后沿 DATAOUT 核对至五个独立 RAW4 采样端点。J7 的 12 球号与 I/O 标准再次逐项核对。实现约束 133.333333 MHz，setup/hold 余量 0.044/0.041 ns，短 SWCLK 输出预算余量 0.342 ns。

| 配对 | bit SHA-256 | PS ELF SHA-256 |
|---|---|---|
| 同场直通输入 | `792d4b6c8f38e47b1ba27d19a4ff5211e3a05be642edac7a526baa727df65abc` | `1fbf6471e14669a809aa02a3e4a6fbb262370ea9b45511f2a460e6f52a5d4ee5` |
| ELD1 实验 | `0f20227a3ed159065834cad1106ff7a2d6c50c64e576f2c20038c7ffd7dabfde` | 同上；本轮重新编译，字节相同 |

新建 ELD1 工程复用 44 个缓存 IP，采用源码已有的延时模块。首次 opt 阶段成功后，驱动对 Vivado 状态文案匹配过窄而误报失败。核对 opt 结束标志、成功日志和 DCP 后继续原网表，保留首次驱动日志。五路 tap 功能、错误装载和采集集成仿真通过。 工件配对（历史归档 `archive/main-before-formal-release-20261106:prebuilt/j7-eld1-calibration-20261106/README.md`） · [实施摘要](raw/implementation-summary.txt)

## 结果

| 条件 | 36 MHz 实测 |
|---|---|
| 直通输入，100 ms × 3 | parser 错误 4 / 4 / 1，全失败 |
| ELD1 零 tap，100 ms × 3 | parser 错误 1 / 0 / 2，通过 1 轮 |
| 调校后 `28,18,15,20,15`，100 ms × 3 | 全通过，首轮 USB 与物理 DDR 读回一致 |
| 同一候选，1 s × 3 | parser/包错误均 0，每轮约 3081 万条指令，完整解码建库通过 |
| 各线 ±1/±2 tap 的 20 个邻域，100 ms | 16 个通过、4 个失败，集中于 D0/D1 |
| ELD1 零 tap，32 MHz 1 s × 3 | 全通过，作为收尾频率对照 |

候选 tap 按 D0、D1、D2、D3、CLK 排列。相比直通和零 tap，校准使 **36 MHz 的固定设置通过了三轮 1 秒采集与完整解码**。最终邻域中 D0=27，D1=16/19/20 分别出现 2、1/3/1 次 parser 错误，尚未达到预定的 ±2 tap 裕量标准，`confirmed36MHz=false`。32 MHz 继续保留为已验证的稳定边界。 [完整 219 点记录](raw/calibration.json) · [同场直通对照](raw/direct-control.json)

先测零 tap，再测公共 data/clock 的 5×5 粗网格，最后依次对五路扫描全部 0～31 tap。每个配置的首次结果都保留，失败点不重试。通过点要求窗口完整、无 parser/FIFO/writer/ready 故障，并检查 formatter 四路 0/1 与翻转激励。候选与长窗独立做原生解码、函数核对和指令数量比例交叉检查。D0 首次扫描未形成 5 个连续通过 tap，后续各线扫描与候选独立验证继续保留，最终判据包含全部邻域。

本次 219 个点均完成控制与清理。历史 ZL-009 第111点故障的原始根因仍待定位，新增每次地址设置的请求及回复记录，发生非输入质量故障即停止。测得的是这些输入和有限时长的协议通过区。 [所有点原始文件 SHA](raw/all-points-identity.json)

## 恢复与核查

tap 恢复为任务开始的零设置，RCC、APB1ENR、Flash ACR、64 KiB SRAM、核心寄存器、VTOR、FPB 和 DWT 恢复并读回。原 J7 生产配对已经重新加载，85580 B PS 执行段物理核对一致，CDC48 Flash 装载段和时钟匹配，目标运行。 [板卡收尾](raw/board-summary.json) · [目标复核](raw/target-after.json)

用户要求复核改脚遗漏，发现并登记了原始 `0x1D` 旧 GPIO 路径和 TCK 断开仍驱动问题，另列 RTCK 预留、独立复位脚验收及外部时序约束范围。 [J7 改脚复核](j7-production-audit.md)
