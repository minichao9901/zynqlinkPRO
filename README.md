# zynqlinkPRO

开发接手先读 [AGENTS.md](AGENTS.md)、[项目问题跟踪列表](docs/项目问题跟踪列表.md) 和 [CLI工作台](docs/toolbox-cli-ai.md)。全部文档从[文档入口](docs/README.md)导航，脚本从[工具入口](tools/README.md)发现。发现或处理问题时同步更新问题表并随改动提交。

Zynq-7020 CMSIS-DAP：PL SWD/JTAG/RTT/HSS 与并行 ETM，PS USB/OCM 固件，配套 Web/CLI。

2026-11-05：新增统一探针控制服务与F103ZE ETM环形飞行记录（手动/Fault轮询触发），保留普通窗口路径。原生服务CLI见`toolbox.py --runtime R probe --help`；实现、实际配对、验收范围与交付状态见[统一控制与飞行记录](docs/validation/session-flight-recorder-20261105/README.md)。

本机入口：双击`dist/zynq-etm-bridge/zynq-etm-bridge.exe`，在Web载入ELF、选函数、核对时钟、点击联动采集。请保留完整程序目录及`_internal`；分发ZIP时完整解压再启动。
ETM页面的「教学 Demo」提供离线示例分析、首次联动采集和记录导入三个分步引导；离线示例不需要硬件，真实硬件按钮始终由用户点击。
PLL和AHB/APB分频由target固件负责。CLI用于AI；一条命令打包：
`python toolbox.py bridge-build`（固定更新`dist/zynq-etm-bridge/`，保留数据；仅需分发时加`--zip`）。
保留F103ZE ETMv3和H743 ETMv4能力；H743的SWD/JTAG分档性能及Zynq实板ETMv4连续窗口见 [H743综合报告](docs/validation/h743-comprehensive-20261101/README.md)，[Golden例程](firmware/target/stm32h743_cdc_trace/README.md)默认CPU60/TRACECLK20MHz。

火焰图可导出自包含交互HTML，双击默认打开Timeline，并有周期权重标签页；支持鼠标框选放大、Shift拖动平移及查找；Web、Trace CLI与bridge EXE离线接口共用实现，见 [HTML导出说明](docs/flame-html-export.md)。

2026-11-03：ETM C++ 候选已合入 main；默认静态字典、解码/执行流、完整索引/建库和 TraceStore 读取由 C++ 执行，Python 保留任务/API、身份核验与发布。旧 Python 实现及合并前 main 的固定 tag 保留为 [Golden Reference](docs/etm-golden-reference.md)。固定程序身份和 F103/H743 离线回归见 [主线集成报告](docs/validation/etm-main-integration-20261103/README.md)。Web UI 紧凑布局、WebUSB收敛和ETM教学Demo现已合入，集成验证见 [Web UI主线集成报告](docs/validation/web-ui-main-integration-20261103/README.md)。

2026-11-04：独立缓存/流式ETM研究已按用户决定[归档为参考资料](docs/validation/etm-offline-research-archive-20261104/README.md)，当前暂不采纳；候选源码/程序未并入main，实验worktree已清理。

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

业务记录保留5份：F103旧格式1s/100ms、H743初始化/单次echo 2s、F103 HAL存储1s、最终冻结版手动飞行记录，见[记录清单](docs/retained-records.json)。包含原始输入、目标ELF、源码和trace-store；缺失源码正文的补充来源单独记录，不冒称采集时快照。自动测试另保留最小固定哈希夹具。2026-11-05[工程整理](docs/validation/cleanup-20261105/README.md)将重复记录/回放移入回收站，历史逐轮证据及8个一次性旧脚本固定在tag `archive/main-before-cleanup-20261105`，当前树保留报告、摘要和关键回归输入。

正式PS构建所需BSP、真实CM3模型和main的VexRiscv仿真模型均随Git提供，来源及哈希见[必需依赖清单](docs/required-dependencies.json)。换机需安装对应工具链，详见依赖与构建说明。

- [统一CLI](docs/toolbox-cli-ai.md)、[Trace CLI](docs/Trace-CLI使用说明.md)
- [ETM接线/使用](docs/Zynq-ETM-Trace操作说明.md)
- [真实CM3仿真](docs/CM3-target仿真接入-20261028.md)
- [依赖与构建](docs/dependencies.md)
- [验收与限制](docs/F103ZE-Web-CLI-ETM统一验收-20261031.md)
- [精简说明](docs/slimming-20261031.md)

2026-11-02：用户恢复定位后，HPM6800EVK缺首DEF已由PS USB DATA0复位修正，CDC字节缺口由本机连续大块接收修正；100轮首包与新EXE24步随机通过。实际修复配对在prebuilt/hpm6800-usb-fixed-133-20261102，详见[R23](docs/validation/hpm6800-def-cdc-fix-20261102/README.md)。旧Golden字节保留，临界HSS波动与span显示警告另列，历史暂停报告不改写。
历史源码、逐轮报告和旧bit/ELF可从Git tag `archive/main-before-slim-20261031`追溯；该tag不含原本未跟踪的业务数据。

2026-11-04：新增精英板F103ZE [HAL SPI Flash / EEPROM Trace例程](firmware/target/stm32f103_hal_storage/README.md)及[实际目标ELF](prebuilt/targets/f103ze-hal-storage-20261104/README.md)。真实读写后恢复原外设内容；同一实际输入新旧完整60表/182查询一致。普通Web断点回归、HSS持续接收及STAT/回放修复和性能/剩余失败见[合并后真机报告](docs/validation/main-web-hardware-20261103/README.md)。

2026-11-04：ZL-111/112/115 的请求边界、AP恢复错误传播和有界等待已修复；[实板验收](docs/validation/probe-safety-111-112-115-20261104/README.md)覆盖故障注入及F103 SWD/JTAG、RTT/HSS/调试与CLI/固定Web ETM。实际[bit/双ELF配对](prebuilt/probe-safety-111-112-115-20261104/README.md)随源码交付；正式镜像无注入开关，仅RAM加载，未固化QSPI。

2026-11-05：ETM“报告”更新DDR/飞行记录与离线性能Profile，烧录器新增“固件字节 / ELF解析”两个只读Tab；见[使用与验收](docs/validation/report-firmware-inspector-20261105/README.md)。
