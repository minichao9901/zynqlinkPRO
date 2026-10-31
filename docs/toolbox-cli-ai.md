# CLI工作台

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
