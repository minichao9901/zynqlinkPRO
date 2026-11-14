# 正式交付

| 配对 | 用途 |
|---|---|
| [release-20261106](release-20261106/README.md) | 当前 J7 转接板：ELD1、原始 SWD 序列修复与 WebUSB 网页入口；F103ZE 限定验收 |
| [qspi-release](qspi-release/README.md) | J7 正式 QSPI 固定目录，CLI 和本机 Web 手册共同使用 |
| [qspi-release-20261106](qspi-release-20261106/README.md) | 11 月 6 日历史 QSPI 包，实体冷启动及 F103ZE 回归通过 |
| [qspi-probe-fw-info-20261113](qspi-probe-fw-info-20261113/README.md) | J7 探针固件 0.7-nonce32 QSPI 包，固化、冷启动、BOOT 和 OCM 读回以及 Web 版本显示通过 |
| [qspi-probe-hid-20261114](qspi-probe-hid-20261114/README.md) | 0.8-nonce32 版本归档，实体冷启动、BOOT 与 OCM 读回、Chrome 持久授权及 H743 流回归 |
| [golden](golden/README.md) | 原 7020/120 MHz Golden 比较、目标 ELF、构建输入与回退 |
| [recovery](recovery/README.md) | 已验收 QSPI 恢复包，保留原始字节与来源 |
| targets/ | 正式目标固件与源码身份 |

实验、失败及被替代的 23 套交付已退出当前树，原始文件保存在 tag `archive/main-before-formal-release-20261106`。具体目录见[归档清单](../docs/validation/release-20261106/evidence/archived-prebuilt.json)，恢复使用 `git archive` 或 `git show <tag>:<路径>`。归档不改变历史失败、暂停状态或验收边界。

加载新配对属于 JTAG/RAM 操作，不代表 QSPI 固化或冷启动验收。每套配对以自己的 manifest、哈希及报告为准。
