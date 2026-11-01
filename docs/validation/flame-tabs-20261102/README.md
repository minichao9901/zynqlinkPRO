# 双标签交互火焰图与bridge交付（2026-11-02）

ZL-012追加鼠标框选放大和双标签导出。每个自包含HTML默认打开 **Timeline · 执行顺序**，另有同一区间的 **周期权重火焰图**。两个视图分别保留缩放历史、搜索、选中调用及纵向滚动。左键双向拖动框选，松开后放大；Shift＋拖动平移，Esc取消正在进行的操作。SVG导出保持原有接口。

- [CDC初始化双标签HTML](CDC初始化-双标签交互火焰图.html)：seq7～42571，Timeline925段/14层，周期页55段/15层、62237周期。
- [单次echo双标签HTML](单次echo-双标签交互火焰图.html)：seq7782088～7784098，Timeline60段/10层，周期页27段/9层、4539周期。
- [Timeline预览](init-timeline.png)、[周期页预览](init-cycles.png)、[框选预览](selection-preview.png)、[实际冻结Web页面](frozen-web-ui.png)、[CLI及操作说明](../../flame-html-export.md)。

周期页使用TraceStore中可求和的周期计数及其调用树，不以指令记录数冒充耗时，也不声称每条指令都有精确时间戳。缺少周期时保留第二标签并说明不可用。各视图保留200000调用段上限；HTML的聚合导出也必须能容纳其Timeline区间。旧模式/权重参数继续校验，聚合root应用于周期页，HTML始终默认Timeline；SVG仍按参数导出单个视图。

## 源码与本机程序

功能提交 **59284b9a28b12da6dea90bb0ea87b1bfbdbbd556**，从固定提交的独立worktree重建，manifest的sourceDirty=false。另一会话正在修改的HPM、PS/RTL及测试夹具均未混入本任务源码、程序构建或提交。ZL-012及文档已同步更新，其余未提交工作保留。

固定程序已更新：`dist/zynq-etm-bridge/zynq-etm-bridge.exe`，1797文件SHA-256逐项核对通过。EXE SHA-256：

`346b0ebc0e3517b4191fb68439ca8bf98f8576e79436ce1afcdf1a55aa130cae`

旧EXE SHA `3f9d8774bec5fe5ed2898c75bdc3e2056abec525d311e099e2146508ba98df61`，已归档到 `E:\zynqlinkPRO\build\bridge-archive\20261102-065833-f111747c\previous`。原固定目录无data，更新前后均0文件/0字节；没有删除用户记录，没有生成ZIP。dist按原约定留本机，Git保留源码、样例、完整包manifest和交付身份。

## 验证范围

- Python导出/集成9项，Web83项，CLI53项，Web构建检查及10份共享驱动一致性通过。
- 实际Chrome浏览器验证正反框选、拖动时蓝色选区、松手放大、越界松手夹紧、Esc取消、pointercancel回滚、Shift平移、标签独立缩放/历史/搜索、键盘切换、点击不误缩放、原有按钮/滚轮/查找功能。另验证缺周期提示、1500层滚动及切换后位置保留，无外部请求或脚本异常。
- 真实冻结EXE在PATH仅System32、无系统Python/Node的环境中，完成F103ZE与H743导入、原生重解、SVG兼容、双标签HTML及查询；1797文件校验、重复启动复用通过，所有硬件路由403。
- 实际冻结Web按钮下载成功，Web CLI describe/invoke/download内容与按钮逐字节一致；下载文件默认Timeline、两个标签及框选放大均验证通过，页面无未处理异常。
- 固定目录EXE再次预检，通过它在全新目录重新导出初始化/echo，内容与当前源码逐字节一致；最终两张文件再做完整浏览器交互检查。Timeline的全部frame/name/event数组与上一轮原始顺序导出一致。

安装后首次样例比对脚本误复用已存在的输出路径：源码CLI按设计报FileExistsError、不覆盖旧文件，因此旧样例少了提交前追加的3处拖动取消保护，与新EXE比较失败。该问题属于测试驱动误用；已保留拒绝覆盖JSON和失败日志，改用source-final/installed-final全新目录，检查返回码后重导、逐字节比较及浏览器复验通过。未通过覆盖或修改旧证据制造一致性。

本任务只使用已保存H743记录，全程离线，没有USB/HID/串口/JTAG操作，没有更改板上状态。所有本任务服务、浏览器和测试进程已停止；未停止另一AI进程。本地提交，未推送。

`delivery.json`记录程序和两张HTML的哈希/范围/计数；`evidence/`保留源码测试、完整包manifest、冻结Web/CLI验证、安装核对及首轮测试误用证据，不包含鉴权令牌或用户data。
