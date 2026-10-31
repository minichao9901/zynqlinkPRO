# ZynqDAP Web 统一 CLI

入口为根目录 `toolbox.py`，参考 `E:\superlinkPRO\toolbox.py`，覆盖本仓库九页。
Web 操作由本机队列交给真实页面执行；`trace` 转交本仓库 ETM CLI。

## 启动

```powershell
python -X utf8 toolbox.py --help
python -X utf8 toolbox.py catalog
python -X utf8 toolbox.py catalog --full
python -X utf8 toolbox.py --runtime build/toolbox-001 serve --port 8878
```

运行时目录须不存在。在 Chrome/Edge 打开服务输出的完整 `browserUrl` 并保留页面。
同一端口提供工作台、`/etm/`、`/etm/api/`、`/trace-cli/`，避免跨源 iframe
阻断 CLI 和探针互斥。无需另起静态站和8766服务。端口被占用或被 Windows 保留时，
换一个空闲端口和新的运行时目录。Ctrl+C 停止服务，重启使用新运行时。

首次 USB/串口/HID 授权须在真实浏览器完成一次；CLI click 不生成用户手势。
先点页面连接按钮选择 ZynqDAP，之后 CLI 可复用授权。内置浏览器若不显示设备
选择器，请使用 Edge/Chrome 和新服务运行时；一个服务只接受一个执行页面。
令牌和运行时不可提交 Git。

## 全部命令

全局参数放在子命令前：`--runtime R`、`--timeout 60`、`--out result.json`（拒绝覆盖）。
stdout 为 JSON；退出码0=请求成功、1=执行失败、2=参数错误；trace 保留自身退出码。

| 命令 | 作用 |
|---|---|
| `catalog [--full]` | 离线九页功能/命令/静态控件清单 |
| `probe-flash [--image-dir DIR]` | 直接经Zynq JTAG备份整片QSPI、固化BOOT.bin、回读校验并验证复位启动；不需要浏览器/runtime |
| `serve --port 8878` | 启动统一 Web、ETM 后端与本机队列 |
| `ping` / `status` | 执行器就绪 / USB授权和调试、ETM状态 |
| `page P describe [--target T]` | 当前控件、选项、公开方法、targets、停止白名单 |
| `page P state` / `show` | 页面文字和摘要 / 切换页签 |
| `page P read SELECTOR` | 读取值、文本和 disabled 状态 |
| `page P set SELECTOR JSON` | 设置并触发 input/change，复选框用 true/false |
| `page P click SELECTOR` | 点击唯一且未禁用的控件 |
| `page P interrupt SELECTOR` | 长任务期间点击白名单停止按钮 |
| `page P invoke METHOD [--target T] [--args JSON / --args-file F]` | 等待原页面方法返回 |
| `page P event SELECTOR TYPE [--data JSON]` | 键盘/鼠标/指针/滚轮/输入事件 |
| `page P upload SELECTOR FILE... [--directory]` | 向 file input 上传文件或源码目录 |
| `page P wait SELECTOR --contains TEXT` | 等待控件文本 |
| `page P downloads` | 列出当前页捕获的 Blob 导出 |
| `page P download ID FILE` / `discard ID` | 分块落盘并计算 SHA-256 / 释放暂存 |
| `request F.json` / `batch F.json` | 单条请求 / 顺序执行，首个失败停止 |
| `job ID` / `ack ID` | 查询任务 / 删除已完成结果 |
| `trace ...` | `etm-service/trace.py` 全部命令 |

P 为 `serial terminal rtt rttcdc scope flash dbg etm gen`。
T 以 describe 返回为准：通常为 view/session；RTT转发另有 hid；
ETM 另有 target（目标控制）和 history（执行流、分析与导出）。
隐藏 file input 通过 describe 中的 `@file:view.属性名` 访问。invoke 不接受私有方法、
任意对象路径或 eval。参数需要文件时用 `{"$file":"E:/path/fw.elf","kind":"buffer"}`，
kind 支持 file/buffer/bytes；复杂 JSON 推荐 --args-file，避免 PowerShell 引号问题。

## 各功能的验证路径

以下 R 替换为服务的运行时目录：

```powershell
python -X utf8 toolbox.py --runtime R ping
python -X utf8 toolbox.py --runtime R page dbg describe
python -X utf8 toolbox.py --runtime R page dbg invoke connect
python -X utf8 toolbox.py --runtime R page dbg invoke runLine --args '["halt"]'
python -X utf8 toolbox.py --runtime R page dbg invoke runLine --args '["r"]'
python -X utf8 toolbox.py --runtime R page dbg invoke runLine --args '["c"]'
python -X utf8 toolbox.py --runtime R page dbg invoke disconnect
```

| 页面 | 实板验收内容 |
|---|---|
| serial / terminal | 授权端口、连接、接收、发送、终端共享会话、保存、断开 |
| dbg | 连接F103ZE、匹配ELF、暂停/继续/单步、寄存器/内存、断点、变量、断开 |
| rtt | 匹配固件控制块、通道发现、上下行、停止、数据质量 |
| rttcdc | HID配置、RTT→CDC接收、停止、质量报告、切回普通串口 |
| scope | 匹配ELF变量、真实采样、触发、停止、CSV导出、质量与会话释放 |
| flash | 上传目标ELF、STM32F1、编程+校验+复位，读取 #f-result 和 #f-log |
| etm | 下述完整流程，必须核对质量和导出文件 |
| gen | 参数、生成、文件预览和下载 |

RTT/J-Scope 需要目标固件提供控制块/变量，ETM样例固件不等于RTT测试固件。
切换目标固件后重新载入匹配 ELF，记录固件 SHA-256。

## ETM：CLI 控制 Web 的完整流程

加载配对与限制见 [ETM操作说明](Zynq-ETM-Trace操作说明.md) 和 [Trace CLI](Trace-CLI使用说明.md)。

### 本地服务采集（无需浏览器设备授权）

适用于CLI驱动当前已连接F103ZE。先通过JTAG加载实际bit/ELF配对，再在serve声明相同文件：

```powershell
python -X utf8 toolbox.py --runtime build/native-web-001 serve --port 8878 --bit B.bit --zynq-elf P.elf
python -X utf8 toolbox.py --runtime build/native-web-001 page etm upload '#elf-file' TARGET.elf
python -X utf8 toolbox.py --runtime build/native-web-001 page etm wait '#hse' --enabled
python -X utf8 toolbox.py --runtime build/native-web-001 --timeout 180 page etm invoke captureNative --args-file capture-args.json
```

capture-args.json为位置参数数组：

```json
[{"seconds":0.1,"entry":"cdc_acm_init","resetToEntry":true,"usbReconnect":true,"hclkDiv":4,"gpioSpeed":1,"traceId":2,"swdKhz":1000,"decode":true}]
```

真实Web页面负责发起任务、显示进度、载入记录和分析；本地服务复用原生板卡事务工具，
逐字节核对目标Flash、保存配置/运行状态、配置ETM/TPIU、采集和恢复。服务记录输入配对
的SHA-256，但**声明路径不会自动切换板上固件**。支持F103ZE连续窗口或FPB硬件断点起点；
不传entry/resetToEntry时读取Web当前选中的断点与复位选项。确认PC精确命中后才启用采集，
退出核对FPB、CoreSight和时钟恢复。复位采USB初始化时可选usbReconnect短暂拉低PA12，
避免Windows沿用复位前的USB地址。它只恢复自己触及的GPIO位，不覆盖ETM的GPIOE配置。
本地采集复用同一探针租约，与WebUSB采集互斥；鉴权只接受当前CLI令牌。停止请求等待
当前短窗与现场恢复完成，不强杀硬件事务、不自动重试。恢复未通过时阻止后续采集。
原始数据及acceptance.json在记录的raw/下保留，即使解码失败也不丢证据。

CDC同步激励可加入`serialStimulus`对象：`{"port":"COM34","text":"hello","rounds":4,"intervalMs":10}`。
它先打开真实串口，等待采集就绪标记才发送，记录发送相对时间、回显和SHA-256；失败不重试。
Web串口使用相同接口时须先关闭。精确二进制回显需DTR=true、行尾none。

`serve --native-probe`显式启用真实USB/HID/COM转发；Web的DAP/RTT/HSS解析仍照常执行。
转发只接受本机、同源和当前CLI令牌，不替换navigator，不模拟探针成功。
首次连接清理旧DAP回包；ETM采集与各页共享真实探针所有权。

```powershell
python toolbox.py --runtime R validate capacity --elf TARGET.elf --sources SOURCE_DIR --lengths 0.01,0.1,0.2,1 --artifacts build/capacity-001
python toolbox.py --runtime R validate debug --elf TARGET.elf --rounds 20 --artifacts build/debug-001
python toolbox.py bridge --help
```

validate保留逐步CLI结果和每窗原始ETM、质量、恢复与解码统计。目录必须全新；失败停止，
不自动重放硬件操作。`--case-timeout`默认600秒。`bridge`提供可选OpenOCD本机后端，
烧录完成等待自己启动的后端退出；ELF编程量按可加载Flash段计算。

### TRACECLK与软件滤波实验

```powershell
python toolbox.py trace sweep --target-elf TARGET.elf --bit PROBE.bit --zynq-elf PROBE.elf --cpu-mhz 48 --out build/frequency-001
python toolbox.py trace sweep --target-elf TARGET.elf --bit SAMPLE.bit --zynq-elf SAMPLE.elf --cpu-mhz 48 --raw-samples --out build/raw-001
python toolbox.py trace samples --capture build/raw-001/cpu48-div1-gpio1-r1 --elf TARGET.elf --out build/filter-001
```

sweep不会加载bit/ELF，运行前须明确JTAG加载；每次核对目标Flash与ELF，并从RCC读取实际
SYSCLK/AHB分频，板级HSE默认8MHz。默认3轮、两种GPIO驱动档、AHB /4 /2 /1、10ms窗口。
可用`--divs`、`--gpio`、`--rounds`、`--milliseconds`指定有限实验。失败样本保留，只有恢复
通过才继续下一项；`sweep.json`逐项accepted才表示那一项通过，程序退出0只表示矩阵执行完。
实时字节采集使用正式执行流配对；`--raw-samples`必须加载RAW_DIAGNOSTIC=3专用配对。

samples对同一份五线样本分别运行不滤波、因果三点多数和逐线两点稳定滤波，各扫四个取样
相位和两种半字节相位，严格TPIU解复用后用OpenCSD解码。输出包含所有失败、初始未同步
字节、边界和字节SHA，不修补ETM字节。依赖numpy/pyelftools与仓库原生解码器。该短窗实验
不能直接证明连续采集可靠性；样本只持续约0.975ms，可能缺少I-SYNC而解不出执行路径。

### 本地服务依赖与压力入口

```powershell
python -m pip install -r etm-service/requirements.txt
python toolbox.py fixtures rtt --out prebuilt/NEW_RTT_DIR
python toolbox.py fixtures scope --out prebuilt/NEW_SCOPE_DIR
python toolbox.py --runtime R validate rttcdc --elf prebuilt/NEW_RTT_DIR/fw.elf --stream-seconds .5 --artifacts build/rtt-web-001
python toolbox.py --runtime R validate scope --elf prebuilt/NEW_SCOPE_DIR/fw.elf --periods 100,20,10,5,2 --stream-seconds 1 --artifacts build/scope-web-001
python toolbox.py --runtime R validate scope --elf prebuilt/NEW_SCOPE_DIR/fw.elf --scope-channels 8 --periods 100,50,25 --observe-clock --artifacts build/scope-eight-001
```

fixtures固定构建F103ZE额定72MHz，保存源码与ELF哈希。stream验收会通过Web桥实际烧录所给
ELF；结束后需用Web烧回业务固件。RTT逐条检查序号、回退和字节对账，J-Scope导出真实CSV并
检查计数值及流质量。包含失败的矩阵不会标为通过；实测结果以统一验收文档为准。

`rttcdc`使用公开的`captureWindow({seconds,maxMiB})`记录有限原始窗口，默认32MiB上限，
返回实际时长、字节数、是否完整和是否超限，并生成可download的二进制Blob。
它独立于2MiB显示历史，可验证3秒的高速序号流。RTT Viewer的`saveRaw()`导出有界原始历史；
`save()`按当前显示模式输出可读内容，终端模式保留终端滚动历史语义。
`--observe-clock`在流仍活动时经PS JTAG读回FCLK与SWD divider，不暂停F103目标。

打开ETM历史应使用`page etm invoke openRecord --args '["capture-..."]'`，它同步记录选择框和分析器。
`history.load`是低层阅读器方法。`history.zoomRange(true/false)`、`backRange()`、`setRange({start,end})`
和`exportFlame({mode:"aggregate",weight:"records",rootPath:""})`可直接通过`--target history`调用。
切换火焰图后源码跟随会按可见几何位置定位选中行。

serve使用Waitress的HTTP/1.1连接复用，避免高频本机RPC耗尽Windows动态端口。
本地传输相同请求ID只执行一次；结果缓存过期拒绝重放。100000请求达到会话上限后，
需先停止硬件任务再重新启动服务。普通WebUSB不经过此服务。
页面刷新保留本会话身份；重新打开时换用自己的新OS句柄并返回generation，旧请求不能关闭新句柄。
FPGA重载后重新连接即可，不需要拔插数据线或强杀其它应用。

### WebUSB采集（首次需要浏览器授权）

1. `page etm describe`，向返回的ELF控件 upload 目标ELF，等待标签更新。
2. 首次在页面连接探针授权，后续复用授权连接；填板级 HSE=8 MHz。
3. 读取时钟，选择业务断点和采集起点，核对实际 HCLK/TRACECLK。
4. 配置并暂停，设时长（建议从50 ms开始），点击联动采集。
5. 读取 job/日志，直到采集和解码结束；核对 source ID 2、字节数、同步、结束包、
   FIFO/USB loss、FCLK/TCK、OpenCSD错误和 gaps。
6. `page etm describe --target history`，使用公开方法查看执行流、热点、调用树/火焰图；
   导出 CSV/SVG/记录包，通过 downloads/download 保存并记录 SHA-256。
7. 恢复 trace 配置、断点和目标运行状态，断开ETM，切回调试器确认探针可复用。

批处理字段在根对象，不嵌套在 args 中：

```json
[
  {"action":"workbench","page":"etm","op":"read","selector":"#job-state"},
  {"action":"workbench","page":"etm","op":"describe","target":"history"}
]
```

## 结果、恢复与边界

`ok:true` 代表队列请求成功执行。click/set/upload/event 返回 `completed:false`，
页面仍可能异步失败；invoke 返回 `verificationRequired:true`，原方法可能捕获了错误。
必须读取页面日志、业务结果和质量。超时不会取消或重试硬件操作，使用返回的job ID查询，
不要重放烧录、写寄存器、复位或采集。长任务用 interrupt 停止。
任务保留一小时、最多200条，长脚本应 ack 已记录结果。batch非事务，不回滚硬件。
导出最多暂存32个，保存后 discard；刷新会清空暂存。单文件上传上限24 MiB。

```powershell
python -m unittest discover -s tools/tests -p 'test_toolbox*.py'
node --test web/tools/selftest/trace-cli-automation.test.mjs
python -X utf8 tools/accept_web_cli.py --runtime R --out build/cli-smoke-001
python -X utf8 toolbox.py trace doctor
```

模拟/离线与实板分开记录；进展和未完成项见
[统一实板验收记录](F103ZE-Web-CLI-ETM统一验收-20261031.md)。

## Zynq 探针 QSPI 固化

```powershell
python -X utf8 toolbox.py probe-flash --dry-run
python -X utf8 toolbox.py probe-flash
# 已固化镜像只回读及复位检查，不擦写：
python -X utf8 toolbox.py probe-flash --verify-only
```

默认使用 `prebuilt/20261031_orbtrace_opt_qspi_7020_120`：本次优化7020/120MHz、50/60MHz SOTA复测通过的bit/OCM固件配对，后续ETM滤波改动未合入。可用 `--image-dir` 指定另一完整启动包；包内BOOT.bin、加载器、bit/ELF和初始化文件由SHA-256清单绑定。变更bit/ELF后需重新生成启动包。

此命令直接使用Windows Xilinx SDK 2018.3（默认 `E:/Xilinx/SDK/2018.3`，可用 `--sdk` 覆盖）、Python及pefile、Zynq FTDI/JTAG，不依赖浏览器或CLI服务。拨码切到QSPI后重新上电；与其他硬件任务错开执行。当前Flash几何只验收了EF4019单片32MiB，命令会拒绝其他型号。

默认先备份整片到新的 `build/probe-flash-时间/`，保存原备份SHA-256后才擦写，随后由SDK校验并独立整片回读，检查镜像及擦写范围外数据，再验证无暂停系统复位后的OCM入口交接。`--out NEW_DIR` 指定新的输出目录，`--backup-only` 只备份。原Flash备份及含备份的build目录保留在本机，不提交公开Git；失败时查看目录内result.json和日志。固化后保留QSPI拨码，按板上复位键即可启动，无需每次JTAG下载。

此配对的PL时序WNS +0.499ns / WHS +0.020ns；OCM占用120976字节，USB/DAP队列未缩小。启动包中包含构建来源与哈希，验收依据见 `docs/validation/orbtrace-qspi-20261031/`。

备份辅助程序会暂时接管探针；`--backup-only`结束时CPU暂停，恢复使用需复位到已有有效镜像或重新加载配对。
