# Trace CLI

统一入口`python -X utf8 toolbox.py trace`，转交`etm-service/trace.py`。该入口的`capture/doctor`是Zynq原生路径；离线decode/query/export等转交`etm-service/tools/cli_entry.py`及`trace_cli.py`，沿用原生二进制/TraceStore协议。

```powershell
python toolbox.py trace --help
python toolbox.py trace doctor --offline
python toolbox.py trace capture --help
python toolbox.py trace query --help
python toolbox.py project describe etm.cli
python toolbox.py project run etm.cli --dry-run -- query --help
```

doctor --offline只检查本地依赖、当前Golden路径，不枚举USB、不访问服务，不证明板上版本。普通doctor会检查设备/服务，不属于离线验证。
capture是实际硬件动作；decode/query/export作用于保存记录。各命令的精确参数用--help查询，CLI保留JSON信封与底层失败状态，不用重试掩盖失败。

ETM目标配置默认SWD为10 MHz，网页连接、本地采集服务接管和恢复连接保持同一档位；不改变目标CPU/TRACECLK。参数单位按入口区分：

| 入口 | 时钟参数 | 显式1 MHz对照 |
|---|---|---|
| `toolbox.py trace capture` / `etm-service/trace.py capture`（Zynq原生、无需浏览器） | `--swd-khz`，kHz | `--swd-khz 1000` |
| `etm-service/tools/cli_entry.py` / `trace_cli.py` 中的target/Web命令 | `--swd-hz`，Hz，以子命令帮助为准 | `--swd-hz 1000000` |

不要把底层Web路径参数照搬给Zynq原生capture。旧“固定1MHz”限制已撤销；完整Web控制仍需对应服务的鉴权URL和浏览器worker。

F103ZE常用目标ELF为`prebuilt/golden/f103ze-cdc48.elf`。Zynq原生capture要求明确传`--elf`（目标MCU）、`--bit`（探针PL）和`--zynq-elf`（探针PS）；它不会加载所声明配对。doctor的默认Golden路径不证明板上身份；Golden、release及实验版的哈希/范围以各manifest和报告为准。业务记录清单在retained-records.json，数据包含源码和配置，不依赖旧build/worktree。

```powershell
# 硬件示例：先核对空闲并加载同一配对；输出目录须不存在。
python -X utf8 toolbox.py trace capture --elf prebuilt/golden/f103ze-cdc48.elf --bit prebuilt/fclk133-release-20261101/probe.bit --zynq-elf prebuilt/fclk133-release-20261101/application.elf --out build/trace-capture-new --seconds 1 --swd-khz 10000
```

新会话协作规则见根 [AGENTS.md](../AGENTS.md)。遇到异常或验收缺口时，同步更新 [项目问题跟踪列表](项目问题跟踪列表.md)，原始证据保留在`docs/validation/`对应目录。

SVG支持timeline/aggregate及选定seq范围。完整timeline有200000段上限，超宽聚合图也有实际限制；精简不消除这些边界。HSS缺首DEF仍暂停。
