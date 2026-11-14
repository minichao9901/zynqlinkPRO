# H743 精简验收在目标识别处阻塞

2026-11-14 23:57 至 2026-11-15 00:02（上海时间）。J7 已在线并通过身份与配对核对。目标 SWD 无有效 ACK，JTAG 两个预期 TAP 均返回全零，未能从调试口确认 STM32H743 的身份。目标供电、I/O 参考电平、接线和故障根因需要在台架核对。问题编号 ZL-240。

## 探针身份与建链复测

- 工作台为本机 `toolbox.py serve --native-probe`、隔离 Edge 浏览器、v1.3.8（OpenOCD Wasm，源码模式，未打包）。测试源码提交 `e791818f0c87a401060a470bd9b098d24afbce17`。开测时已有 ZL-006 问题表改动，运行代码无跟踪文件差异。`board.accept` 因工作区标记 `sourceDirty=true`，离线 `--review` 拒绝纳入跨板汇总，原始单板汇总保留。
- 现场唯一探针是 J7 `12345678`，USB/HID 和 COM33 同序列号，XSCT 下载线 `210299008529`。采样模式挑战分别经 USB 发起、物理 MEM-AP0 读回并确认恢复。AP0 验证四个 PL 能力配置寄存器，并核对正式 `0.8-nonce32` 应用 ELF 的 85,716 字节 OCM 执行代码。`BOOT_MODE=1` 且有效 QSPI 启动标记。初始 FCLK 由 AP0 寄存器推算为 99,999,999 Hz。[探针与原始报文](evidence.json)
- 档位计算采用探针 PLL 与分频寄存器报告。连接、时钟配置及 SWJ 选择命令均被探针接受。SWD DPIDR 读请求返回 `05 00 07`，ACK 对应 `0b111`。JTAG 以 IR 长度 4、5 分别读取 CPU 和边界 TAP，两者都返回 `16 00 00 00 00 00`。

| 链路 | 请求 MHz | 实际链路 Hz | FCLK Hz | 目标读回 |
|---|---:|---:|---:|---|
| SWD | 1 | 999,999.983 | 119,999,998 | 无有效 ACK |
| SWD | 10 | 9,999,999.833 | 119,999,998 | 无有效 ACK |
| SWD | 50 | 49,999,999.500 | 99,999,999 | 无有效 ACK |
| JTAG | 1 | 999,999.500 | 1,999,999 | 双 TAP 全零 |
| JTAG | 50 | 49,999,999.500 | 99,999,999 | 双 TAP 全零 |

主动连接时 J7 复位脚数字读回高，发出的操作未包含 NRST 脉冲。脱机时回到高阻输入和路由 0。Windows 只枚举 J7 COM33 和无可识别序列号的 CH340 COM34，没有可绑定到 H743 的原生 USB CDC。J7 本端状态和 CH340 枚举不能独立证明 H743 的供电、参考电平或复位脚电位。前次 F103ZE 收尾用同一 J7 和同一配对，目标 Flash、心跳及探针空闲均有独立证据。[F103ZE 收尾](../f103-web-reset-usb-20261114/README.md)

## 统一入口结果

`board.accept --board h743 --execute` 退出码 1，`accepted=false`。SWD 10 MHz 目标预检失败。SWD/JTAG 50 MHz 各 7 个功能/性能用例和各 3 轮压力，加上 SWD 10 MHz 的 ETM，共 21 个业务用例因目标预检阻塞。另 1 条目标终态复核阻塞，总计 1 失败、22 阻塞、0 通过。随机种子 `680014`，三轮脚本动作保留在证据中。未开始真实烧录或 USB 物理拔插。

| 验收部分 | 计划条件 | 本轮 |
|---|---|---|
| SRAM、烧录、调试、RTT Viewer、RTT 转发、J-Scope 单路及八路 | SWD/JTAG 50 MHz 各一遍，吞吐 CPU480/HCLK240，缓存随现场取证 | 14 项阻塞 |
| 跨页压力 | SWD/JTAG 各 3 轮，轮内四业务随机顺序 | 6 轮阻塞。物理数据线测试需台架配合并确认可独立供电。ARM/JTAG 网页 RTT 转发和 J-Scope 能力边界另见 ZL-226。 |
| ETM | SWD 10 MHz，CPU/HCLK 60 MHz，TRACECLK 20 MHz，连续 1 秒硬件窗 | 1 项阻塞 |

目标 ELF 的声明 SHA-256 及配对见 [结构化证据](evidence.json)。未取得可信目标 Flash、CPUID、目标时钟、缓存及运行状态读回，目标 ELF 尚未绑定现场。本轮没有性能样本，历史差值不可比。匹配条件与历史数据从 [H743 工作台暨性能报告](../h743-workbench-acceptance-20261109/README.md) 对齐，当前配对与该报告所用 RAM 配对的差异须随复测单列。另可参照 [H743 0.8 流专项](../h743-streams-hid-20261114/README.md)，其 60 MHz 链路与本轮 50 MHz 指定档位不可直接比较。

## 收尾与续跑

- [x] 计划、逐项结果、探针身份、频率、原始 ACK/TAP、首次失败及独立复测归档。原始文件在本机 `build/h743-board-accept-20261114/`，包括 `campaign/summary.json`、`campaign/events.jsonl`、`initial-target-swd10-failure.json`、`diagnostic-final.json`、`review-console.txt`、`cleanup.json` 和 OCM 物理读回。本轮未生成目标备份或 Trace 记录。
- [x] 复核探针释放。每次 DAP 断开均返回 `03 00`，最终 GPIO 高阻、路由 0、JTAG 采样模式回到 0、FCLK 回到初始 99,999,999 Hz。采集、调试、探针 packet、DDR、CDMA、RTT、HSS 空闲，Web 代理 USB/HID/串口资源表为空。目标 Flash、SRAM、核心断点和外设未进入写入阶段，目标运行状态仍未确认。
- [x] 登记 ZL-240。命令和交付路径、RTL/固件/夹具交付不适用。本地提交本轮证据与问题条目，保留 ZL-006 和已有 F103ZE 文件。
- [x] 本轮浏览器、Web 服务及工具子进程已退出，删除本轮临时服务目录、令牌和含鉴权内容的日志。共享 `hw_server`（PID 12776）及既有工作区、固定 EXE、历史记录均保留。无本轮临时分支或 worktree。

| 交付位置 | 本轮状态 |
|---|---|
| 远端 `main` | 推送不适用。开测时本地 `origin/main` 跟踪引用为 `d340cc3e`。 |
| 本机固定 EXE | 安装与启动复核不适用。 |
| 公开 Pages | 部署与公开复核不适用。 |
| Release 下载包 | 打包、发布和下载验收不适用。 |
| J7 QSPI | 核验台架已有 QSPI 启动标记及 AP0 执行代码，确认为正式配对 `0.8-nonce32`。固化、BOOT 整体读回和实体冷启动复测不适用。[既有冷启动证据](../qspi-probe-hid-20261114/README.md) |

现场先核对 H743 实际供电、J7 与目标共地、电平、转接板朝向，以及 SWDIO/SWCLK、TDI/TDO 和可用的 NRST。实测目标端电源及复位电平，确认 J7 能读到 H743 的 DPIDR `0x6ba02477` 和 DEV_ID `0x450`，再核对 Flash 装载段、已运行的 ELF 和时钟配置。两条链路预期接线见 [J7 接线图表](../../../README.md#硬件与接线)。

确认原应用和复位场景后，在新证据与工作台目录按 [统一入口](../../板卡精简验收与交付.md#一键执行) 补跑。下例用于已核验的 CPU480/HCLK240 Golden 现场及同一 QSPI 配对，真实烧录包含备份和独立读回。

```powershell
python -X utf8 toolbox.py --runtime build/accept-web-h743-resume serve --native-probe --bit prebuilt/qspi-release/probe.bit --zynq-elf prebuilt/qspi-release/application.elf
# 打开服务输出的本机鉴权地址，等浏览器工作页就绪，再在另一终端执行。
python -X utf8 toolbox.py project run board.accept -- --board h743 --runtime build/accept-web-h743-resume --out build/accept-h743-resume --jtag-cable-serial 210299008529 --only sram --only flash --only debug --only rtt-viewer --only rtt-forward --only jscope --only stress --allow-flash --execute
# CPU60/TRACE20 现场核对后，使用独立目录补测 ETM。
python -X utf8 toolbox.py project run board.accept -- --board h743 --runtime build/accept-web-h743-resume --out build/accept-h743-etm-resume --jtag-cable-serial 210299008529 --only etm --execute
```
