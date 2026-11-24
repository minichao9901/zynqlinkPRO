# E:\zynqlinkPRO-efficiency 协作规则

适用于此 worktree。项目说明见 [README](README.md)，文档与验收入口见 [工程索引](docs/README.md)。

## 开工与验收入口

- 先看 `git status --short`、`git log -5 --oneline`，确认 worktree、分支和在途修改。明确本轮板卡、功能、性能及交付范围，保留其他任务的修改和生成物。
- 新融合 bit/PS ELF 的三板验收按 [融合验收手册](docs/selectio/fusion-acceptance.md) 执行。用 `python -X utf8 toolbox.py project run fusion.accept -- list` 查询 [acceptance-cases.json](acceptance-cases.json) 的必验项和脚本覆盖。探针回归、诊断与历史记录用 `project case <用例ID>` 查询。用 `project describe` 或底层 `--help` 核对入口。用 `project run --dry-run` 离线预览参数。
- 融合工程的通用参考配对为 RAW4 ABI 2。按用例显式指定 `--pair`。在动硬件前核对实际加载配对和启动方式。`serve --j7` 使用命令的正式 J7 默认配对，融合版或 QSPI 实物现场按实载 bit/PS ELF 声明。
- [板卡验收与交付](docs/板卡精简验收与交付.md)规定三板标准工作台回归和跨页压力。标准 `board.accept` 与融合 `board.accept --selectio` 分开取证，后者当前只支持 F103ZE。按用例预览，按脚本要求用 `--execute` 实际操作，`--review` 汇总结果。每轮保留数据，可恢复的失败继续，恢复未确认时剩余项记为阻塞。
- 本机工作台使用独立 `--runtime`，服务仅绑定本机，运行时令牌留在本机。页内操作先用 `page <页面> describe` 发现。操作后核对状态、数据质量、日志和恢复。共享 Web 驱动改动后执行 `tools/sync_etm_shared.py --check`，必要时同步两份驱动。按影响范围选 CLI、Web 或离线 Trace 回归。
- [构建、工具链、加载和发布](docs/README.md#配对与手册)记录具体入口。部分旧 `validate` 会写目标 Flash。历史报告中的 `.py.txt` 和 `.tcl.txt` 只供复查，实板用当前确认的入口。

## 硬件和性能取证

- 核对探针、USB 序列号、目标板、当前 COM、实际 bit/PS ELF 和目标 ELF。J7 与 SuperLinkPRO 并接时按任务指定身份。报告中的板上状态带有时间，切换工作树或运行目录后重新核对。
- 单板操作串行执行。先查占用及采集、DDR、DMA 状态。只停止本任务进程，保留共享 `hw_server` 和其他会话。上板、写入、更新安装和发版按本轮授权执行。
- 默认保持目标 PLL、AHB/APB、Flash 和 QSPI。备份并核对临时 SRAM、核心寄存器、AFIO、时钟和 Trace 配置的恢复，记录最终运行或暂停状态。失败按实际条件保留，避免用重刷、复位或降频覆盖原现场。
- F103ZE **后续性能验收使用 HCLK128**，仅在已授权的临时 SRAM 夹具中执行。核对 RCC 和 DWT，记录实际链路、运行态和恢复。CDC48 用于功能回归及 ETM 基线。HCLK72 及历史 HCLK96（含 4.0 MB/s 对照）分别保留各自条件。用例见 [F103ZE 入口](docs/README.md#从任务找入口)。
- H743 的 ETM 与吞吐按各自目标时钟、ELF 和缓存状态取证。记录 SRAM/RTT 实际使用的 AXI 或 DTCM，内存访问和备份兼容 1 KiB TAR 回绕。原生 ETM 使用连续 DDR USB 窗口，F103 专用 entry/reset 仅用于 F103。历史 JTAG 1/10 MHz 支持 SRAM/RTT，当 FCLK 低于 24 MHz 时 HSS 无法启动。按[同板复验](docs/validation/h743-cdc-golden-requal-20261123/README.md)和 [HCLK 对照](docs/validation/h743-hclk-ab-20261123/README.md)核对条件。
- ETM 业务按低频 SWD 取证，默认 10 MHz。`trace capture --elf` 指目标 MCU，`--zynq-elf` 指探针 PS，`--swd-khz` 用 kHz，底层 Trace Web 的 `--swd-hz` 用 Hz。150 MHz FCLK 和 36 MHz TRACECLK 等研究按用户暂停范围保留。高频 ETM 与 RTT 并发按本轮任务范围取证。
- DDR/OCM 身份经物理 MEM-AP0 核对。完整 Trace 窗口、执行流和逐线校准分别保留证据。性能对比固定配对、目标固件及时钟、事务、队列、窗口及重复次数，记录实际 FCLK/SWCLK/TCK 和来源，区分寄存器折算与实测。控制、硬件窗口、下载、解码、索引和首屏分开报告。

## 问题、证据和交付

- 问题、失败验收、修复、复现和能力边界变化及时登记 [问题表](docs/项目问题跟踪列表.md)，随改动提交。沿用已有编号，记录编号、优先级、状态、触发条件、影响、处理、证据日期和报告路径。根因未定时标为待定位。关闭依据为实际修复和对应验证。保留失败及对照证据和用户暂停状态。
- [验收索引](docs/validation/README.md)指向现有证据。历史报告保留当时结论。出现差异时查更新证据及其配对。保护 `build/` 的独有原始记录、恢复备份和共享输出。清理与暂存均逐项确认，按[保留约定](docs/validation/build-retention.md)处理。
- 每完成一阶段，核对 diff 和问题表，完成对应验证后独立提交。交接按授权范围明确远端 main、固定 EXE、Pages、Release、QSPI 冷启动的结果，并附证据或状态。固定桌面程序更新通过 `toolbox.py bridge-build`，用候选验收后更新并保留用户 `data/`。推送和发布须在本轮授权内。
- PL 实现和路由默认 **133.333333 MHz（7.5 ns）**，120 MHz 对照需明确授权。RTL、PS 固件及相关构建配置变更后的交付，必须生成、验收并提交实际配对的 bit/ELF，记录源码提交、构建选项、SHA-256、时序和上板结果。默认放版本化的 `prebuilt/`，明确选中的 bit/ELF 也可存于 `build/` 或 `releases/`。目标 MCU 镜像另见[各板 images](firmware/target/README.md)。
- JTAG/RAM 临时加载与 QSPI 实体冷启动单独签收。固定启动包见 [prebuilt/qspi-release](prebuilt/qspi-release/README.md)，历史回退和实验配对见[产物索引](prebuilt/README.md)。构建或验收失败时保留已知可用配对，未完成的验证按实际状态记录。
