# STM32H743 CDC / ETMv4 Golden例程

本工程目标程序入口，从 `E:/superlinkPRO/etm/firmware/stm32h743_cdc_trace` 复制；原始说明保存在 `README.upstream.md`、`VARIANTS.upstream.md`，其中Kingst/旧路径/历史验收不能当作Zynq结论。旧的 `etm-service/firmware/stm32h743_cdc_trace/` 保留固定提交的历史来源快照；新的构建和Golden以本目录为准。

板型为阿波罗STM32H743，HSE25MHz、外部VDD33USB、目标CDC VID/PID `F055:7431`；PE2=TRACECLK、PE3～PE6=D0～D3，SWD/JTAG和Trace须共地。目标固件自行设置PLL/AHB/APB/USB，采集端不替固件改PLL。

## 构建与烧录

在仓库根目录运行，依赖ARM GCC；必要SDK子集及许可证已随本目录保留，不再依赖另一工程的绝对路径。

```powershell
python -X utf8 toolbox.py project run target.h743-build -- -CoreMHz 60 -TraceR 12 -BannerEveryMs 20 -OutputDir build/h743-new -NoPublish
# 默认参数也是CPU60/HCLK60/TRACECLK20，周期banner20ms。
# 只显示烧录计划：
pwsh -File firmware/target/stm32h743_cdc_trace/flash.ps1 -Elf build/h743-new/fw.elf
# 确认目标程序可替换且已备份后，真正擦写目标Flash：
pwsh -File firmware/target/stm32h743_cdc_trace/flash.ps1 -Elf build/h743-new/fw.elf -Execute
```

`-CoreMHz 60 -TraceR 8` 为30MHz TRACECLK诊断档；本次Zynq接线未通过，不能作为Golden。`-CoreMHz 480 -TraceR 24` 为CPU480/HCLK240/TRACECLK20的独立吞吐配置，不能把其结果混入CPU60的历史ETM比较。供电/VOS、Flash等待周期随例程设置，其他芯片修订和板型须单独核对。

输出 `fw.elf/bin/hex/map/symbols/disasm`；交付目录为 `prebuilt/targets/stm32h743-cdc-trace-20261101/`，各档身份和验收范围见manifest及 [综合报告](../../../docs/validation/h743-comprehensive-20261101/README.md)。默认不复制历史频率变体二进制。

## 采集与测速

先加载并独立核对探针bit/PS ELF，再烧录和逐段读回匹配目标ELF。实板采集例子：

```powershell
python -X utf8 toolbox.py trace capture --elf prebuilt/targets/stm32h743-cdc-trace-20261101/cpu60-trace20/fw.elf --bit prebuilt/fclk133-release-20261101/probe.bit --zynq-elf prebuilt/fclk133-release-20261101/application.elf --out build/h743-capture-new --seconds 1 --swd-khz 10000 --gpio-speed 2
python -X utf8 tools/validate_h743_performance.py --phase sram --out build/h743-sram-new --bit prebuilt/fclk133-release-20261101/probe.bit --elf prebuilt/fclk133-release-20261101/application.elf
```

测速phase还包括 `rtt`、`hss`，不会自动烧录目标；每次用新目录、独占板卡。H743原生CLI目前支持连续DDR USB窗口，明确拒绝F103专用entry/reset选项；Web的H7起点流程仍是独立路径，不能把CLI通过扩展为Web全流程通过。ETMv4配置读取实际IDR，开启返回栈/周期计数、关闭分支广播；SWD仅用10MHz控制。

RTT高带宽测试使用AXI SRAM `0x24040000` 的临时RAM producer，完整备份/恢复20KiB与核心寄存器，并要求D-cache关闭。例程I-cache开、D-cache关；SDK的GCC `at` 属性警告已保留，实际 `_SEGGER_RTT` 位于 `0x24000cf4`，不能沿用链接脚本注释所称的固定DTCM地址。`g_trace` 为 `0x20003000`，ready只表示USB初始化返回，不证明主机枚举；程序RTT满后非阻塞丢弃日志，CDC继续回显。

发现问题或能力边界变化时同步更新 [项目问题跟踪列表](../../../docs/项目问题跟踪列表.md)，本轮关联ZL-011、060～070。没有进行QSPI写入。
