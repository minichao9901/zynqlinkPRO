# CLI工作台

CLI用于AI自动化；用户直接双击`zynq-etm-bridge.exe`，在Web完成选ELF、选函数、配置与采集。
PLL、AHB/APB分频属于target固件，生产Web/API与Trace capture CLI不再设置AHB分频。

## Windows桥包构建与离线验收

```powershell
# 构建机：已验证Windows x64 / Python 3.13，依赖见requirements-bridge-build.txt
python -X utf8 toolbox.py bridge-build --out dist/zynq-etm-bridge-win64
# 包含冻结EXE自身预检；完整回归用独立新目录，明确禁用所有硬件接口：
python toolbox.py project run bridge.verify -- --package dist/zynq-etm-bridge-win64 --out build/bridge-check
```

输出目录含EXE和`_internal`运行库，并生成同名ZIP；用户应完整解压，不单独复制EXE。
打包、验收均拒绝覆盖输出；manifest保存源码提交、依赖版本、文件SHA，预检子进程PATH无Python/Node。
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
Trace原始CLI见Trace-CLI使用说明.md。页内控制、串口/调试/RTT/J-Scope/烧录命令用toolbox.py相应子命令的--help与describe查询；其硬件动作不能用作离线检查。

需要启动工作台时用serve子命令，运行目录可用项目内小型.runtime目录。硬件模式必须显式指定Golden的bit/ELF；本轮精简与离线验证没有启用它。旧8882运行目录已清理，后续启动须生成新runtime，不能复用已删除的鉴权/URL文件。

RTT桥若需此前OpenOCD部署，路径为prebuilt/golden/host/openocd/openocd.exe，scripts为同目录scripts。没有服务在本轮结束时自动重启。
