# ETM Golden Reference

2026-11-03：合并前 main 已固定为 annotated tag `archive/main-before-etm-cpp-20261103`，对应提交 `06452f2`。该 tag 保留当时的源码、已跟踪原生程序及历史验收，不随 main 后续优化移动。只在用户明确要求时推送 tag。

旧 Python 实现继续保留，用于优化后的差分参考。它不是可删除的冗余代码，也不能未经重新验收就按新实现同步改写。main 是持续开发分支；golden 是明确版本、输入和依赖的组合，两者不能在合并后混称。

## 两层参考

1. **固定历史流程**：以上 tag 的 main 方案，保留其原始二进制和依赖身份。它本来就是 OpenCSD/C++ 解码核心加 Python 静态处理、索引及读取的混合实现，不是从原始 ETM 到最终结果的纯 Python 解码器。本机只读参考 worktree 位于 `E:/zynqlinkPRO-work/etm-golden-main-20261103/`。
2. **当前仓库中的 Python 参考模块**：`static_dict.py`、`trace_store.py`、`native_facts_index.py`、旧索引/最终发布实现继续供显式差分。`ETM_NATIVE_STATIC=0`、`ETM_NATIVE_QUERY=0`、`ETM_COMPLETE_INDEX=0` 可分别选择静态、读取、索引参考；产品入口仍按原生配置运行，不能把这些变量误解为“一键启用完全独立的纯 Python 解码器”。需要完整流程参考时运行固定 tag 的代码。

参考与候选共享 OpenCSD、目标 ELF/固件和一部分格式定义，逐项一致只能证明回归范围内相容，不能排除共同缺陷，更不能替代硬件完整性或 ARM 协议正确性的独立证据。ZL-117 的旧协议标签错误属于已知 golden 缺陷，故障名称/标签应按实际协议单独验证，不能要求新实现复制错误。

## 固定输入和检查范围

- F103 大记录：`docs/validation/zl006-cpp-stage1-20261102/f103-large-input/`。
- H743 1 秒：`docs/validation/h743-comprehensive-20261101/raw/etm20-4ms-matrix/1000ms-1/`。
- H743 2 秒：`docs/validation/h743-flame-20261102/raw/corrected/record/`。
- 各记录原始 ETM、目标 ELF、Sources 的 SHA，以及依赖、原生程序和全部数组身份，见对应报告的 manifest。旧报告的板上状态仅为历史快照。

常规回归比较完整执行/静态块、诊断、analysis、默认视图、60 张索引数组的 dtype/shape/每个值，以及随机/边界查询 DTO；不能只比较指令总数。用 `validate_etm_complete_index.py` 检查 Python 索引与 C++，用 `validate_etm_native_images.py`、`validate_etm_native_queries.py` 检查静态和读取，用 `validate_etm_redecode.py --main-root <固定tag的worktree> ...` 检查旧流程升级和输入绑定。

历史旧 decoder 有 ZL-116 输出路径限制，参考回归的输出使用 `E:/zynqlinkPRO/build/` 下的新目录；不改写 golden 程序来掩盖这个边界。基准升级应另建版本/tag，保留旧证据并记录原因，不移动本 tag。

本次主线集成、Web 分支冲突核对及固定程序回归见 [集成报告](validation/etm-main-integration-20261103/README.md)。
