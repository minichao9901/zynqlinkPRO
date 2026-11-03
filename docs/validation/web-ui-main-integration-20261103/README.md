# Web UI 主线集成（2026-11-03）

用户授权在ETM C++集成后合入Web分支。父版本main为`4fd4044`，Web分支为`b181751`，实际合并提交`a2b8bc4`。本轮在主工作区main合并，原Web worktree及分支保留；不推送、不操作硬件。

## 范围与协调

合入紧凑布局、设置收起、日志检索、目标/ELF复用及生命周期修复、WebUSB唯一调试后端、移除工程生成页、HPM烧录批量传输、STM32/HPM白名单与25MHz限制、原生流25MHz选项，以及ETM三条教学流程。原生研发CLI调优选项保留。

ETM C++生产源码、配套原生EXE/DLL与合并前main一致；server.py自动保留原生ELF DTO和教学只读接口两项。没有重建或替换PL/Zynq ELF。生产代码无文本冲突，问题表文档按事项合并，主表127条编号唯一。

独立分支107～114与main事项碰撞：Web107/108/109/110/111/112/113/114映射为125/124/126/127/121/122/123/120。ZL-106合并较新修复证据；不重复建行。完整别名见[映射表](../../问题编号别名-20261102.md)。历史报告/JSON保留原编号，必须连同分支来源解释。ZL-123（Web原113）的HSS额外跳采仍待定位；RTL审查111～115不因UI合并关闭。

## 已完成检查

- 128项Web、56项CLI、15项原生核心/发布/依赖自测通过。
- Web语法与共享副本检查通过；865个必需依赖内容及Git跟踪检查通过。
- 原生核心资源保持原main字节，见native-preserved.json；固定程序用户data更新前摘要见data-before.json。

## 最终固定程序

`E:/zynqlinkPRO/dist/zynq-etm-bridge/zynq-etm-bridge.exe` 已从干净合并提交`a2b8bc4`构建并更新（sourceDirty=false）。更新器归档旧程序到`build/bridge-archive/20261103-202544-47c6c06e/previous`；未生成ZIP。用户data仍为5文件/1664字节，内容树SHA保持`674d4c6ede36cad3e5d461b29e320896be5608a8a1aa5173389be4bb4621e968`，见package-identity.json。

新EXE SHA-256：`44cab3398350c7fcfbee48b0abbad67ef68d95fc8e46b85d65353d6000cf42da`。包manifest SHA：`718a2b4d275608cbf0d152ca566a4b05f00e944a1f36354f90072d337e692775`。原生算法EXE/DLL保持原main已验收字节。完整冻结检查包括F103/H743导入、原生解码、查询、HTML/SVG及CLI导出、示例原字节、重复启动、硬件路由禁用，见frozen-verification.json。

实际固定EXE以新data目录、--offline启动：8页45条CLI操作通过；浏览器导入H743教学示例、完成7步分析（实际点击报告/指令行/历史导航/火焰图/可信区段）、重复打开、Escape退出恢复布局，均通过。示例210497路径/14265包/11中断；记录选项仍为2，控制台error为0。见web-cli.json、browser.json和merged-tutorial.png。只读验收与UI测试均不接触板卡。

测试服务/浏览器已关闭，没有本任务后台进程。原Web分支及worktree不动；main除未跟踪build外无产品未提交修改。

本轮不重新测硬件吞吐，不把历史板测或离线耗时当作新采集E2E。
