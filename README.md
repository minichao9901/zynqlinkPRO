# zynqlinkPRO

Zynq-7020 CMSIS-DAP：PL SWD/JTAG/RTT/HSS 与并行 ETM，PS USB/OCM 固件，配套 Web/CLI。

| 正式版本 | 目录 | 身份 |
|---|---|---|
| Golden，7020/120MHz，JTAG/RAM | [prebuilt/golden](prebuilt/golden/README.md) | bit `1da17c…` / ELF `e97791…` |
| 已验收 QSPI 恢复包 | [prebuilt/recovery](prebuilt/recovery/README.md) | bit `f02a15…` / ELF `668440…` / BOOT `ee7116…` |

两套均保留原验收字节、来源和SHA-256。本轮精简没有重新综合或编译PL/PS，没有上板或写Flash。恢复包不代表新Golden的QSPI验收。

```powershell
# 明确需要上板时，以下命令只下载到RAM
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/golden/application.elf prebuilt/golden/probe.bit prebuilt/golden/ps7_init.tcl
# 严格离线：不枚举USB、不访问运行服务
python toolbox.py trace doctor --offline
python toolbox.py project list
python toolbox.py project run etm.records-check
python toolbox.py project run sim.cm3 --dry-run -- --top tb_cm3_jtag
```

业务记录只保留F103ZE CDC-ETM最新有效1s和100ms，见[记录清单](docs/retained-records.json)。记录包含原始输入、目标ELF、源码和trace-store；可重建的native.bin已省略。自动测试另保留最小固定哈希夹具。

- [统一CLI](docs/toolbox-cli-ai.md)、[Trace CLI](docs/Trace-CLI使用说明.md)
- [ETM接线/使用](docs/Zynq-ETM-Trace操作说明.md)
- [真实CM3仿真](docs/CM3-target仿真接入-20261028.md)
- [依赖与构建](docs/dependencies.md)
- [验收与限制](docs/F103ZE-Web-CLI-ETM统一验收-20261031.md)
- [精简说明](docs/slimming-20261031.md)

HSS跨功能切换偶发缺首DEF仍按用户要求暂停，保留最小失败/对照证据，未宣称修复。
历史源码、逐轮报告和旧bit/ELF可从Git tag `archive/main-before-slim-20261031`追溯；该tag不含原本未跟踪的业务数据。
