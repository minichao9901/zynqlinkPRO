# HPM SDK 原版 CFG 与双工作台发布

2026-11-12 从用户提供的 HPM SDK v1.11.0 `boards/openocd` 纳入 39 份原版 CFG 与 SDK 许可证，逐字节核对 Git 内容及两套 Windows 包。10 个 HPM 内置项通过 SDK 的 `BOARD`、`PROBE=cmsis_dap` 参数选择板与接口，恢复 HPM6P00EVK。ARM 继续使用 Wasm 同版本的 OpenOCD 原版 target CFG。两类均通过工作台现有 Wasm 原版 CFG 加载入口。

| 项目 | ZynqLink v1.3.2 | SuperlinkPRO 1.1.0-web.14 |
| --- | --- | --- |
| 包源码 | `ee018949` | `7d429665` |
| 日常 EXE SHA-256 | `08392d4e2f462d0f57e0676ffddecabea52fd56269568f02f7b0c71dfd3f6b2d` | `e283af4bcf1a5df3634bcb02f693cf592aba968517a61b0e6e6047a8a3b57a1d` |
| 日常数据 | 114 个文件 SHA-256 安装前后一致，旧程序归档 | 66 个文件 SHA-256 安装前后一致，旧程序归档 |
| 软件验收 | 159 项 Web、65 项 CLI、冻结版离线解码与导出、安装后预检通过 | 35 项相关 Web、10 项 CLI、冻结候选及安装后离线验证通过 |
| 下载包 | 56,175,993 字节，SHA-256 `3fe836df423f370271364ab223f725f17898aa4ad39a36f406136d327070c7b4` | 103,358,138 字节，SHA-256 `12e6c7bca0c18d89c9e63ba9b96e67152f0384c897c3150c730e2f8c77f1f0f2` |
| 线上 | `main` `ee018949`，`gh-pages` `c384fdc`，[GitHub Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.2) | `main` `8e9d5024`，[Pages Actions](https://github.com/minichao9901/superlinkPRO/actions/runs/43206395938) |

两个站点的公开清单均指向本次包。直接请求了 HPM6P00EVK 的 all-in-one、board、SoC 三份 CFG，各站逐字节与 SDK 一致；两个公开 ZIP 端点的总长度及首 4,096 字节与本机包一致。ZynqLink Release 资产服务端 SHA-256 和 SuperlinkPRO 公开下载清单 SHA-256 分别与本机包匹配。ZynqLink 发布中 API TLS 读取中断，同一版本的草稿流程恢复后资产核验与发布通过（ZL-164）。[ZynqLink Pages](https://minichao9901.github.io/zynqlinkPRO/) · [SuperlinkPRO Pages](https://minichao9901.github.io/superlinkPRO/)

两项目各 30 个内置项使用实际 Wasm 无 USB 解析。HPM6P00EVK 本轮覆盖配置加载、包内文件和线上资源，真机烧录待验证。SuperlinkPRO 全量目录扫还包含依赖 CDP 和外部固件夹具的用例，环境缺项保留在本机日志；与本改动相关的 CFG、烧录、复位和排队回归均通过。本轮未对板卡执行烧录或复位。上一轮 H743 实板对照见[验收记录](../h743-web-flash-resume-20261112/README.md#openocd-原版-cfg-对照与内置列表迁移)。
