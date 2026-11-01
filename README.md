# zynqlinkPRO

开发接手先读 [AGENTS.md](AGENTS.md)、[项目问题跟踪列表](docs/项目问题跟踪列表.md) 和 [CLI工作台](docs/toolbox-cli-ai.md)。发现或处理问题时同步更新问题表并随改动提交。

Zynq-7020 CMSIS-DAP：PL SWD/JTAG/RTT/HSS 与并行 ETM，PS USB/OCM 固件，配套 Web/CLI。

本机入口：双击`dist/zynq-etm-bridge/zynq-etm-bridge.exe`，在Web载入ELF、选函数、核对时钟、点击联动采集。请保留完整程序目录及`_internal`；分发ZIP时完整解压再启动。
PLL和AHB/APB分频由target固件负责。CLI用于AI；一条命令打包：
`python toolbox.py bridge-build`（固定更新`dist/zynq-etm-bridge/`，保留数据；仅需分发时加`--zip`）。
保留F103ZE ETMv3和H743 ETMv4能力；H743的SWD/JTAG分档性能及Zynq实板ETMv4连续窗口见 [H743综合报告](docs/validation/h743-comprehensive-20261101/README.md)，[Golden例程](firmware/target/stm32h743_cdc_trace/README.md)默认CPU60/TRACECLK20MHz。

2026-11-01：ETM研究成果已合并主线；最佳已验证基线tag为`etm-best-24mhz-ddr-usb-20261101`（F103ZE TRACECLK24MHz、1/2秒DDR＋USB采集及Web压力通过），配对在`prebuilt/etm-ddr-usb-raw4-20261101/`。ELD1/36MHz研究仍未通过高频验收；详见[主线合并与最佳基线](docs/ETM主线合并与最佳基线-20261101.md)。

| 正式版本 | 目录 | 身份 |
|---|---|---|
| Golden，7020/120MHz，JTAG/RAM | [prebuilt/golden](prebuilt/golden/README.md) | bit `1da17c…` / ELF `e97791…` |
| 已验收 QSPI 恢复包 | [prebuilt/recovery](prebuilt/recovery/README.md) | bit `f02a15…` / ELF `668440…` / BOOT `ee7116…` |

两套均保留原验收字节、来源和SHA-256。本轮精简没有重新综合或编译PL/PS，没有上板或写Flash。恢复包不代表新Golden的QSPI验收。

133.333 MHz实验与普通DAP 50/60 MHz的最新板测见[极限性能与Golden对照](docs/validation/performance-limits-20261101/README.md)；固定133实验仍不是Golden替代品，ETM并发RTT限制单独保留。

ETM配置默认SWD已改为10MHz，USB交接/恢复保持所选档位，本地程序已重建；[1秒ETM端到端1/10MHz对照](docs/validation/etm-e2e-clock-20261101/README.md)显示控制段更快，但完整E2E未测出稳定缩短。

```powershell
# 明确需要上板时，以下命令只下载到RAM
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/golden/application.elf prebuilt/golden/probe.bit prebuilt/golden/ps7_init.tcl
# 严格离线：不枚举USB、不访问运行服务
python tools/verify_dependencies.py
python toolbox.py trace doctor --offline
python toolbox.py project list
python toolbox.py project run etm.records-check
python toolbox.py project run sim.cm3 --dry-run -- --top tb_cm3_jtag
```

业务记录只保留F103ZE CDC-ETM最新有效1s和100ms，见[记录清单](docs/retained-records.json)。记录包含原始输入、目标ELF、源码和trace-store；可重建的native.bin已省略。自动测试另保留最小固定哈希夹具。

正式PS构建所需BSP、真实CM3模型和main的VexRiscv仿真模型均随Git提供，来源及哈希见[必需依赖清单](docs/required-dependencies.json)。换机需安装对应工具链，详见依赖与构建说明。

- [统一CLI](docs/toolbox-cli-ai.md)、[Trace CLI](docs/Trace-CLI使用说明.md)
- [ETM接线/使用](docs/Zynq-ETM-Trace操作说明.md)
- [真实CM3仿真](docs/CM3-target仿真接入-20261028.md)
- [依赖与构建](docs/dependencies.md)
- [验收与限制](docs/F103ZE-Web-CLI-ETM统一验收-20261031.md)
- [精简说明](docs/slimming-20261031.md)

HSS跨功能切换偶发缺首DEF仍按用户要求暂停，保留最小失败/对照证据，未宣称修复。
历史源码、逐轮报告和旧bit/ELF可从Git tag `archive/main-before-slim-20261031`追溯；该tag不含原本未跟踪的业务数据。
