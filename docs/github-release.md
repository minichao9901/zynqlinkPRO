# GitHub 发布

源码、网页和 Windows 包均使用 `minichao9901/zynqlinkPRO`。`main` 保存工程与正式 bit/ELF，`gh-pages` 只保存静态前端，Releases 保存完整便携 ZIP。在线地址为 `https://minichao9901.github.io/zynqlinkPRO/`，下载标签为 `#download`。

1. 修改源码与下载页版本；同步问题表，完成必要回归，提交源码及已验 bit/ELF。
2. 运行 `python -X utf8 toolbox.py bridge-build --zip`。候选先完成冻结预检和 F103/H743 离线验收，再更新固定程序，保留 `data` 并归档旧程序。不要在工作区有源码修改时发布包。
3. `python -X utf8 tools/publish_github.py stage --out build/pages-<版本>` 只复制 Git 跟踪的静态前端，生成逐文件 SHA；不复制记录、后端或令牌。先在浏览器检查页面。
4. `python -X utf8 tools/publish_github.py publish --out build/pages-<版本> --package dist/zynq-etm-bridge.zip --tag v1.3.0` 核验 ZIP 全部文件及源码干净标记，推送静态分支，设置 Pages，上传 ZIP/SHA256SUMS 后才发布 Release。凭据只经 Git credential helper 读入内存。
5. 核对匿名访问网站与下载地址、远端资产 SHA，再提交发布证据并 push main。已发布 Release 不覆盖；后续版本换 tag。

固定下载链接为 `https://github.com/minichao9901/zynqlinkPRO/releases/latest/download/zynq-etm-bridge-win64.zip`。网页不托管 ETM 后端，ETM 用户运行本地 EXE。

WebUSB 采用与 superlinkPRO 相同的标准 BOS platform capability / GET_URL，vendor code `0x21`，URL index `1`，保留原 WinUSB `0x20`。逐项实板检查：`python tools/verify_webusb_landing.py --out build/usb-landing-new.json`。描述符宣告网址，浏览器控制是否显示设备通知，不强制弹窗或自动授权。改网页 URL 时须同步固件并重建、验收、提交配对。
