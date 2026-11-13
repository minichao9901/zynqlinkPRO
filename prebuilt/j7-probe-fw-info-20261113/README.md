# J7 探针固件版本与编译时间

沿用正式 J7 的 PL 与 PS 初始化，新增 HID `0x16` 编译时间查询，固件版本为 `0.7-nonce32`。构建选项和逐文件 SHA-256 见 [构建清单](ps-build.json) 与 [验收清单](manifest.json)。

本配对通过 JTAG 临时加载及浏览器 HID 读取验证。实板验收结束后恢复已通过冷启动验收的原 QSPI 镜像。[实板与工作台验收](../../docs/validation/probe-build-info-20261113/README.md)
