> 2026-11-01：本目录保留迁入时的固定来源快照。当前自包含构建、H743 Golden及实板结果转到 [firmware/target/stm32h743_cdc_trace](../../../firmware/target/stm32h743_cdc_trace/README.md)。下文的“未找到SDK/未烧录/待验”是历史状态，不代表当前结论。

# H743 CDC / ETMv4 换板用例

从superlinkPRO固定提交迁入源代码、链接脚本、CherryUSB及其许可证、构建辅助模块。
逐文件来源/SHA见`source-provenance.json`。迁入的是target程序，不是Zynq PS固件。
`README.upstream.md`和`VARIANTS.upstream.md`为原始历史说明，其中Kingst采样率、滤波、
旧绝对路径和频率验收不能当成本仓库Zynq链路结论；旧频率变体二进制未迁入。

本例为阿波罗H743板：HSE25MHz，外部VDD33USB，目标CDC VID/PID=F055:7431，
PE2为TRACECLK，PE3～PE6为D0～D3，接收端须共地。其他板按原理图核对。
CPU、PLL1R/TRACECLK、AHB/APB和USB PLL3由固件配置；Web只读回核对。

## 构建（AI操作，不烧录）

外部ARM GCC和兼容H743 SDK仍是依赖。SDK须包含`Drivers/`、`Core/`、
`RTT_TRACE_LOG/`和`stm32h743xx.h`，不能用只有H7B0头文件的SDK冒充。
迁入后未找到本机完整H743 SDK，因此本次未完成目标编译，也没有烧录H743。

```powershell
python toolbox.py project run target.h743-build -- -CoreMHz 60 -TraceR 12 -UsbSupply External -Gcc ARM_GCC_EXE -SdkRoot H743_SDK_DIR -OutputDir NEW_OUTPUT_DIR -NoPublish
```

该显式档位为CPU/HCLK60MHz、TRACECLK20MHz；`-TraceR 8`为TRACECLK30MHz。
这些是构建计算值，换板后仍须核对实际RCC和板上晶振。先低频短窗，再逐档验收。
脚本保留上游参数默认值，AI必须显式传CoreMHz/TraceR，不应依赖上游480MHz默认档。
产物为fw.elf/bin/hex、map、符号和反汇编；NoPublish避免覆盖其他目标镜像。
源代码变更后必须重新构建并使用与板上程序完全匹配的ELF，不能沿用历史记录的ELF。

## Web验收

用户双击bridge EXE，在Web载入匹配ELF/源码，连接H743，填写HSE25MHz，
添加自己的循环函数或`trace_hook_entry`。后者在CDC初始化前，仅首次执行，需选先复位。
选择10ms，保留服务端联动和自动解码，检查同步、结束、丢失、ETMv4包错误和入口恢复。
再验证CDC原样回显、换函数采集、火焰图缩放和SVG自动下载。

原生C++/TraceStore离线参考位于`tools/tests/fixtures/h743-etmv4/`；
它与本次源码构建不是同一产物身份，不作对应声明。
Zynq接H743的真机采集仍待用户换板后验收。

完整操作及接线见仓库`docs/Zynq-ETM-Trace操作说明.md`。
