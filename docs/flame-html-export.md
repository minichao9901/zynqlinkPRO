# 可缩放的火焰图 HTML

在 Web 的火焰图中选定执行区间，点击 **导出交互火焰图 HTML**。也可在“记录与导出”选择“当前区间交互火焰图 HTML”。双击下载文件即可离线查看，不需要启动工作台或连接板卡。每个文件包含 **Timeline · 执行顺序** 和 **周期权重火焰图** 两个标签页，默认打开 Timeline。

- `＋/−`、滚轮：放大/缩小，滚轮以指针位置为中心。
- 鼠标左键拖动：显示蓝色选择区，松开后放大该区间，支持从左向右或从右向左框选。
- `Shift＋左键拖动`：横向平移；“复位”回到文件包含的完整区间，“上一级”返回之前的视窗。
- 点击调用段查看完整函数名、原始范围和调用路径；双击或“放大选中调用”定位该调用。
- 查找函数后用“上一个/下一个”定位，其他调用仍保留；深调用栈可纵向滚动。
- 键盘 `+/-` 缩放、左右方向键平移、`Home` 复位；`Esc` 取消尚未完成的框选/平移。
- 两个标签页分别记住缩放、历史、搜索、选中调用和纵向滚动位置。标签按钮可用左右方向键切换。

“按执行顺序”导出始终使用原始执行序号和完整调用深度，不合并重复调用、不使用页面显示分桶；横轴不是逐指令精确时间。事件和未知祖先标记保留。像素过窄时不显示文字，放大或悬停可看完整名称，数据仍在文件里。周期页按相同区间的真实周期计数对调用路径聚合，宽度代表累计周期，保留周期计数的归属说明，不将指令记录数换算为耗时。没有周期计数时仍显示第二个标签页，并明确说明不可用。周期计数不等于每条指令都有精确时间戳。

HTML自包含，无外部脚本、字体或网络请求。导出范围不能在离线文件里扩大到未包含的区间；需要更多数据时回工作台重新选区间导出。每个视图仍限制200000个调用段，超过时明确提示缩小区间。SVG兼容导出继续保留。

## CLI

```powershell
# 本工程统一入口；默认timeline，也可显式指定。
python -X utf8 toolbox.py trace export --record <记录目录> --format flame-html --flame-mode timeline --from-seq 7 --to-seq 42571 --out cdc-init.html
# 新bridge EXE的离线接口，不需要本机Python/Node，不启动Web服务。
.\dist\zynq-etm-bridge\zynq-etm-bridge.exe --trace-cli export --record <记录目录> --format flame-html --flame-mode timeline --from-seq 7 --to-seq 42571 --out cdc-init.html
.\dist\zynq-etm-bridge\zynq-etm-bridge.exe --trace-cli query --record <记录目录> --view summary --compact
```

HTML始终包含两个视图并默认Timeline；旧 `--flame-mode/--flame-weight` 参数继续校验，显式聚合节点 `--flame-root` 应用于周期页。SVG仍按原参数导出单个视图。两个视图各自受200000调用段上限约束，聚合导出也需其Timeline区间能够导出。

`--trace-cli --help`列出离线记录命令；`--trace-cli export --help`查看格式/范围参数。该EXE接口明确拒绝capture/target等硬件命令。一般启动仍双击EXE进入工作台；请保留整个程序目录及`_internal`。

Web CLI沿用已有网页方法，先发现接口，再调用：

```powershell
python toolbox.py --runtime <运行目录> page etm describe --target history
python toolbox.py --runtime <运行目录> page etm invoke exportFlame --target history --args '[{"mode":"timeline","format":"html"},{"captureOnly":true}]'
python toolbox.py --runtime <运行目录> page etm downloads
python toolbox.py --runtime <运行目录> page etm download <下载ID> flame.html
```

使用当前已选记录与区间；`captureOnly=true`只交给CLI下载捕获，普通点击仍触发浏览器下载，并保留“再次下载 HTML”链接。

本轮使用已有H743初始化及单次echo记录，未访问板卡。样例、截图与源码/冻结程序验收见 [交互HTML验收](validation/flame-html-20261102/README.md)。

双标签与框选放大的更新验证见 [双标签HTML交付](validation/flame-tabs-20261102/README.md)。
