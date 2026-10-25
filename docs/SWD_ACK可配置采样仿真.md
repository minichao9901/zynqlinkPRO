# SWD ACK 可配置采样仿真

本轮只调整 ACK 前后的时钟状态机，读数据状态机保持原路径。

`SWD_CFG` 新增两个字段：

- `[24:23] cfg_turn_extra`：目标释放 SWDIO 后，在第一次 ACK 前额外保持低电平的完整 turnaround 周期，范围 0～3。
- `[27:25] cfg_ack_delay`：每个 ACK 位的高相位额外保持 FCLK 拍数，范围 0～7。ACK 位在高相位保持期间不推进到下一位，下降沿前再取样。

固件 vendor 命令：`0x83` 设置/查询 `turn_extra`，`0x84` 设置/查询 `ack_delay`。传输忙时命令返回错误，避免在一笔 SWD transfer 中途改时序。

仿真模型让目标在 SWCLK 上升沿推出 ACK，并加入目标输出延迟；使用 WAIT ACK（`010`）避免 SWDIO 上拉把迟到的 ACK0 伪装成 1。运行：

```powershell
python tools/simulate_swd_ack.py
```

当前结果：基线 `TCO=1 ns, ack_delay=0` 通过；`TCO=8 ns, ack_delay=0` 通过；故意设置 `TCO=20 ns` 时 `ack_delay=0` 得到错误 ACK，`ack_delay=1` 恢复为正确 ACK。说明 ACK 延后必须同步延长 SWCLK 的高相位，单独把软件采样动作延后会错位。

这组参数先用于仿真和小范围实测，不能直接等同于 60 MHz 以上一定可用。真正上板时还需检查 SWDIO 线路、IO 延迟和目标的实际输出延迟。
