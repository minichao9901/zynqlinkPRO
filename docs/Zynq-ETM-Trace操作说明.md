# Zynq ETM Web 操作说明

用户双击Windows bridge EXE并操作Web；CLI用于AI自动化、打包和验收。
主流程沿用superlinkPRO，LA接收后端替换成Zynq ETM-LA，保留原生C++解码与TraceStore。

## 启动与停止

完整解压桥包，双击`zynq-etm-bridge.exe`，浏览器自动打开ETM工作台。保留`_internal/`目录。
无需安装Python或Node，不需手输启动命令。数据默认保存在EXE旁的`data/records/`。
关闭桥控制台停止服务；重复双击同版本/同数据目录会重新打开已有工作台。
桥不会给Zynq下载bit/ELF，也不会烧录目标。上板前使用已经加载对应配对的ZynqDAP。
DDR USB研究配对为`prebuilt/etm-ddr-usb-raw4-20261101/`，保留原Golden；只在加载这对文件后验证新路径。

## 1 调试：ELF、源码与函数

点击“采集设置”→“1 调试”，载入与目标Flash完全匹配的ELF。
F103ZE现有Golden目标为`prebuilt/golden/f103ze-cdc48.elf`；H743使用自己的匹配ELF。
展开“配套源码”，选择对应源码目录。ELF导入只供符号、镜像校验和解码，不烧录。
点击“连接探针”，核对芯片识别；首次进入保留原硬件状态，不自动重置目标时钟。
搜索函数并点“＋”，或输入`b cdc_poll`；选断点列表中的圆点作为采集起点。
起点表示从该处开始录制后续窗口，包含被调函数和中断，不是只采该函数。
循环业务函数可取消“先复位，再运行至起点”；只执行一次的初始化函数可勾选复位。
H743可选superlinkPRO例程的`trace_hook_entry`或自己的循环业务入口。

## 2 时钟：只读核对

PLL、AHB/APB分频、CPU和Trace时钟由target固件负责。Web只读取RCC，用户填写板上真实HSE。
“预期频率”只做核对，填写更低数字不会修改实际频率。生产Web/API不接受`hclkDiv`。
F103ZE样例HSE为8MHz，48MHz固件默认HCLK48MHz、物理TRACECLK24MHz。
H743阿波罗Golden例程HSE为25MHz、CPU/HCLK60MHz、TRACECLK20MHz；30MHz在本次Zynq接线下未通过。
H743 Trace时钟和CPU可独立，必须以实际RCC及板级HSE计算，不能套用F103的CPU/2。
如果需要降低TRACECLK，应由target固件构建档位完成，并重新载入新固件的匹配ELF。
H743本轮已验收范围是原生CLI连续DDR USB窗口，详见 [综合报告](validation/h743-comprehensive-20261101/README.md)，不能扩展成Web全部入口已验收。

## 3 采集：全程点击Web

Trace ID先用2。分支广播默认关闭；F103不支持返回栈压缩与周期准确模式，页面会禁用。
H743保留ETMv4分支广播、返回栈和周期计数能力检测、Funnel/ETF/TPIU路由。
点击“配置并暂停”可先检查配置，也可由“联动采集”自动配置。
点击“检查接收端”，确认Zynq ETM接收端在线。
第一次时长选10ms，保留“服务端联动”和“保存后自动解码”，点击“联动采集”。
网页依次校验ELF、命中起点、核对时钟、配置ETM/TPIU、释放USB；本地服务arm FPGA后恢复CPU，
接收结束后交回网页，恢复Trace配置和本页断点。无需用户输入CLI。

当前DDR固件默认在硬件窗口内写入DDR，窗口结束后通过USB下载，再由C++解复用、解码和显示。
可设10/100/1000/2000ms；旧固件仍最多1000ms。采集时长以参考时钟计数核对，下载时间单列。
F103ZE24MHz TRACECLK已完成1/2秒USB与物理数据对照、30次Web开关及10轮100ms换函数采集；
每轮窗口内CDC回显、无丢帧/解码错误。100ms完整Web操作约12.5～14.9秒，尚不能称实时显示。
H743已单独完成20MHz的10/200/500/1000ms原生连续采集；Web换函数起点、首屏/导出仍需单独验证，旧固定EXE未因此自动更新。

Zynq接收必须有数据、已同步、完整结束且无丢失；失败保留原始数据和原因，不算成功。
DDR窗口用硬件参考tick核对，不是逐指令周期时间；legacy主机接收跨度不能证明完整硬件窗口。Web显示实际接收质量，源码映射率不能作为无损证明。
先10ms再100ms；长窗失败时缩短窗口、检查接线，必要时由target固件降低Trace频率。

## 接线

Zynq J7.16←TRACECLK；J7.15/17/18/19←D0/D1/D2/D3；J7.14←GND。
F103ZE的Trace脚为PE2～PE6；H743须按自己的板级引出核对这五根信号。
目标SWDIO/SWCLK/GND仍接ZynqDAP，Trace接收为4位并行DDR。

## 4 分析与导出

新记录自动解码，右侧查看执行流、调用统计、火焰图、热点、ETM包和可信区段。
点击火焰图定位历史源码；不是在线单步，也不提供历史变量值。
“导出当前火焰图SVG”自动下载并显示状态和再次下载链接。
“4 文件”可导出记录包、CSV、源码执行流，或导入`.etmrecord`离线重解码。
桥包examples内有H743真实历史参考记录，来自superlinkPRO的Kingst LA，仅用于离线回归。

## H743换板验收约定

H743继续使用superlinkPRO迁入的目标识别、ETMv4配置、Funnel/ETF/TPIU路由、
C++解码、TraceStore和Web分析/导出；接收设备使用Zynq ETM-LA。
F103专用的ETMv3编程模式重启不用于H743。诊断CSR和后续DDR后端不应按F103协议硬编码。
旧Kingst参考只证明离线回归。本轮H743接Zynq的连续原生CLI采集已单独验收，不能替代完整Web起点流程。
当前自包含target Golden位于`firmware/target/stm32h743_cdc_trace/`，
含源文件、SDK子集、许可证和构建脚本；旧`etm-service/firmware/`同名目录保留历史来源快照。

换板后先核对接线、电平、板上HSE和实际固件，载入其匹配ELF/源码，
选自己的循环入口；初始化入口`trace_hook_entry`需要复位后命中。
首次以target固件提供的低频档、10ms窗口验证，检查实际CPU/TRACECLK、
同步/结束/丢失、ETMv4包错误及采集入口，再逐档增加Trace频率和窗口。
每档记录Zynq bit/ELF与target ELF的SHA、接线、诊断计数和原始记录，
完成反复开关探针、换函数采集、解码、缩放和SVG自动下载后再判定通过。
当前Zynq已验证CPU60/TRACECLK20MHz。30MHz未通过，不能自动重启更高频扫描；Web完整流程通过前仍保留上述检查项。

AI压力工具`toolbox.py project run etm.stress`现支持`--profile stm32h743`，
必须显式提供`--elf`和`--functions`，可设`--sources`、实际`--hse-mhz`及`--reset-before`。
使用`--echo`还必须指定目标`--cdc-port`，避免误用F103端口；
用户仍全程操作Web，不需要执行这些参数。

## AI打包命令

```powershell
python -X utf8 toolbox.py bridge-build
# 同一入口也可使用项目工具别名：
python toolbox.py project run bridge.build
# 仅需分发ZIP时增加：
python toolbox.py bridge-build --zip
```

构建机安装`requirements-bridge-build.txt`；本机默认只输出`dist/zynq-etm-bridge/`一个程序目录。
更新前验收真实冻结EXE，确认F103/H743原生解码、导出和重复启动复用通过；随后保留原`data/`，将旧程序归档到`build/bridge-archive/`。更新失败会恢复原程序。关闭正在运行的桥后再更新。
默认不生成ZIP；`--zip`才额外生成分发包，且只包含程序文件，不打包用户数据、采集记录或鉴权令牌。
包内manifest记录源码提交、依赖版本、文件SHA-256。Golden bit/PS ELF不因打包改变，不包含SDK或Node。
AI离线预检：`zynq-etm-bridge.exe --check --data-dir CHECK_DIR`，不连接目标。
AI界面验收：加`--offline --no-browser`，硬件API明确拒绝，只允许导入、解码和浏览。
实际构建与离线验收结论统一见[F103ZE记录](F103ZE-Web-CLI-ETM统一验收-20261031.md)。
