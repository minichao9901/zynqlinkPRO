# 有限DDR采集的隔离实验模块

此目录不在生产`fpga/rtl/*.v`构建集合中。不能拿当前已加载的内存pilot bit声称这些模块已上板。

- `etm_ddr_packetizer.v`：128bit帧/有效长度/EOF转AXIS64，保留最后一拍到确定EOF，正确生成TKEEP/TLAST，空记录不伪造DMA拍。
- `etm_ref_window.v`：独立参考时钟域的精确N周期窗口，锁定请求长度；忙时拒绝重新开始，停止报告实际周期及原因。窗口done只表示关窗，不能表示DDR已完成。
- `etm_frame_async_fifo.v`：带长度/EOF元数据的134bit跨域FIFO，同步BRAM读、寄存输出，背压时保持数据；容量包括尚未被消费的输出项。

计时输入命令必须已进入ref_clk域；顶层还需实现配置CDC握手、源停止确认、最后部分帧/EOF可靠入队、
物理不可停源的拒收计数，以及全部AXI写响应完成后才发布记录。跨域reset必须属于同一捕获epoch，
在捕获之间同时断言、分别同步释放。捕获时不能因为USB配置变化清FIFO。

AI仿真入口：`python toolbox.py project run etm.capture-sim -- --out NEW_DIR`。
8/512项FIFO均测试独立时钟、反压、多次指针回绕、停写/停读时钟、元数据完整性和下一捕获复位。
每个变体覆盖12项参考窗口用例；这不是已经模拟或实测了200MHz参考时钟下的完整1～2秒采集。
