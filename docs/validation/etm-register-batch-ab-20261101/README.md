# 多寄存器访问 A/B

同板、同已加载bit/ELF、相同目标ELF和100ms采集窗口；默认C++二进制/TraceStore链路。逐轮CSV等价数据见analysis.json，完整控制地址/阶段计数在captures.json，etmrecord包括原始ETM、FRM1、目标ELF、源码及采集/解码元数据。

AI复测命令（工作台须已打开对应runtime的鉴权URL，输出目录须为新目录）：

```powershell
python tools/stress_etm_web.py --runtime build/etm-register-batch-ab-20261101/runtime --artifacts build/register-batch-repeat-new --rounds 3 --capture-rounds 6 --milliseconds 100 --functions cdc_poll,cdc_poll --echo --cdc-port COM34 --case-timeout 120 --profile-control --native-exchange on --packed-memory on --register-batch alternate
```

没有写目标Flash/QSPI，也没有由主机改变目标分频；配对身份见runtime声明与统一文档已加载配对的验收记录。live-clocks.json为这次测试结束后只读回读，FCLK约120MHz、SWCLK约1MHz。不是10MHz SWCLK实验，也不是高于24MHz TRACECLK实验。

本阶段保持PPB双读、写完成屏障、逐项回读、RCC变化检查和恢复；节省的是HTTP往返次数。6轮样本中控制交换734→632，但完整流程中位只改善约4.6%，不能推导实时显示或1秒级验收已完成。
