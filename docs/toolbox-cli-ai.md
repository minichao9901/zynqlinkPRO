# ZynqDAP Web 统一 CLI

入口为根目录 `toolbox.py`，参考 `E:\superlinkPRO\toolbox.py`，覆盖本仓库九页。
Web 操作由本机队列交给真实页面执行；`trace` 转交本仓库 ETM CLI。

## 启动

```powershell
python -X utf8 toolbox.py --help
python -X utf8 toolbox.py catalog
python -X utf8 toolbox.py catalog --full
python -X utf8 toolbox.py --runtime build/toolbox-001 serve --port 8878
```

运行时目录须不存在。在 Chrome/Edge 打开服务输出的完整 `browserUrl` 并保留页面。
同一端口提供工作台、`/etm/`、`/etm/api/`、`/trace-cli/`，避免跨源 iframe
阻断 CLI 和探针互斥。无需另起静态站和8766服务。端口被占用或被 Windows 保留时，
换一个空闲端口和新的运行时目录。Ctrl+C 停止服务，重启使用新运行时。

首次 USB/串口/HID 授权须在真实浏览器完成一次；CLI click 不生成用户手势。
先点页面连接按钮选择 ZynqDAP，之后 CLI 可复用授权。内置浏览器若不显示设备
选择器，请使用 Edge/Chrome 和新服务运行时；一个服务只接受一个执行页面。
令牌和运行时不可提交 Git。

## 全部命令

全局参数放在子命令前：`--runtime R`、`--timeout 60`、`--out result.json`（拒绝覆盖）。
stdout 为 JSON；退出码0=请求成功、1=执行失败、2=参数错误；trace 保留自身退出码。

| 命令 | 作用 |
|---|---|
| `catalog [--full]` | 离线九页功能/命令/静态控件清单 |
| `serve --port 8878` | 启动统一 Web、ETM 后端与本机队列 |
| `ping` / `status` | 执行器就绪 / USB授权和调试、ETM状态 |
| `page P describe [--target T]` | 当前控件、选项、公开方法、targets、停止白名单 |
| `page P state` / `show` | 页面文字和摘要 / 切换页签 |
| `page P read SELECTOR` | 读取值、文本和 disabled 状态 |
| `page P set SELECTOR JSON` | 设置并触发 input/change，复选框用 true/false |
| `page P click SELECTOR` | 点击唯一且未禁用的控件 |
| `page P interrupt SELECTOR` | 长任务期间点击白名单停止按钮 |
| `page P invoke METHOD [--target T] [--args JSON / --args-file F]` | 等待原页面方法返回 |
| `page P event SELECTOR TYPE [--data JSON]` | 键盘/鼠标/指针/滚轮/输入事件 |
| `page P upload SELECTOR FILE... [--directory]` | 向 file input 上传文件或源码目录 |
| `page P wait SELECTOR --contains TEXT` | 等待控件文本 |
| `page P downloads` | 列出当前页捕获的 Blob 导出 |
| `page P download ID FILE` / `discard ID` | 分块落盘并计算 SHA-256 / 释放暂存 |
| `request F.json` / `batch F.json` | 单条请求 / 顺序执行，首个失败停止 |
| `job ID` / `ack ID` | 查询任务 / 删除已完成结果 |
| `trace ...` | `etm-service/trace.py` 全部命令 |

P 为 `serial terminal rtt rttcdc scope flash dbg etm gen`。
T 以 describe 返回为准：通常为 view/session；RTT转发另有 hid；
ETM 另有 target（目标控制）和 history（执行流、分析与导出）。
隐藏 file input 通过 describe 中的 `@file:view.属性名` 访问。invoke 不接受私有方法、
任意对象路径或 eval。参数需要文件时用 `{"$file":"E:/path/fw.elf","kind":"buffer"}`，
kind 支持 file/buffer/bytes；复杂 JSON 推荐 --args-file，避免 PowerShell 引号问题。

## 各功能的验证路径

以下 R 替换为服务的运行时目录：

```powershell
python -X utf8 toolbox.py --runtime R ping
python -X utf8 toolbox.py --runtime R page dbg describe
python -X utf8 toolbox.py --runtime R page dbg invoke connect
python -X utf8 toolbox.py --runtime R page dbg invoke runLine --args '["halt"]'
python -X utf8 toolbox.py --runtime R page dbg invoke runLine --args '["r"]'
python -X utf8 toolbox.py --runtime R page dbg invoke runLine --args '["c"]'
python -X utf8 toolbox.py --runtime R page dbg invoke disconnect
```

| 页面 | 实板验收内容 |
|---|---|
| serial / terminal | 授权端口、连接、接收、发送、终端共享会话、保存、断开 |
| dbg | 连接F103ZE、匹配ELF、暂停/继续/单步、寄存器/内存、断点、变量、断开 |
| rtt | 匹配固件控制块、通道发现、上下行、停止、数据质量 |
| rttcdc | HID配置、RTT→CDC接收、停止、质量报告、切回普通串口 |
| scope | 匹配ELF变量、真实采样、触发、停止、CSV导出、质量与会话释放 |
| flash | 上传目标ELF、STM32F1、编程+校验+复位，读取 #f-result 和 #f-log |
| etm | 下述完整流程，必须核对质量和导出文件 |
| gen | 参数、生成、文件预览和下载 |

RTT/J-Scope 需要目标固件提供控制块/变量，ETM样例固件不等于RTT测试固件。
切换目标固件后重新载入匹配 ELF，记录固件 SHA-256。

## ETM：CLI 控制 Web 的完整流程

加载配对与限制见 [ETM操作说明](Zynq-ETM-Trace操作说明.md) 和 [Trace CLI](Trace-CLI使用说明.md)。

1. `page etm describe`，向返回的ELF控件 upload 目标ELF，等待标签更新。
2. 首次在页面连接探针授权，后续复用授权连接；填板级 HSE=8 MHz。
3. 读取时钟，选择业务断点和采集起点，核对实际 HCLK/TRACECLK。
4. 配置并暂停，设时长（建议从50 ms开始），点击联动采集。
5. 读取 job/日志，直到采集和解码结束；核对 source ID 2、字节数、同步、结束包、
   FIFO/USB loss、FCLK/TCK、OpenCSD错误和 gaps。
6. `page etm describe --target history`，使用公开方法查看执行流、热点、调用树/火焰图；
   导出 CSV/SVG/记录包，通过 downloads/download 保存并记录 SHA-256。
7. 恢复 trace 配置、断点和目标运行状态，断开ETM，切回调试器确认探针可复用。

批处理字段在根对象，不嵌套在 args 中：

```json
[
  {"action":"workbench","page":"etm","op":"read","selector":"#job-state"},
  {"action":"workbench","page":"etm","op":"describe","target":"history"}
]
```

## 结果、恢复与边界

`ok:true` 代表队列请求成功执行。click/set/upload/event 返回 `completed:false`，
页面仍可能异步失败；invoke 返回 `verificationRequired:true`，原方法可能捕获了错误。
必须读取页面日志、业务结果和质量。超时不会取消或重试硬件操作，使用返回的job ID查询，
不要重放烧录、写寄存器、复位或采集。长任务用 interrupt 停止。
任务保留一小时、最多200条，长脚本应 ack 已记录结果。batch非事务，不回滚硬件。
导出最多暂存32个，保存后 discard；刷新会清空暂存。单文件上传上限24 MiB。

```powershell
python -m unittest discover -s tools/tests -p 'test_toolbox*.py'
node --test web/tools/selftest/trace-cli-automation.test.mjs
python -X utf8 tools/accept_web_cli.py --runtime R --out build/cli-smoke-001
python -X utf8 toolbox.py trace doctor
```

模拟/离线与实板分开记录；进展和未完成项见
[2026-10-30验收记录](validation/web-cli-f103ze-20261030/README.md)。
