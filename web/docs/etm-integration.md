# Web 工作台的 ETM 入口

从本机 `dist/zynq-etm-bridge/zynq-etm-bridge.exe` 启动，在「更多功能」进入 ETM 执行轨迹。源码开发从仓库根目录运行：

```powershell
python -X utf8 toolbox.py --runtime build/etm-web-new serve --port 0 --open-browser
```

本地服务负责采集后端、OpenCSD 解码和记录查询。在线静态页提供工作台入口，本机记录保存在用户数据目录。

- 有探针时，以实际加载的探针 bit 和 PS ELF 启动服务，读取目标身份后载入匹配运行固件的目标 ELF。[连接和参数](../../docs/toolbox-cli-ai.md#启动与操作-web)
- 离线时可导入 `.etmrecord` 或使用仓库样本。裸数据需要匹配的目标 ELF、协议和原采集配置。[保留样本](../../docs/retained-records.json)
- 当前融合版的采集、核验和导出以 [Trace CLI](../../docs/Trace-CLI使用说明.md) 为准。Web 的 ABI 2 专用操作范围见[融合验收](../../docs/validation/README.md)。
