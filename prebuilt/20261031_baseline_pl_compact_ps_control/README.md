# 旧PL / 最终紧凑PS诊断对照

此bit来自旧 `13c7b52` filtered TPIU基线，特意复用于归因，**不是本次优化重新综合的bit**。
ELF来自最终固件 `cbedca2`，PS初始化与优化配对相同，控制变量为PL bit。

同一ELF、同一PS配置、同一实际100MHz FCLK/50MHz SWD，旧新PL各5×3秒八变量对照，
超载吞吐差小于0.5%，无跳点100kHz工作点一致；严格数据/序号/计数校验通过。
JTAG长窗读写也通过。旧PL的RTT25/30MHz请求仍失败，原始失败与恢复校验保留。

此组合只作诊断对照，不替代交付配对，不宣称整套ETM/所有频点已验收。
[完整归因](../../docs/validation/orbtrace-hardware-20261031/README.md)；实际文件SHA/源版本见清单。
