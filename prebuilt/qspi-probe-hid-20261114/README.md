# J7 QSPI 镜像 · 0.8-nonce32

用[实测 J7 bit/ELF 配对](../j7-probe-hid-20261114/manifest.json)重包。探针 HID 报告构建时间 `Nov 14 2026 00:08:09`。镜像为 4,281,040 字节，SHA-256 为 `34576b1fecd0b76ef40d25856f7f60b549298a014943353df1454934505980de`。写后及实体冷启动后两次完整 BOOT 读回均一致，物理 MEM-AP0 确认从 QSPI 运行的 OCM 代码与 ELF 一致。

探针空闲且已在 QSPI 启动模式时，可显式选择该包固化。

```powershell
python -X utf8 toolbox.py probe-flash --skip-backup --image-dir prebuilt/qspi-probe-hid-20261114
```

实体断电重上电后，先核对已运行的固件。

```powershell
python -X utf8 toolbox.py project run probe.ocm-verify -- --elf prebuilt/qspi-probe-hid-20261114/application.elf --require-qspi --out-dir build/qspi-hid-cold-new
```

再独立读回整个 BOOT 区并验证自主复位。

```powershell
python -X utf8 toolbox.py probe-flash --image-dir prebuilt/qspi-probe-hid-20261114 --verify-only --out build/qspi-hid-readback-new
```

[验收数据](acceptance.json) · [文件清单](flash_manifest.json) · [构建清单](build_manifest.json) · [冷启动与流验收](../../docs/validation/qspi-probe-hid-20261114/README.md)
