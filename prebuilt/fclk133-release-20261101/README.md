# FCLK133 release 配对

实际板测使用的一对产物，`RTL_DEBUG=0`：

- `probe.bit` SHA-256 `af1031d3caa0d7bd3b6adffa911d26efdab9e0bfb5223fb18f70dabb70ebeeed`
- `application.elf` SHA-256 `2137f7d0f507c08574f36223130103c0710645cbfdefb5c1d8c8efb0cfb990a0`

来源：RTL `e749c426a018cab6f543415772bbe88efb6652e4`的冻结布线，133.333 MHz重新完整STA/bitgen；配套固件与验证来源`0118b1610e91c770cdf801863a576726b59f9f33`。未用旧预编译产物代替本次生成。

启动/明确选择的DDR录制工作点：现有ARM PLL /10，寄存器读回计算133,333,332 Hz。普通DAP调速保持原IO PLL策略，60 MHz链路使用约120 MHz FCLK；SWCLK/TCK固件上限仍为60 MHz。133.333 MHz录制验收使用约995.025 kHz的标准SWD控制波形。

预留DDR尾100 MiB：`0x39C00000..0x40000000`（end exclusive）。1秒、2秒录制和100 MiB写满停止均通过；采集中不做USB下载，采完再下载。STAs、实际计数器/时钟、字节/序列检查及完整哈希见[验收记录](../../docs/validation/fclk-resume-20261101/release-133/README.md)和`validation.json`。

独立60 MHz SWD RTT在暂停目标ETM输出的同条件下与Golden一致。目标ETM保持输出时，本板的原Golden和新配对均出现RTT访问错误；并行输出场景未通过。25 MHz JTAG RTT已验收，60 MHz JTAG RTT失败记录保留。已有5个双向端口的外部delay覆盖及CDC警告仍需独立签核，不能将本次板测当作所有接口/所有目标的正式时序认证。

实际加载（不写QSPI）：

```powershell
$env:ZYNQLINK_WORK_DIR = 'E:\zynqlinkPRO\build\fclk133-runtime'
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/fclk133-release-20261101/application.elf prebuilt/fclk133-release-20261101/probe.bit prebuilt/fclk133-release-20261101/ps7_init.tcl
```

必须整对加载并使用本目录的`ps7_init.tcl`。原`prebuilt/golden`和QSPI恢复包保持原样；本目录不修改Flash，断电后的启动镜像取决于板上原QSPI内容。
