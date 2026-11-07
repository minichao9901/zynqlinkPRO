# ETM 独立页面共享模块

本目录的 JavaScript 文件是 `web/app/` 中同名相对路径的逐字节副本。独立 ETM 页面使用这些副本加载探针资源协调、定时、源码与断点编码。OpenOCD Wasm 及其 USB 依赖由 ETM 服务的 `/app/openocd/` 路由直接提供。

修改共享模块后，在仓库根目录同步并校验。

```powershell
python -X utf8 tools/sync_etm_shared.py --write
python -X utf8 tools/sync_etm_shared.py --check
```
