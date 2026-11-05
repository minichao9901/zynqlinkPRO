# 交互火焰图HTML与bridge交付（2026-11-02）

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

ZL-012新增自包含交互HTML，默认按原始执行序号导出。完整调用深度、事件和未知祖先标记保留；不依赖超宽SVG画布。Web按钮/下载API、Trace CLI、bridge EXE离线接口共用生成器。SVG兼容导出仍保留，200000调用段边界未取消。

- CDC初始化：交互执行顺序火焰图（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/flame-html-20261102/CDC初始化-交互火焰图.html`）：seq7～42571，925个调用段、14层。
- 单次echo：交互执行顺序火焰图（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/flame-html-20261102/单次echo-交互火焰图.html`）：seq7782088～7784098，60个调用段、10层。
- [使用说明及CLI](../../flame-html-export.md)，初始化预览（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/flame-html-20261102/init-preview.png`）、echo预览（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/flame-html-20261102/echo-preview.png`）、冻结程序实际Web页面（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/flame-html-20261102/frozen-web-ui.png`）。

双击HTML即可离线打开；支持缩放按钮、滚轮围绕指针缩放、拖动平移、复位/上一级、选中调用定位、完整名称悬停、函数查找与深调用栈纵向滚动。键盘+/-、左右方向键和Home可操作。像素不足时裁剪文字，完整调用数据仍内嵌，放大后查看；没有分桶/聚合执行顺序数据。横轴不是逐指令精确时间。

## 源码与本机程序

源码功能提交206495b；完整UI复验发现并修复离线自动列表异常后，最终冻结源码提交为 **eaa600d55bb83ed3d4b24fcaebe42dd504a4cfd9**。从独立干净worktree构建，manifest的sourceDirty=false，没有混入另一AI的HPM/PS/RTL未提交改动。

已更新固定 `dist/zynq-etm-bridge/zynq-etm-bridge.exe`，完整1797文件哈希核对通过。新EXE SHA-256：

`3f9d8774bec5fe5ed2898c75bdc3e2056abec525d311e099e2146508ba98df61`

旧EXE SHA `ea74f6f52923b382c2553b5cecf14e7caeb196fd6e1c430d9190e56f19138057`，旧程序归档在 `build/bridge-archive/20261102-012449-5a5a04fd/previous/`。原固定目录无data，更新前后均0文件；更新器的data保留/回滚/安全边界另有4项测试通过。没有生成分发ZIP。dist按仓库约定留本机，Git记录源码、样例、完整包manifest与交付哈希。

CLI例子（仓库根目录）：

```powershell
python -X utf8 toolbox.py trace export --record <记录目录> --format flame-html --flame-mode timeline --from-seq 7 --to-seq 42571 --out init.html
.\dist\zynq-etm-bridge\zynq-etm-bridge.exe --trace-cli export --record <记录目录> --format flame-html --flame-mode timeline --from-seq 7 --to-seq 42571 --out init.html
```

EXE离线接口还验证了import-record、decode、verify、record info、elf inspect、query；capture等硬件命令明确拒绝。正常双击仍打开工作台，请保留整个程序目录。

## 验证与边界

- Python导出/集成7项：与原生SVG精确帧及事件间隙一致、区间/聚合周期权重、1500层无截断、段上限清理、脚本数据转义、自包含资源、离线Web与CLI字节一致、硬件命令拒绝。
- Web自测83项、CLI自测53项、发布器4项、共享驱动10份一致通过。
- 独立浏览器验证925/60段原始H743样例的缩放按钮、滚轮、拖动、复位、查找；1500层纵向虚拟滚动、聚合周期模式和恶意script名称转义均通过，无外部请求/脚本错误。
- 最终真实冻结EXE在PATH仅System32、没有系统Python/Node的环境中，完成F103ZE/H743导入、原生重解、SVG兼容导出、交互HTML和查询。Web API与EXE CLI HTML逐字节一致，1797文件身份正确，重复启动复用同实例。
- 冻结程序实际网页上选择区间913～977，点击“导出交互火焰图 HTML”确实下载并显示再次下载链接；通过Web CLI describe发现history方法，再invoke/exportFlame及分块download，内容与按钮下载逐字节一致，页面无未处理脚本异常。
- 固定目录安装后再次预检，并用该EXE检查全部7种已公开离线记录命令及硬件拒绝；两张交付图也由最终EXE重新导出，浏览器交互重新检查通过。

首个候选206495b的API/CLI及文件导出正确，但完整离线UI启动出现两个serial/list异常：后端正确403拒绝，前端却把HTML错误页当JSON读取。已登记ZL-077并修复：离线页面加标记，共享驱动自动list直接返回空，所有连接/传输仍拒绝，后端403保护不变。重新构建eaa600d的完整UI验证通过才更新固定程序；首候选失败保留在evidence/candidate1-ui-failure.json。

本任务没有USB/HID/串口/JTAG操作或板测，H743数据来自之前已保存记录；不声明硬件性能或采集路径获得新验收。所有本任务离线服务、浏览器和测试进程已停止，未停止另一AI进程。

## 并行协作与证据

另一会话的HPM6800、PS/RTL、夹具、bit/ELF及其问题条目未纳入本任务提交。源代码提交使用独立索引，只变更ZL-012与本任务ZL-077，保留另一会话的工作树/暂存内容；构建从固定提交独立检出。根目录其他未提交改动继续保留。

`delivery.json`记录源提交、EXE身份、样例范围/哈希；`evidence/`保留源码/冻结验证、Web CLI实测、安装与data核对、首候选失败及完整包manifest。没有提交运行时令牌或用户data。本地commit，未推送。
