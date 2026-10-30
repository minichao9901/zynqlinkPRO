# ZynqDAP toolbox CLI —— 给 AI 用的总入口

本文件是给 AI 的第一阅读入口。CLI 在 `web/tools/toolbox.mjs`，为一句白话：
**把「人去点网页」换成「AI 发命令，网页照做」**。

它不自己开设备、不碰 USB。请求走本机队列交给**已经打开的工作台页面**执行，所以串口、
WebUSB、HID 的能力、会话、资源互斥都还留在浏览器里，CLI 只是借用。

## 1. 先记住这三条

1. `ok:true` 只代表 **CLI 请求被处理**，不代表硬件任务成功。`click`/`set` 返回
   `completed:false` 表示事件已投递；还要 `state` / `read` / `wait` 去看页面自己怎么说。
2. **超时不要重放**烧录、写寄存器、复位、采集。用 `job <ID>` 查；任务可能还在跑。
3. 第一次连接 USB / 串口 / HID 必须在**真实浏览器窗口**里由人授权一次，CLI 造不出这个手势。
   授权过之后，刷新页面仍可复用，CLI 就能全程驱动。

## 2. 启动与最短路径

需要 Node 18+（仓库已有）。在仓库根目录：

```powershell
node web/tools/toolbox.mjs --runtime build/toolbox-001 serve --port 8896 --open
```

`serve` 会创建运行时目录、打印 `browserUrl`，并用 Edge/Chrome 打开它。**保持这个页面**。
运行时目录必须不存在或为空；带一次本机令牌，别提交、别外传。

另开一个终端：

```powershell
node web/tools/toolbox.mjs --runtime build/toolbox-001 ping
node web/tools/toolbox.mjs --runtime build/toolbox-001 page etm describe
node web/tools/toolbox.mjs --runtime build/toolbox-001 page etm state
```

`--open` 用真实窗口（能授权设备）；想无头跑自检用 `--open --headless`，或直接
`node web/tools/toolbox-selftest.mjs`（自己起服务、自己开无头浏览器、跑完整套）。

## 3. 命令表

全局参数写在子命令前：`--runtime <目录>`、`--timeout <秒>`（默认 60）、`--out <新文件>`
（JSON 结果，拒绝覆盖）。退出码 0 成功 / 1 失败 / 2 参数错。

| 命令 | 说明 |
|---|---|
| `catalog` | 不用服务，列出九个页面和功能范围 |
| `serve --port 8896 [--open] [--headless]` | 建运行时 + 前台跑本机服务 |
| `ping` | 页面是否在线、队列深度 |
| `status` | 工作台摘要（`summary()`，含各页 summary） |
| `page P describe` | 当前控件（selector/type/value/options/disabled/label）+ 公开方法 |
| `page P state` | 页面文字（最多 20000 字）、最近异常、摘要 |
| `page P show` | 切到该页面 |
| `page P reload` | 让页面重新加载（改完前端代码后用） |
| `page P read SELECTOR` | 读一个控件的值/文本 |
| `page P set SELECTOR JSON值` | 写参数并触发 `input`/`change`；复选框用 `true`/`false` |
| `page P click SELECTOR` | 点未禁用的控件；只投递，不等异步完成 |
| `page P invoke METHOD [--args JSON \| --args-file F]` | 调页面公开方法，等它返回 |
| `page P event SELECTOR TYPE [--data JSON]` | 键盘/鼠标/pointer/wheel/input/change |
| `page P upload SELECTOR FILE...` | 放进真实 file input 并触发 change（单文件 ≤24 MiB） |
| `page P wait SELECTOR --contains 文字` | 页面内轮询直到匹配或超时 |
| `page P downloads` | 列出这次页面会话里导出的文件（Blob 被接管，不会落进下载目录） |
| `page P download ID FILE` | 取回一个导出文件，写盘并校验 SHA-256（实测一致） |
| `request F.json` / `batch F.json` / `job ID` | 单条请求 / 顺序批处理 / 查任务 |

`P` 取：`serial`、`terminal`、`rtt`、`rttcdc`、`scope`、`flash`、`dbg`、`etm`、`gen`。

`invoke` 只允许视图对象上**不以 `_` 开头**的函数，不执行 eval，也不接受任意对象路径。
`describe` 返回的 `methods` 就是当前真正可调的清单——不要猜。

## 4. 典型用法

### 不接板子也能跑的三条链路

```powershell
# 调试器模拟目标（内置 Cortex-M7）
node web/tools/toolbox.mjs --runtime R page dbg set '#d-backend' '"mock"'
node web/tools/toolbox.mjs --runtime R page dbg click '#d-connect'
node web/tools/toolbox.mjs --runtime R page dbg wait '#d-out' --contains '已连接：模拟目标'

# J-Scope 假探针采样
node web/tools/toolbox.mjs --runtime R page scope set '#sc-mock' true
node web/tools/toolbox.mjs --runtime R page scope click '#sc-start'
node web/tools/toolbox.mjs --runtime R page scope read '#sc-samples'

# ETM 实板记录样例 → 解码 → 调用树
node web/tools/toolbox.mjs --runtime R page etm click '#ze-sample-f103'
node web/tools/toolbox.mjs --runtime R page etm wait '#ze-log' --contains '调用树'
node web/tools/toolbox.mjs --runtime R page etm invoke summary
```

### 接板子（人先授权一次）

```powershell
# 串口：先在页面里选端口并「连接」，之后 CLI 发数据
node web/tools/toolbox.mjs --runtime R page serial describe     # 查控件
node web/tools/toolbox.mjs --runtime R page serial invoke sendText --args '["hello\r\n"]'

# ETM：连 ZynqDAP → 载入 ELF → 采集 → 解码 → 读结果
node web/tools/toolbox.mjs --runtime R page etm click '#ze-connect'
node web/tools/toolbox.mjs --runtime R page etm upload '#ze-elf' E:/fw/fw-ze.elf
node web/tools/toolbox.mjs --runtime R page etm click '#ze-start'
node web/tools/toolbox.mjs --runtime R page etm wait '#ze-status' --contains 'ETM 字节'
node web/tools/toolbox.mjs --runtime R page etm invoke summary
```

### 导出并核对

```powershell
node web/tools/toolbox.mjs --runtime R page etm invoke exportCsv
node web/tools/toolbox.mjs --runtime R page etm invoke exportSvg
node web/tools/toolbox.mjs --runtime R page etm downloads
node web/tools/toolbox.mjs --runtime R page etm download 1 build/etm-flow.csv
```

`download` 会写文件并回 `{size, sha256, picked:true}`，`picked` 表示落盘后重算的 SHA-256
和页面给出的一致。实测 1309 字节实板样例：CSV 335,153 字节 / 6369 行、SVG 1261 字节。

### 批处理

```json
[
  {"page":"etm","op":"read","args":{"selector":"#ze-status"}},
  {"page":"etm","op":"invoke","args":{"method":"summary"}}
]
```

```powershell
node web/tools/toolbox.mjs --runtime R batch actions.json
```

## 5. 已知边界

- **浏览器特权操作仍需人手**：首次设备选择、系统文件夹选择、全屏、剪贴板。
- **导出文件走 CLI 接管**：页面导出（CSV/SVG/JSON）会被 `downloads` 列出来，`download` 取回
  并核对 SHA-256；单次上限 16 MiB，页面刷新后清单清空。
- 没有 `interrupt`（长任务停止请点页面上的「停止」按钮）、没有 `ack`（服务只在内存里留
  最近一小时的 job）。
- 一个服务只服务一个执行页面；多开标签会互相抢队列。
- 离线/模拟自检不能替代真机验收。

## 6. 维护与验收

```powershell
node web/tools/toolbox-selftest.mjs     # 真起服务 + 无头浏览器 + 真跑 CLI 子进程
node web/tools/check.mjs                # 模块语法/本地依赖/页面容器
node --test web/tests/*.test.mjs
```

改动 `toolbox.mjs` 的命令或页面能力后，同步更新本文件的命令表和 `catalog`。
新增页面时，`web/app/main.js` 的 `pages` 表和 `catalog` 都要加，否则 `describe` 会报
「没有这个页面」。
