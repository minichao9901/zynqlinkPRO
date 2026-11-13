# zynqlinkPRO J7 HID 授权修复配对

探针固件 `0.8-nonce32`，实机 HID 构建时间 `Nov 14 2026 00:08:09`。沿用已固化的 J7 PL，重新编译 PS。详见 [配对清单](manifest.json)、[编译选项和源码哈希](ps-build.json)及[实机验收](../../docs/validation/h743-streams-hid-20261114/README.md)。

临时加载到探针后，Windows Chrome 在同一站点与配置中复用 USB 和 HID 授权。实机通过物理 MEM-AP0 独立核对 85,716 字节 OCM 执行区。此配对用于 JTAG RAM 加载，验收后探针回到已有的 0.7-nonce32 QSPI 镜像。

后续已将同一 bit/ELF [重包并固化至 QSPI](../qspi-probe-hid-20261114/README.md)，实体冷启动通过。

```powershell
python -X utf8 toolbox.py probe-load --bit prebuilt/j7-probe-hid-20261114/probe.bit --elf prebuilt/j7-probe-hid-20261114/application.elf --ps-init prebuilt/j7-probe-hid-20261114/ps7_init.tcl
```
