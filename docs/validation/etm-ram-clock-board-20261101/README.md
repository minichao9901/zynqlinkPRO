# SRAM固件24/36MHz输入对照

实验使用同一已加载PL/PS配对prebuilt/etm-ddr-usb-raw4-20261101；没有改RTL/PS，没有新bit或新的STA验收声明。target固件由prebuilt/f103ze-cdc-ram-clock-20261101加载到SRAM，CPU频率来自target自身SystemClock_Config，RCC和固件诊断均已核对。SWCLK为1MHz，TRACECLK值按目标HCLK/2推算。

trace24mhz：100ms、1s采集和完整原生packet/range检查通过，保存FRM1及ETM原始数据、解码总结和可导入记录。trace36mhz：首轮100ms就失败，没有重试或执行下一轮；保留原始capture.frm1和具体错误计数，不用不可信数据创建通过的解码记录。USB在硬件窗口结束后才下载。

loader.json显示实验前后Flash字节一致、RCC恢复，36MHz质量失败没有妨碍返回原48MHz Flash固件。result.json包含CDC逐笔echo时间/摘要和严格硬件窗口判定。原生临时native.bin体积大，可从保留的原始数据和明确的ELF重建，未纳入Git。

36MHz硬件采样/成帧损坏：23,741个parser错误、23,742次同步获取；frameDrops=0、writerError=0、IDELAY ready loss=0、FIFO highwater=1。不能据此认定某根杜邦线的具体电气故障，也不能把IDELAYCTRL RDY当成逐线眼图校准完成。当前RAW4仍未使用可调的逐线IDELAY输出。
