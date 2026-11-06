# 验收与历史证据

当前状态见[问题索引](../项目问题跟踪列表.md)，文档导航见[文档入口](../README.md)。目录内各报告保留当时结论，失败、暂停和能力边界继续有效。

2026-11-06当前J7 bit/ELF、WebUSB、工程下载与GitHub发布见[正式交付](release-20261106/README.md)。23套旧prebuilt归档到 `archive/main-before-formal-release-20261106`，失败及暂停结论不变。

2026-11-05整理后，当前树保留各阶段报告与顶层摘要、最终会话/飞行记录、固件查看器和探针安全的完整公开证据；另保留原生差分依赖的 F103 大输入、H743 1s 与 H743 2s 固定原始输入。业务库仅有[5份精选记录](../retained-records.json)。自动测试夹具独立保留。

历史逐轮输出、截图和一次性驱动固定在 annotated tag `archive/main-before-cleanup-20261105`，对应清理前提交 `6765937`。逐文件路径、尺寸和SHA见[归档清单](cleanup-20261105/archived-files.json)。该归档tag已于2026-11-06随正式发布推送；原Git历史仍在。

查看单个历史文件：

```powershell
git show archive/main-before-cleanup-20261105:docs/validation/etm-e2e-clock-20261101/README.md
```

需要整目录或二进制证据时，用Git原生归档保留字节，再解压到项目外独立目录：

```powershell
git archive --format=zip --output=E:/zynqlinkPRO-history-20261105.zip archive/main-before-cleanup-20261105 docs/validation tools
```

历史脚本可能操作硬件或写Flash；恢复文件本身不授权执行。不要把历史板上状态当作当前现场，也不要因清理而关闭问题或重启暂停研究。
