# ZynqDAP Web 工作台

从 **superlinkPRO/Web** 原样拷贝后做减法的工具箱：保留串口助手、终端、RTT Viewer、RTT 转发、J-Scope、烧录器、调试器、ETM 执行轨迹、工程生成。页面源码仍是 superlinkPRO 的模块化 ES module，没有改用合并包。

## 启动

```powershell
node web/tools/serve.mjs      # 默认 http://127.0.0.1:8898
```

ETM 执行轨迹页需要本地 `etm-service`：

```powershell
cd etm-service
python server.py --port 8766
```

## 删掉的功能

按需求移除，导航、DOM、模块和帮助文案都已清理：

- USB→SPI/QSPI
- SPI/QSPI 屏
- SPI 转发
- SWO 执行轨迹
- USB→I2C
- USB→ADC/DAC

`web/app/{spi,spi-cdc,i2c,analog,swo}` 已删除；`main.js`、`probe-users.js`、`probe-status.js`、`event-logs.js`、`gen/view.js` 中对应入口也删了。工程生成页不再生成旧的 ETM 桥包。

## ETM 页

`#tab-etm` 是 iframe，指向 superlinkPRO 的原始 ETM 工作台（`http://127.0.0.1:8766/`），由 `etm-service` 提供页面、Zynq 采集和解码。页面内的“② 逻辑分析仪”已替换为“② Zynq ETM 接收”。

`web/app/etm/view.js` 只做服务探测和 iframe 管理；不包含 ETM 分析逻辑。

## 设备通路

| 功能 | 通路 |
|---|---|
| 串口 / 终端 | Web Serial |
| RTT / 烧录 / 调试 | CMSIS-DAP WebUSB（EP1/EP2） |
| RTT 转发 / J-Scope | HID 控制 + CDC / HSS bulk-in |
| ETM | superlinkPRO 原始页面 + `etm-service` 的 Zynq EP2 `0x82` |

ETM 与其它探针功能共用同一台 ZynqDAP。ETM 采集期间浏览器会释放 USB，由本地服务独占；结束后页面自动重连。其它页签不要在采集窗口内同时占用探针。

## 验证

- 9 个页签逐页点击无控制台错误、无 404；六个删除页面的 DOM/导航均为 0。
- ETM 页载入记录后显示 6,368 路径 / 1,287 包 / 1 中断，火焰图可打开。
- 实板采集待 ZynqDAP 接回后复核（详见 `etm-service/README.md`）。
