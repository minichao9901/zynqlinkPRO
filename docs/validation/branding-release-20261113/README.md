# zynqlinkPRO v1.3.6 界面与发布验收

- 从干净源码 `c161a18073ca379993517c6c3eddba5d344cbd8f` 构建。Windows 启动器、包清单和内置 Web 的版本一致。主窗口、工程下载、帮助、ETM 独立页和探针相关状态采用 zynqlinkPRO 产品名。硬件返回的设备名、协议标识和历史样本来源按实记录。
- 固定 EXE 已升级。1,888 个程序文件逐项校验，原有 213 个数据文件的长度、时间和 SHA-256 一致。冻结 F103ZE/H743 离线 Trace 验收通过。Chrome 逐个打开 10 个工具页，以及 ETM 内页、帮助、版本窗口和可执行手册。27 条手册命令可见，QSPI 预检退出码为 0。本轮为界面与发包验收，未执行板卡擦写或复位。
- Pages 逐个打开 9 个公开工具页，版本窗口时间为 `2026-11-13 15:09:21 UTC`。内置 Web 构建时间为 `2026-11-13 15:08:54 UTC`。两侧下载卡显示 v1.3.6，下载和版本说明指向同一正式标签。模拟 API 离线和缺失 Windows 资产时，卡片显示「最新发布」。[Pages 部署](https://github.com/minichao9901/zynqlinkPRO/actions/runs/43450251896)
- 160 项 Web 自测、73 项 CLI 自测以及 166 个模块语法检查通过。问题编号 ZL-209。
- 从上述下载卡给出的地址匿名完整下载 56,195,565 字节。ZIP 内包清单、Web 构建模块和 GitHub Release 均为 v1.3.6。下载文件、GitHub 资产、公开 `SHA256SUMS.txt` 与本地 ZIP 的 SHA-256 一致，值为 `2ee6287ecc087425db9a7e22b53094368e52a04c4e7f7a02f9170eac72c645f8`。[GitHub Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.6)
