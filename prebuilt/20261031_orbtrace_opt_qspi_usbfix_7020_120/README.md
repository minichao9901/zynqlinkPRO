# 7020/120MHz 优化版：USB Chapter 9 修正版 QSPI 包

应用源 `0ec2e63`，修复 SET_CONFIGURATION 使用空 UserDataPtr、向 OCM 地址零写1的问题；静态上下文在初始化失败退出时只解除引用，不调用free。代码71268字节、OCM跨度120976字节、DDR静态占用711520字节，16×4096 DAP队列与512KiB USB arena不变。

| 文件 | SHA-256 |
| --- | --- |
| `probe.bit` | `f02a15db0b576f631c08448b19ea3844d1b45ef00ee6801d243caee398960230` |
| `application.elf`（60MHz配置） | `6684400fd217fdd10f4a6375be48eff1e55560d861eca097470a2b88f0a6ddb7` |
| `application_50.elf`（50MHz配置） | `ad01372c6975fe7af974fd3e7888167239551b9321676aef15c520f7f823e64c` |
| `BOOT.bin` | `ee7116bc71b0c7f0fdbebed75c5c85137e80ec7ef7c1b8cc3db50cebb39f1185` |

PL显式复用未改变RTL的bc9ced6配对，未声称重新综合。7020/120MHz STA：WNS+0.499ns、WHS+0.020ns、TNS/THS零。后续ETM滤波改动未合入。启动链与此前已冷启动的版本相同；stage2二进制SHA-256仍为`f18bd49242ad78e3a28d99f7f486377bbe056f904dc6766119a788b3e561ecf8`。新ELF的固化/复位/冷启动验收单独记录，不借用旧ELF的结果。

新60MHz ELF已重新上板完成50/60MHz峰值、RTT、30秒soak和42行严格HSS；50MHz ELF另行加载完成50MHz峰值/RTT。四轮USB配置请求后全部可执行字节与最终ELF一致，复位向量保持EA000049。原始记录及相同参数对照在`docs/validation/orbtrace-usb-context-20261031/`。QSPI最终验收状态以flash_manifest.json及该目录最终记录为准。

主应用代码继续在OCM执行。空闲启动FCLK100MHz，请求SWCLK/TCK60MHz时切换FCLK120MHz。FSBL、BIF、构建来源/选项/哈希、实际bit/ELF均在本目录；只读Flash辅助程序用于整片备份与独立回读。

统一CLI默认使用本包：

```powershell
python -X utf8 toolbox.py probe-flash
python -X utf8 toolbox.py probe-flash --dry-run
python -X utf8 toolbox.py probe-flash --verify-only
```

完整固化流程为整片32MiB备份 → SDK擦除检查/写后校验 → 独立整片回读和擦写范围外对比 → 无暂停QSPI复位启动。旧包`20261031_orbtrace_opt_qspi_7020_120`仅保留历史，含已确认的USB空指针问题，不是当前默认。
