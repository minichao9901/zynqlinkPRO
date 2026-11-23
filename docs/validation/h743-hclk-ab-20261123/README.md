# H743 HCLK60／240 运行态对照

2026-11-23，探针 J7 USB `12345678`、HS3 `210299008529`，同一块 STM32H743 Rev V。两档均使用同一个 [RAW4 融合 bit/PS ELF](../../../prebuilt/selectio-usb-split-raw4-20261123/README.md) 和同一份已刷入的历史 CDC Golden ELF。物理 MEM-AP0 复核探针 OCM 80,668 B。CPU/HCLK 分别是 60/60 与 480/240 MHz，两档 CPU 用 DWT 回读，HCLK 由 D1 分频寄存器确认。

通过低速 SWD 临时把同一 HSE 驱动的 PLL1 调至 480 MHz，AHB 二分频，原 LDO 保持，VOS1 开 ODEN 进入 VOS0，先把 Flash ACR 临时设至 4 WS。PLL2/3 和 PLL1Q/R 的输出保留。升档期间目标执行验收负载，CDC 应用的 Flash 保持原样。 [STM32H743 数据手册](https://www.st.com/resource/en/datasheet/stm32h743ai.pdf) · [RM0433](https://www.st.com/resource/en/reference_manual/dm00314099.pdf)

## 同口径 A/B

每条链路在两档使用相同 SRAM 地址。SWD AXI SRAM 地址为 `0x24043020`，JTAG DTCM 为 `0x2000b020`。SRAM 使用 4,032 B 跨页、WinUSB 深度 4，CPU 在现有的 Flash 自跳转指令上保持运行。RTT 使用同一段 RAM producer、同一 8 KiB 环、2,048 B chunk 与独立 EP7，目标运行态生产，逐字对账并核对 STOP 后环指针。以下是约 2 秒对照窗，单位为十进制 MB/s。

| 调试路径 | HCLK60 读／写／RTT | HCLK240 读／写／RTT |
|---|---:|---:|
| SWD 99.999998 MHz，tap8/slot25/idle4 | 0.797／0.780／0.755 | **4.926／4.773／4.299** |
| JTAG 99.999998 MHz，tap16/slot28/idle65 | 读写均首笔 WAIT，RTT 0.624 | 3.397／3.324／3.021，读写为单独短窗 |
| JTAG 49.999999 MHz，tap16/slot28/idle255 | 0.644／0.642／0.622 | 0.644／0.641／0.623 |

SWD 的 SRAM 读、写和 RTT 分别约为原速率的 6.18、6.12 和 5.70 倍。JTAG 50 MHz/idle255 在两档均通过，读窗口均零自动退避。该档每字先花 298 个 TCK，扫描预算约 0.671 MB/s，覆盖了两档实测 0.64 MB/s。JTAG 100 MHz/idle65 的 HCLK240 单向短窗能通过，随后交替读写复测出现异常 ACK，未签收。

### WAIT

SWD 每个读写请求为同一页的 256 个数据字，另有 3 个设置／确认事务。通过探针的物理 MEM-AP0 读取 PL `0x80010014` 高 16 位的 WAIT 计数。每个方向独立三轮。

| HCLK | 读 WAIT | 写 WAIT |
|---|---:|---:|
| 60 MHz | 5,377 / 5,377 / 5,377 | 5,472 / 5,473 / 5,473 |
| 240 MHz | 257 / 257 / 257 | 259 / 259 / 259 |

WAIT 下降约 95%。这一对照同时改变 CPU 和 HCLK，验证了提速工况对运行态 MEM-AP 等待的影响。JTAG 记录的是队列的可见 WAIT 和读块自动退避，独立 RTT 引擎没有对主机公开逐事务 WAIT 计数，所以 RTT 仅列吞吐、序列、STOP 与错误计数。

## JTAG 筛档

HCLK240 下，100 MHz 对 slot27–32 和多个 idle 值做定向筛选。slot28 的 idle49/57/61/63 等有 WAIT，idle65、67、69、71、73 等在复跑中有异常 ACK。较长 idle 也出现异常 ACK。PL 队列状态 4 包含不符合预期的扫描 ACK，单凭该状态无法判定是目标总线 FAULT 还是采样导致的错误。 [扫描状态定义](../../../fpga/rtl/jtag200_arm_stream.v#L140)

### JTAG SRAM 长窗

签收档位为实际 **72,727,272 Hz、tap16／slot26／idle65**，HCLK240。扫档中 slot26 的 idle73、81 和 97 也短测通过，50 MHz／slot28／idle33 短测合计约 2.421 MB/s。签收档的 5 秒独立读／写为 **2.502／2.462 MB/s**。下表是同档的运行态交替长窗，每次写入不同载荷并紧接读取校验。

| 轮次 | 实际秒数 | 合计载荷 B | 合计 MB/s | 自动退避 |
|---|---:|---:|---:|---:|
| JTAG-L1 | 60.01 | 148,377,600 | 2.473 | 0 |
| JTAG-L2 | 60.02 | 148,442,112 | 2.473 | 0 |
| JTAG-L3 | 60.02 | 148,442,112 | 2.473 | 0 |

三轮载荷、旁侧保护字和 PS 字节计数相符。

### JTAG RTT 长窗

72.727 MHz SRAM 签收档启动独立 EP7 RTT 后，首轮收尾的 DAP Disconnect 返回 `ff`。确认 PL 队列、ETM 和 CDMA 空闲后，临时重载同一 bit/ELF 并独立从备份恢复。第二轮保留了 5 秒采样状态，显示上行 0 B、返回 `-4`，探针错误计数 499。自动恢复采用 DAP Connect 的上下文恢复入口并成功核对原时钟。72.727 MHz 独立 RTT 继续待验。

**RTT 签收档为实际 49,999,999 Hz、tap16／slot28／idle33。** 同一 EP7、8 KiB DTCM 环、2 KiB chunk，在 HCLK240 连续 60.000 秒实收 134,385,664 B，**2.240 MB/s**。包含 STOP 尾部共 134,387,712 B，逐字序列和探针计数一致，错误为 0。保留目标的 WrOff、RdOff 和 producer 计数，环内未转发的 8,188 B 与已转发载荷相加等于目标已发布量。

## 现场交接

- SWD 的运行态 A/B、每页 WAIT 和 JTAG 短筛见 [时钟及短窗证据](clock-and-short-evidence.json)。JTAG 三轮 SRAM、RTT 分档、失败和独立恢复见 [长窗与最终现场证据](long-and-restoration-evidence.json)。脚本及私有 SRAM 备份保留于本机 `build/h743-hclk-ab-20261123`。
- H743 已恢复原 CDC CPU/HCLK 60/60 MHz、RCC/PLL、Flash ACR、LDO/ODEN、SRAM 和核心寄存器。独立复核目标处于运行，心跳及 COM43 回显通过，31,752 B Flash ELF 装载段逐字节相同。
- 探针保留同一 RAW4 RAM 配对，物理 OCM 80,668 B 一致，RTT、HSS、ETM、DDR 和 CDMA 空闲。源代码和证据仅交付到本地融合分支。本地与远端 `main` 均为 `03b6a1da`。固定 EXE、Pages、Release 和 QSPI 冷启动超出本轮交付范围。
