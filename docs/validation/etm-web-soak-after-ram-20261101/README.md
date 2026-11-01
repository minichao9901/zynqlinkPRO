# SRAM实验恢复后的Web压力验收

同一已加载prebuilt/etm-ddr-usb-raw4-20261101配对，target已通过复位返回原Golden CPU48MHz / TRACECLK24MHz固件。没有写Flash/QSPI，没有由Web改目标分频。新runtime本地桥默认C++ binary/TraceStore链，界面由AI CLI实际操作。

```powershell
python tools/stress_etm_web.py --runtime build/etm-register-batch-ab-20261101/runtime --artifacts build/etm-web-soak-repeat-new --rounds 30 --capture-rounds 20 --milliseconds 100 --functions cdc_poll,cdc_tx_poll --echo --cdc-port COM34 --case-timeout 120 --profile-control
```

30次纯打开/关闭，加20轮打开→交替函数断点→100ms采集→原生解码→恢复→关闭全部通过。没有失败重试；RCC逐轮一致、无传输loss、packetIssues合计0、清理错误0，硬件窗口内每轮4～6次完整精确CDC echo。打开中位0.632秒，范围0.523～0.806秒。耗时仅记录，不是当前优化重点。

analysis.json为汇总，captures.json/summary.json保留每笔CDC摘要、控制地址/阶段及解码结果。20份etmrecord包含原始ETM、FRM1、目标ELF、源码、会话及解码/性能元数据，可脱离worktree重放。live-clocks.json为结束后只读时钟核对；post-soak-echo.json为结束后额外13次精确CDC echo。final-web.png保留最后一轮显示及已释放探针的界面。

结论限于本次24MHz及有限轮数。更高TRACECLK、独立tap调节效果和H743板尚未验收；另见SRAM36MHz失败证据。它们不能由本压力结果替代。
