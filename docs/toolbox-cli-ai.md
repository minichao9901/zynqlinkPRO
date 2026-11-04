# CLI工作台

统一本机探针控制：`toolbox.py --runtime <目录> probe status`读取队列/资源/错误状态，不访问板卡；`probe cancel --owner <会话ID>`取消排队或请求在运行操作边界退出；`probe call usb|hid|serial <动作> --file <JSON>`调用公开服务协议。后两者可能影响硬件，不能用作离线检查。原生服务不需要浏览器worker，沿用鉴权令牌、owner与resourceEpoch，失败不自动重放。跨进程锁及ETM恢复交接见[统一控制验收](validation/session-flight-recorder-20261105/README.md)。

新会话先读根目录 [AGENTS.md](../AGENTS.md) 和 [项目问题跟踪列表](项目问题跟踪列表.md)。发现、复现、修复或变更问题状态时，同步更新该表，随相关改动提交。

CLI用于AI自动化；用户直接双击`zynq-etm-bridge.exe`，在Web完成选ELF、选函数、配置与采集。
PLL、AHB/APB分频属于target固件，生产Web/API与Trace capture CLI不再设置AHB分频。

## Windows桥包构建与离线验收

```powershell
# 构建机：已验证Windows x64 / Python 3.13，依赖见requirements-bridge-build.txt
python -X utf8 toolbox.py bridge-build
# 仅需分发时额外生成ZIP：
python -X utf8 toolbox.py bridge-build --zip
# 包含冻结EXE自身预检；完整回归用独立新目录，明确禁用所有硬件接口：
python -X utf8 toolbox.py project run bridge.verify -- --package dist/zynq-etm-bridge --out build/bridge-check-new
```

固定本机目录是`dist/zynq-etm-bridge/`，包含EXE和`_internal`运行库。默认不生成ZIP；加`--zip`时才额外生成分发包，不带用户data、记录或令牌。分发包需完整解压，不能只复制EXE。
候选完成冻结预检和离线验收后，更新器保留data、归档旧程序，再替换固定目录；失败可回滚。它不是无条件拒绝更新已有合法程序目录。单独验收的输出目录必须新建；manifest保存源码提交、依赖版本、文件SHA，预检子进程PATH无Python/Node。
默认双击直接打开Web，数据放EXE旁`data/records`。AI可用`--data-dir`隔离测试数据；
`--offline`明确拒绝USB/HID/串口及采集，只允许导入/解码/浏览。保留H743 ETMv4与F103ZE ETMv3。

## 项目工具

入口python toolbox.py，Web与非Web工具统一从project list/describe/run访问。索引来自当前Git跟踪源码，历史实验已退出活跃列表；旧371项是归档版本的计数。

```powershell
python toolbox.py --help
python toolbox.py project list
python toolbox.py project describe probe.regression
python toolbox.py project run sim.cm3 --dry-run -- --top tb_cm3_jtag
python toolbox.py project run web.check
python toolbox.py project run test.web
python toolbox.py project run test.cli
python toolbox.py trace doctor --offline
```

run默认执行底层工具并保留退出码；只看计划必须用--dry-run，底层参数放在--后面。list/describe/--dry-run不操作板。
Trace原始CLI见 [Trace-CLI使用说明.md](Trace-CLI使用说明.md)。页内控制、串口/调试/RTT/J-Scope/烧录命令先用`toolbox.py page --help`与`page <页面> describe`查询；其硬件动作不能用作离线检查。

需要启动工作台时用serve子命令，每次使用新的runtime目录。启用本机硬件通路时，显式声明实际已加载配对；下面以release133为例，不要求所有任务强制使用Golden，也不会自动下载所声明文件：

```powershell
python -X utf8 toolbox.py --runtime build/workbench-new serve --port 8878 --native-probe --bit prebuilt/fclk133-release-20261101/probe.bit --zynq-elf prebuilt/fclk133-release-20261101/application.elf
# 浏览器打开服务打印的鉴权URL后，在另一终端查询公开页内方法：
python -X utf8 toolbox.py --runtime build/workbench-new page etm describe --target target
```

serve前须按实际任务核对板卡空闲及加载身份。运行时URL/令牌只限本机使用，不提交Git；旧runtime或已关闭服务的URL不能作为当前worker。`click/set`只确认事件投递，还要检查完成状态、质量和恢复结果。

工作台调试探针后端统一为WebUSB；已移除OpenOCD/J-Link本地桥、`toolbox.py bridge`与工程生成页。`bridge-build`仍用于构建本机Zynq工作台EXE及其ETM/原生USB服务，与已退役的调试后端桥不同。历史板测工具和报告中的OpenOCD引用仅作取证。

### Web频率限制与原生RISC-V研发参数

Web烧录、RTT Viewer、调试器按所选目标限制频率：HPM最高25MHz，其他ARM/RISC-V最高60MHz，提供25MHz档；切到HPM时旧高频选择降至25MHz。HPM RTT自动档显式使用10MHz，避免继承前一次研发高频。Web页CLI操作也沿用这些限制。波形/RTT转发连接并识别为ZynqLinkPro后，RISC-V可显式选择10/20/25MHz TCK，启动时先确认架构再设置并核对时钟ACK；自动档仍10MHz。旧软件探针的RISC-V `clockHz`仍按idle约定保持0，不向未知探针发送Hz。实测方法见[25MHz流对照](validation/web-cli-streams-25mhz-20261103/README.md)。

独立原生研发CLI仍提供高频、idle及采样窗口配置，并未受Web25MHz上限影响：

| 入口（`project run`后的工具ID） | 参数 | 单位/含义 |
|---|---|---|
| `tools/validate_hpm6800_performance.py` | `--speeds`、`--idle`、`--modes` | TCK请求Hz列表、idle拍数0～64、采样模式列表0/1/16/17 |
| `tools/validate_hpm6800_streams.py` | `--stage rtt/hss`、`--speeds`、`--idle`、`--mode` | 同上，mode为单值；HSS另有`--periods`（24MHz ticks）、`--variables` |
| `tools/characterize_hpm6800_idle.py` | `--speeds`、`--idles`、`--modes` | TCK/idle/采样模式的矩阵对照 |

历史限定HPM6800EVK的66.667MHz通过配置为idle22、mode17；mode17是Q1/previous-bit返回窗口，不能只增加idle而忽略采样窗口。大于15拍需要扩展idle的PL/PS配对，66.667MHz还需要相应固件cap与FCLK策略；工具会核对有效idle和实际时钟。详见[历史高频报告](validation/hpm6800-speed-completion-20261102/README.md)。这不是所有HPM型号的频率保证，本次仅核查参数并修改Web，没有重新运行高频测试。

下面只发现/打印计划，不操作板卡；真实执行前仍须核对空闲、加载配对并独立核对OCM：

```powershell
python -X utf8 toolbox.py project describe tools/validate_hpm6800_performance.py
python -X utf8 toolbox.py project run tools/validate_hpm6800_performance.py --dry-run -- --bit prebuilt/hpm6800-jtag66-133-20261102/probe.bit --elf prebuilt/hpm6800-jtag66-133-20261102/application.elf --out build/hpm-cli-high-new --speeds 66666667 --idle 22 --modes 17 --windows axi --loops 128 --repeats 3
```

## DDR研究路径（仅供AI阶段验收）

主流程仍为双击bridge EXE后使用Web。下列命令用于研发验收，不要求用户输入CLI。
先按配对manifest加载并验证指定bit/ELF，再运行；不会自动切换板上固件。

```powershell
python toolbox.py project run etm.ddr-trace-stress -- --pair prebuilt/etm-ddr-usb-raw4-20261101 --out build/ddr-trace-check-new --rounds 2 --seconds 1,2 --cdc-port COM34 --decode --verify-ddr-physical
python toolbox.py project run etm.framed -- captured.frm1 --out build/framed-check-new --tail-bytes 1 --trace-id 2
```

上例DDR压力套件仍只针对F103，默认USB采后下载，1/2秒窗口、函数交替、CDC；可用物理AP0核对同一缓冲。不会写Flash或改目标分频。
H743已有独立ETMv4连续原生capture实板验收：CPU60/TRACECLK20、SWD10MHz，10/200/500/1000ms各三次CDC负载。Golden源代码/SDK在`firmware/target/stm32h743_cdc_trace/`，`target.h743-build`已指向该目录；产物在`prebuilt/targets/stm32h743-cdc-trace-20261101/`。H743原生entry/reset仍拒绝，Web起点/导出另行验证，不能借F103压力套件背书。详见 [H743综合报告](validation/h743-comprehensive-20261101/README.md)。
FRM1原生工具、PS USB采后下载、Web/CLI默认DDR能力分支已完成本阶段真机验证；更高频和逐线校准继续研究。
`web.shared-sync --check`核对ETM共享驱动（当前10份）；`--write`从主工作台同步。web.check与bridge.build都会阻止驱动副本不一致。

火焰图默认提供可离线缩放的双标签HTML导出，默认Timeline，另有周期权重页；左键框选放大，Shift拖动平移，SVG仍保留。源码CLI使用 `trace export --format flame-html`；新bridge EXE使用 `--trace-cli export --record ... --format flame-html --out ...`。Web CLI的 `history.exportFlame` 默认HTML，可用 `format:"svg"` 显式兼容旧格式，保留当前区间及下载捕获。见 [使用说明](flame-html-export.md)。
