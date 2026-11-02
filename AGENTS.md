# 仓库协作规则

本文件适用于整个仓库，供新会话接手。路径均相对仓库根目录；现有文档目录是 `docs/`，不要另建平行的 `doc/`。

## 新会话先读与现状核对

1. 先执行 `git status --short`、`git log -5 --oneline`，辨认已有修改与当前分支；不要覆盖、清理或批量提交他人的工作。
2. 阅读 [README.md](README.md)、[项目问题跟踪列表](docs/项目问题跟踪列表.md)、[CLI工作台](docs/toolbox-cli-ai.md) 和 [Trace CLI](docs/Trace-CLI使用说明.md)。按任务再读对应 `docs/validation/` 报告、交接和产物 manifest。
3. 问题表是当前状态索引，历史报告保留当时结论；若矛盾，追查较新证据及实际配对，不把历史“待验”或单次通过直接当成现状。
4. 任何报告中的“最后板上状态”都是带时间的快照。切换分支/worktree、启动另一目录的脚本或 EXE，都不会自动切换板上 bit/ELF。

## 工程入口与目录

| 路径 | 用途 |
|---|---|
| `toolbox.py` | AI统一CLI入口：工具索引、Web工作台控制、Trace、构建与验收转交 |
| `web/`、`etm-service/web/` | 工作台及ETM前端；共享驱动由 `tools/sync_etm_shared.py` 管理 |
| `etm-service/trace.py` | Zynq原生采集/doctor入口；离线查询、解码、导出转交保留的Trace CLI |
| `etm-service/tools/trace_cli.py` | 完整Trace命令实现；底层参数以各入口的 `--help` 为准 |
| `tools/` | 构建、加载、身份核对、回归和板测脚本；优先经 `toolbox.py project` 发现入口 |
| `fpga/`、`firmware/xusbps_daplink_dma/` | PL RTL/构建及Zynq PS固件；目标MCU源码在 `firmware/target/` |
| `prebuilt/` | 已版本管理的交付或明确命名的实验配对，身份/范围以各 manifest、README 为准 |
| `dist/zynq-etm-bridge/` | 用户本机程序入口；更新由 `python toolbox.py bridge-build` 完成 |
| `docs/validation/`、`build/` | 已归档证据、工作输出；`build/` 可能混有历史/共享缓存，不能整目录删除或add |

## CLI路径与使用方法（必读）

在仓库根目录执行，Windows建议加 `-X utf8`。详见 [docs/toolbox-cli-ai.md](docs/toolbox-cli-ai.md)、[docs/Trace-CLI使用说明.md](docs/Trace-CLI使用说明.md)；依赖/换机见 [docs/dependencies.md](docs/dependencies.md)。不要沿用已退役的 `toolbox.mjs` 或猜测子命令。

### 发现入口与不操作板卡的检查

```powershell
python -X utf8 toolbox.py --help
python -X utf8 toolbox.py project list
python -X utf8 toolbox.py project describe probe.regression
python -X utf8 toolbox.py project run sim.cm3 --dry-run -- --top tb_cm3_jtag
python -X utf8 toolbox.py trace doctor --offline
python -X utf8 tools/verify_dependencies.py
```

`project list/describe` 与 `run --dry-run` 不执行底层工具。`project run` 默认执行，参数放在 `--` 后；每个底层脚本自己的 `--execute`、硬件/浏览器要求仍有效。计划成功、CLI可发现和仿真通过均不等于实板验收。

主机/Web检查可按改动运行 `python -X utf8 toolbox.py project run web.check`、`project run test.web`、`project run test.cli`。修改共享驱动后核对 `python tools/sync_etm_shared.py --check`；需要同步时用 `--write`，再验证，不能只改一份副本。

### Web工作台与Trace

- 用户日常双击 `dist/zynq-etm-bridge/zynq-etm-bridge.exe`。AI需要完整Web流程时，用 `toolbox.py --runtime <新目录> serve` 启动，浏览器打开启动时给出的鉴权URL并保持页面运行；页内方法先用 `page <页面> describe` 发现，不用内部对象猜调用。
- 开启本机硬件路径时加 `--native-probe --bit <实际加载的bit> --zynq-elf <配套Zynq ELF>`；这些参数只声明身份，**不会下载配对**。服务只绑定本机，运行时令牌不能提交Git。
- 对运行中的工作台：`python -X utf8 toolbox.py --runtime <运行目录> page etm describe --target target`。`click/set` 返回投递成功不代表业务完成；还要核对状态、数据质量、日志及恢复结果。
- Zynq原生Trace不必依赖浏览器：先看 `python -X utf8 toolbox.py trace capture --help`。`--elf` 是**目标MCU ELF**，`--zynq-elf` 是**探针PS ELF**，不要混淆。

H743 Golden源代码与自包含SDK位于 `firmware/target/stm32h743_cdc_trace/`，交付目标ELF位于 `prebuilt/targets/stm32h743-cdc-trace-20261101/`；旧 `etm-service/firmware/` 下同名目录是历史来源快照。先读 [H743综合报告](docs/validation/h743-comprehensive-20261101/README.md)。ETM基线为CPU/HCLK60MHz、TRACECLK20MHz；CPU480/HCLK240是独立吞吐配置，不混用其数据。H743原生CLI支持连续DDR USB窗口，拒绝F103专用entry/reset选项。H743控制/备份内存传输必须兼容1KiB TAR回绕；RTT RAM fixture用AXI SRAM并核对cache及恢复。JTAG低频1/10MHz可用于SRAM/RTT，但当前HSS因FCLK不足24MHz不能启动。

```powershell
# 硬件采集示例：仅在已核对/加载配对、确认板卡空闲且任务允许操作硬件后执行。
python -X utf8 toolbox.py trace capture --elf prebuilt/golden/f103ze-cdc48.elf --bit prebuilt/fclk133-release-20261101/probe.bit --zynq-elf prebuilt/fclk133-release-20261101/application.elf --out build/etm-capture-new --seconds 1 --swd-khz 10000
# 已保存记录的离线查询示例，不采集、不烧录。
python -X utf8 toolbox.py trace query --record <记录目录> --view summary
```

ETM配置默认SWD为 **10MHz**，前端、本地采集服务接管和恢复连接保持所选档位。`toolbox.py trace capture` / `etm-service/trace.py capture` 用 **`--swd-khz`（kHz）**；底层 `etm-service/tools/trace_cli.py` 的目标/Web命令用 **`--swd-hz`（Hz）**。不要跨入口照搬单位；显式1MHz对照分别是1000kHz和1000000Hz。

### 构建与加载

- `python -X utf8 toolbox.py bridge-build`：候选先验收，再更新固定 `dist/zynq-etm-bridge/`，保留用户data、归档旧程序。默认不生成ZIP；仅需分发时加 `--zip`。修改主机代码不会自动更新已冻结EXE。
- PL/PS入口、工具链与BSP见依赖文档及 `project describe`；不要直接双击 `docs/validation/` 中的 `.py.txt/.tcl.txt` 历史驱动，它们可能含旧路径和硬件动作。
- 仅JTAG/RAM加载的通用入口：`python tools/run_xsct.py tools/download_dap_fpga.tcl <Zynq_ELF> <BIT> <PS_INIT_TCL>`；随后用 `python tools/verify_probe_ocm_code.py --elf <Zynq_ELF> --out-dir <新目录>` 独立核对运行代码。
- `probe-flash` 是QSPI写入路径，不是普通RAM加载；`validate` 的部分套件也会写目标Flash。先读帮助/实现，不能把它们当离线检查或无Flash回归。

## 问题跟踪必须同步更新

**以后遇到问题、bug、失败验收、复现变化、修复或能力边界变化，必须在同一工作过程中同步更新 [docs/项目问题跟踪列表.md](docs/项目问题跟踪列表.md)，并随相关改动一起提交。不能只留在聊天、终端或未跟踪的build输出中。**

- 先搜已有稳定编号；同一问题更新原条目，不重复建项。新问题即使当场修复，也要登记现象、处理和验证证据。
- 至少填写编号、优先级、状态、模块/触发条件、影响、当前处理/下一步、证据日期/更新日期、报告路径或提交。尚无根因就明确写“待定位”，区分事实与假设。
- “代码已改”“重载后恢复”“未再复现”“仿真通过”不等于问题已关闭。关闭必须写明实际修复及相应验证范围；未上板或缺少设备时保留待验证。
- 用户暂停/排除的项目继续保留相应状态；登记问题本身不授权重新开展已暂停的高频扫描、硬件修改或固化。
- 保留失败/对照证据和原编号，不删除历史来制造全通过；修复说明和交接引用问题编号。只有状态或证据变化时更新日期，不做无意义的每日改写。

## 硬件和验收边界

- 单板操作不能并行抢占；先查占用、采集/DDR/DMA状态，再动时钟或加载。只停止本任务进程，不结束共享 `hw_server` 或其他会话服务。
- 默认保持目标PLL、AHB/APB、Flash和QSPI；需要改变时按任务授权执行，不能用重刷、复位或降频掩盖失败。临时SRAM/核心寄存器/AFIO/Trace夹具必须备份并核对恢复，记录最终运行/暂停状态。
- 已知DAP Golden在 `prebuilt/golden/`，QSPI恢复包在 `prebuilt/recovery/`；`prebuilt/fclk133-release-20261101/` 是限定F103范围的release，不能把RAM加载等同其QSPI冷启动验收。ETM 24MHz研究基线另见 [主线/基线说明](docs/ETM主线合并与最佳基线-20261101.md)。
- 固定133MHz实验 `prebuilt/fclk133-swd-fixed-test-20261101/` 是SWD-only，不能代替正式release；其中60MHz请求实际可落到33.333MHz。测试必须记录实际FCLK/SWCLK/TCK和来源，不只写请求频率；寄存器计算频率不冒充外部频率计实测。
- 当前ETM业务只要求低频SWD配置；高频ETM输出+RTT并发不是产品必验组合。150MHz FCLK/36MHz TRACECLK等已暂停研究不可因新会话而自动重启。
- DDR/OCM身份核对使用物理MEM-AP0，CPU上下文 `mrd -force` 不能保证绕过缓存。包错误为0、FIFO无丢帧或IDELAYCTRL RDY不能单独证明完整窗口、完整执行流或完成逐线校准。
- 性能对比固定配对、目标固件/时钟、事务规模、队列深度、窗口和重复次数；分别报告控制、硬件窗口、下载、解码/索引与首屏。离线时间、估算和旧JSON路径不得冒充当前E2E。

## FPGA bitstream 与 Zynq ELF 必须纳入 Git

- 后续PL实现与路由时序验证默认按 **133.333333MHz（7.5ns）** 约束，除用户明确要求对照外不退回120MHz。约束频率不等于实际FCLK/TCK；运行时仍须记录读回值，不暗改目标MCU PLL。

- FPGA bitstream（`.bit`）和配套 Zynq 固件（`.elf`）是可交付内容，必须提交到 Git，不能仅留在被忽略的 `build/` 目录中，也不能只提交源码或构建说明。
- 修改 RTL、Zynq 固件或影响它们的构建配置后，交付或合并前必须生成并验收对应产物，把实际验收使用的 bit/ELF 配对与相关源码一起纳入版本管理。不得用旧 `prebuilt/` 产物冒充本次构建。
- 默认把当前交付配对放在 `prebuilt/`；需要保留可复测基线或不同方案时，放在独立、有明确版本名称的目录，并记录加载路径。`build/`、`releases/` 中的 bit/ELF 也允许显式纳入 Git，不批量提交其他中间产物。
- 随产物记录源码提交、构建选项、bit 与 ELF 的 SHA-256、时序结果及上板验收结果。记录的哈希必须对应实际提交和加载的文件；仅有提交号或文件名不足以确认产物身份。
- 测速前核对并加载指定版本的 bit/ELF 配对，记录实际 FCLK/TCK。切换 worktree 或运行另一目录的主机脚本不会切换板上固件。
- 构建或验收未通过时，保留已知可用配对，明确报告未完成的验证；不得把失败产物标记为已验收。

## 提交与交接

提交前检查diff与问题表，按改动完成必要验证；文档修改无需为了“验收”重跑硬件。只提交本任务文件，保留无关未提交工作，不批量add/清理build、dist、用户记录或令牌。提交但未要求推送时不推送。

交接写清提交、改动和验证范围、问题编号/未完成项；若使用过硬件，再写实际配对/哈希、时钟、目标状态、恢复结果及是否还有本任务后台进程。不能用本文件中的历史示例推断当前板上状态。
