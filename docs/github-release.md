# GitHub 发布

源码、网页和 Windows 包均使用 `minichao9901/zynqlinkPRO`。`main` 保存工程与正式 bit/ELF，`gh-pages` 只保存静态前端，Releases 保存完整便携 ZIP。在线地址为 `https://minichao9901.github.io/zynqlinkPRO/`，下载标签为 `#download`。

1. 在 `web/app/core/build.js` 更新工作台版本，同步问题表，完成必要回归，提交源码及已验 bit/ELF。Windows 启动器和包清单从同一模块读取版本。下载卡片从 GitHub 的最新正式 Release 读取版本，API 不可用时显示「最新发布」并保留下载链接。
2. 运行 `python -X utf8 toolbox.py bridge-build --zip`。候选先完成冻结预检和 F103/H743 离线验收，再更新固定程序，保留 `data` 并归档旧程序。不要在工作区有源码修改时发布包。
3. `python -X utf8 tools/publish_github.py stage --out build/pages-<版本>` 只复制 Git 跟踪的静态前端，生成逐文件 SHA；不复制记录、后端或令牌。先在浏览器检查页面。
4. `python -X utf8 tools/publish_github.py publish --out build/pages-<版本> --package dist/zynq-etm-bridge.zip --tag v1.3.0` 核验 ZIP 全部文件及源码干净标记，推送静态分支，设置 Pages，上传 ZIP/SHA256SUMS 后才发布 Release。凭据只经 Git credential helper 读入内存。
5. 匿名打开工程下载页，核对卡片版本、版本说明与实际下载包的标签一致。核对远端资产 SHA，再提交发布证据并 push main。已发布 Release 不覆盖，后续版本换 tag。

主工作树有其他改动时，从已提交的发布源码创建独立工作树打包，发布前核对 ZIP 与 Pages 的来源提交一致。TLS 中断后先查看远端分支和同 tag 草稿、资产状态，再续传。固定 EXE 更新后从固定路径启动，实际点手册的离线预检；静态页面则对照线上版本窗口、清单和公开完整下载。各项证据记录具体版本，离线验收与板测记录分别留存。

固定下载链接为 `https://github.com/minichao9901/zynqlinkPRO/releases/latest/download/zynq-etm-bridge-win64.zip`。网页不托管 ETM 后端，ETM 用户运行本地 EXE。

J7 使用[固定 QSPI 目录](../prebuilt/qspi-release/README.md)。只更新探针镜像时，把验收通过的 BOOT、配套 bit/ELF、辅助程序和清单一起提交并推送到 `main` 的 `prebuilt/qspi-release/`。Pages 链接始终指向该目录，本机 Web 手册和 CLI 使用本机仓库同一路径，用户更新仓库即可选用新镜像。单独更新镜像无需再发布 Pages 或重打 Windows 包。

## v1.3.9 发布验收

2026-11-15（上海时间）。构建来源和发布标签指向 `e17948ff69c2fd8964af2d27983ef6d9c373413a`。匿名 Chrome 打开 Pages，版本和工程下载卡均显示 v1.3.9，构建于 09:50:14。`gh-pages` 为 `cb9f2f31afc1dc8f4c4ea2fae5741f35118974bc`，线上站点清单、实际 Viewer 模块和版本模块均与候选一致。首次取 `gh-pages` 遇 TLS 中断，核对远端仍在旧提交后重新取同一父提交，正常前进发布。[Pages](https://minichao9901.github.io/zynqlinkPRO/#download)

公开 Release 于 10:00:11 发布。完整匿名下载 Windows ZIP 共 56,216,104 B，SHA-256 `db3996a43e1b82328b415b693eb6881cf48dbd81fd0f7ea9b8415e28ad70b054`。比对发布资产、`SHA256SUMS.txt`、本机 ZIP 和包内 1,891 个文件。固定 EXE 已更新至 v1.3.9，构建于 09:50:24，EXE SHA-256 `0ca273c2344d9e1aaa9721052d1b8f53c0b525cd41473f3a40b6511524087d8d`。更新前后用户 `data/` 的 215 个文件哈希一致，旧程序已归档。实际启动固定 EXE 并在浏览器点击手册的离线 QSPI 预检通过。Web 196 项、CLI 109 项、174 个模块语法、共享驱动和 F103/H743 冻结离线验收通过。[Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.9)

Pages 的 QSPI 链接指向 `main` 的 `prebuilt/qspi-release/`。从已推送提交匿名下载了 `flash_manifest.json` 及清单内 15 个文件，逐个比对本机和 SHA-256。正式版本沿用 0.8-nonce32，BOOT SHA-256 `34576b1fecd0b76ef40d25856f7f60b549298a014943353df1454934505980de`。发布差异没有探针 RTL、固件或正式 QSPI 包变更，沿用已有实体冷启动和完整读回证据，前次 H743 Viewer 验收也复核了该配对的运行身份。本次发布不涉及重刷或新冷启动。[正式 QSPI 实板证据](validation/qspi-probe-hid-20261114/README.md) · [发布证据](validation/workbench-v139-release-20261115/evidence.json)

发布工作树、浏览器、固定 EXE 的隔离检查会话和匿名下载临时目录已清理。完整本机复核数据 `build/v1.3.9-release-evidence/`，固定程序及分发 ZIP 在 `dist/`。F103ZE/H743 的 Viewer 源码实板范围见各自报告。两份先前 Viewer 测试的重复 Xilinx DLL/EXE 临时副本仍待清理，执行环境策略拒绝了删除操作，共享 `hw_server` 未受影响。[F103ZE Viewer 验收](validation/f103ze-arm-viewer-20261115/README.md) · [H743 Viewer 验收与收尾](validation/h743-viewer-mem-ap-20261115/README.md#viewer-双板收尾复核)

## v1.3.8 发布验收

2026-11-14。来源提交 `3255b515`，Pages 静态提交 `97ac02bc`。公开 Pages 显示 v1.3.8，构建时间 `08:24:06 UTC`，工程下载页的 QSPI 链接指向 `main` 固定目录。核对线上清单及相关文件字节，浏览器检查说明、版本窗口和下载目标。

公开 Windows ZIP 完整下载 56,200,968 B，SHA-256 为 `7ed9bcde00d2ae120d13cd1b9a945beb31234fb4f1ada8a7c9502188e8d7199e`，与 Release 资产和构建产物一致。保留 `data/` 并更新固定 EXE，构建时间 `08:24:18 UTC`。固定 EXE 的 Web 手册实际执行 QSPI 预检成功，15 个镜像包文件哈希全部通过，冷启动和重包命令引用同一配对。Web 177 项、CLI 76 项，冻结版 F103/H743 离线回归通过。本次未重刷。 [Pages](https://minichao9901.github.io/zynqlinkPRO/#download) · [Release](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.8)

WebUSB 采用与 superlinkPRO 相同的标准 BOS platform capability / GET_URL，vendor code `0x21`，URL index `1`，保留原 WinUSB `0x20`。逐项实板检查：`python tools/verify_webusb_landing.py --out build/usb-landing-new.json`。描述符宣告网址，浏览器控制是否显示设备通知，不强制弹窗或自动授权。改网页 URL 时须同步固件并重建、验收、提交配对。
