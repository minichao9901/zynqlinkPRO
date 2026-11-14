# J7 正式 QSPI 启动包

当前镜像为 **0.8-nonce32**，与[版本归档](../qspi-probe-hid-20261114/README.md)使用同一套 BOOT、bit、应用 ELF 和辅助程序。该镜像已写入 J7，写后、实体冷启动后的完整 BOOT 读回与封存镜像逐字节一致，冷启动的 OCM 执行代码与应用 ELF 一致。详见[实板验收](../../docs/validation/qspi-probe-hid-20261114/README.md)。

`toolbox.py probe-flash` 默认使用此目录。本机 Web 可执行手册的预检、写入、冷启动核对和重包使用同一稳定路径。

```powershell
python -X utf8 toolbox.py probe-flash --dry-run
```

发布新固化版本时，先完成该 BOOT 配对的写入、完整读回、实体冷启动和 OCM 核对，将整套镜像、SHA-256 清单及验收出处一起提交到此目录。带版本的归档目录保留其原内容。重新打包的候选输出留在独立路径，供试验与验证。

[文件清单](flash_manifest.json) · [构建清单](build_manifest.json) · [验收数据](acceptance.json)
