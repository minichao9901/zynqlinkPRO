# J7 QSPI 镜像 · 0.7-nonce32

此包用 J7 的已验收 bit 和带编译时间的 PS ELF 重新生成。固件编译时间为 `Nov 13 2026 20:51:50`（构建机本地时间）。QSPI 固化、断电启动、BOOT 读回、85,828 字节 OCM 对拍和 Web 版本及编译时间显示均通过。[验收数据](acceptance.json) · [构建清单](build_manifest.json) · [文件清单](flash_manifest.json)

从仓库根目录运行下列命令。探针需空闲且启动拨码为 QSPI。

```powershell
python -X utf8 toolbox.py probe-flash --skip-backup --image-dir prebuilt/qspi-probe-fw-info-20261113
```

`--skip-backup` 跳过备份，读回覆盖 BOOT 区。实体断电重上电后，用 JTAG 核对从 QSPI 启动的执行代码。

```powershell
python -X utf8 toolbox.py project run probe.ocm-verify -- --elf prebuilt/qspi-probe-fw-info-20261113/application.elf --require-qspi --out-dir build/qspi-probe-fw-info-cold-new
```

原始实机记录留在本机 `build/qspi-fw-info-20261113/`。正式 PL 的时序证据见 [原 J7 配对](../release-20261106/README.md)。本次用到的 PS 编译选项及源码哈希见 [PS 构建清单](../j7-probe-fw-info-20261113/ps-build.json)。
