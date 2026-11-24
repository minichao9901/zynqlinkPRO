# 新融合配对的三板验收

在 `E:\zynqlinkPRO-efficiency` 根目录执行。根目录 JSON 的 `fusionAcceptance` 规定必验用例、档位、目标镜像、判据和当前执行器。三板所有功能和性能用例固定使用 `prebuilt/selectio-usb-split-raw4-20261123`。CDC Golden 指用来产生 ETM 工作负载的目标 MCU 固件。 [RAW4 ABI 2 配对](../../prebuilt/selectio-usb-split-raw4-20261123/manifest.json) · [验收清单](../../acceptance-cases.json) · [目标镜像](../../firmware/target/README.md)

## 查询和绑定配对

```powershell
python -X utf8 toolbox.py project run fusion.accept -- list --board h743
python -X utf8 toolbox.py project run fusion.accept -- describe fusion-h743-combo
python -X utf8 toolbox.py project run fusion.accept -- campaign --serial <J7序列号> --out build/runs/fusion-campaign/<批次ID>
```

第三条离线核对 bit、PS ELF 和初始化 Tcl 的 SHA-256，并生成 `campaign.json`。旧批次需要重新创建。取得现场授权后，通过 `toolbox.py probe-load --selectio --cable-serial <实接HS3序列号> --usb-serial <J7序列号> --out <新的加载证据目录>` 临时加载探针。从加载目录取 `result.json`。重载后使用新的加载回执。实板执行核对回执的哈希和序列号，通过物理 MEM-AP0 核对探针 PS 代码，并交叉核对 USB 与 HS3 是否连接同一探针。

按 `describe` 输出准备唯一连接的目标、指定镜像与接线。实板执行前确认其他程序已经释放 USB 和目标，并备份要更改的 Flash、RAM 和外设状态。对 ARM 性能用例，先确认当前档位的采样 tap、slot 和 idle。SPI 加 `--manual-spi-switch`，使用能隔离 SWD 和 SPI 的切换夹具。H743 通过目标 USB CDC 控制。F103ZE 主发有 5 秒切换并使能 J7 接收的窗口。每个命令只执行一个档位组合。

## 执行单档并保留证据

```powershell
python -X utf8 toolbox.py project run fusion.accept -- run fusion-h743-combo --image performance-axi --transport swd --rate 50000000 --tap <已校准值> --slot <已校准值> --idle <已校准值> --group-rate 1000 --channels 8 --campaign <campaign.json> --out build/runs/fusion-h743-combo/<运行ID>
```

以上命令预览。实板运行追加 `--execute --hs3-serial <实接HS3序列号> --probe-load-receipt <本次加载目录的result.json>`。设置 `--out` 为新目录。SWO 的 `--rate` 使用信息位率，以 `--encoding uart` 选 NRZ，`--encoding manchester` 选 Manchester。UART 的 `--rate` 为波特率。SPI 用 `--spi-mode` 选 CPOL/CPHA，收与全双工加 `--frame-bytes`。Flash A/B 用 `--image dbg-a` 或 `--image dbg-b` 检查当次实际启动。

查看 `summary.json` 和同目录原始证据。 `pending` 表示脚本已执行，仍需按该行判据补证据或合并其余档位。 `fail` 保留首个失败和原始输出。 `blocked` 记录具体缺口。恢复未确认时停止随后各档。独立码源或外部对端采集可用下列命令逐字节复核，保存输出并随该档提交实际线速、方向、窗口、计数和接线记录。

```powershell
python -X utf8 toolbox.py project run fusion.evidence -- --actual <完整采集.bin> --expected <独立码源参考.bin>
```

### 执行器的覆盖范围

| 脚本 | 当前覆盖 |
|---|---|
| [性能](../../tools/fusion_performance.py) · [HPM SRAM](../../tools/fusion_hpm_sram.py) | F103ZE、H743 的 8/16 位访问、32 位跨页 SRAM、RTT、动态 J-Scope 和并发。HPM 有标准 DAP DMI/SBA 的 SRAM 及独立 RTT、J-Scope 执行入口，选 `--transport riscv-jtag` 并省略 ARM 的 tap、slot、idle。当前并发固件只支持 ARM MEM-AP，HPM 并发需要 RISC-V 数据面。 |
| [启动和 RTT 终端](../../tools/fusion_boot.py) | 三板运行镜像、初始化标记和进度，以及 RTT 命令往返。烧录、冷复位和 GDB 单步、异常栈及观察点仍有待接入的步骤。 |
| [UART](../../tools/fusion_uart.py) · [SWO](../../tools/fusion_swo.py) | 三板 UART COM 回显、F103ZE 真实 ITM、H743 TIM2/DMA 合成码源。UART 持续独立收、发、全双工，H743 真实 ITM，以及独立码源极限仍需对应脚本或现场设备。 |
| [SPI、ETM 和 USB](../../tools/fusion_acceptance_run.py) | F103ZE SPI1 和 H743 SPI r3 主发持续测、H743 接收与全双工有限帧、两块 STM32 的 Golden 和重编 ETM，以及 USB 回环和私有 DDR。ETM SRAM/Fault、F103ZE 接收与全双工、SPI 接收和全双工长窗及流中断恢复按 JSON 的待补项处理。 |

此清单和脚本已做离线校验。每个实板档位和性能上限以本批次取证为准。
