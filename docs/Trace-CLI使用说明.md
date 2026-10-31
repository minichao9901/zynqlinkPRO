# Trace CLI

统一入口python toolbox.py trace；也可直接python etm-service/trace.py。

```powershell
python toolbox.py trace --help
python toolbox.py trace doctor --offline
python toolbox.py project describe etm.cli
python toolbox.py project run etm.cli --dry-run -- query --help
```

doctor --offline只检查本地依赖、当前Golden路径，不枚举USB、不访问服务，不证明板上版本。普通doctor会检查设备/服务，不属于离线验证。
capture是实际硬件动作；decode/query/export作用于保存记录。各命令的精确参数用--help查询，CLI保留JSON信封与底层失败状态，不用重试掩盖失败。

F103ZE目标ELF默认prebuilt/golden/f103ze-cdc48.elf；Zynq默认同目录probe.bit/application.elf。当前Golden哈希和来源在golden-release.json。业务记录清单在retained-records.json，数据包含源码和配置，不依赖旧build/worktree。

SVG支持timeline/aggregate及选定seq范围。完整timeline有200000段上限，超宽聚合图也有实际限制；精简不消除这些边界。HSS缺首DEF仍暂停。
