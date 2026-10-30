# 完整 ETM 页面移植说明

当前工作台的轻量 `ETM 执行轨迹` 面板继续保留 ZynqDAP 直连和 `.zetm` 本地记录解码。`E:\superlinkPRO\web\etm` 的完整页面已经原样移植到当前仓库的 [web/etm](../web/etm/) 路径，主页面 ETM 面板提供“打开完整 ETM 工作台”入口。

完整页面包含：

- ELF / 源码载入、目标识别、F103ZE / H7 时钟规划与 ETM/TPIU 配置
- 硬件断点起点、复位/运行至起点、采集设置与 Kingst 联动
- 历史记录、可信区段、包问题、源码快照和调用栈
- 执行时间线、函数统计、热点、按调用权重/执行顺序的火焰图
- 当前区间火焰图 SVG、CSV、JSON、源码执行流等导出

完整页使用 superlinkPRO 的本地 ETM bridge API（默认 `127.0.0.1:8899`）。没有启动 bridge 时仍可打开页面和查看界面，但采集、历史分析和导出服务会显示离线提示。当前仓库的 ZynqDAP 直连链路不依赖 bridge，继续由轻量面板提供。

本轮验证：

- 完整页面静态加载、分析视图和火焰图入口可见。
- 启动 `E:\superlinkPRO\web\bridge\etm\backend\server.py --port 8899` 后，完整页面报告本地服务在线。
- 当前仓库 Web ETM 记录已通过 OpenCSD WASM 解码：1309 ETM 字节、6368 指令范围、`lastErrorCode=0`。
- 当前工作台九个页面均完成模块语法/本地依赖检查；页面切换回归见 `node web/tools/check.mjs` 和 `node --test web/tests/*.test.mjs`。
