# ETM 差分参考

现行原生 ETM 解码、索引及查询可以和仓库中的 Python 路径对照。`ETM_NATIVE_STATIC=0`、`ETM_NATIVE_QUERY=0`、`ETM_COMPLETE_INDEX=0` 分别选择各层的 Python 参考实现。两条流程共享 OpenCSD 和目标 ELF。回归需比较执行事件、诊断、静态结构、索引数组和查询结果。

| 检查 | 入口 |
|---|---|
| 离线样本和服务接口 | `toolbox.py project run etm.records-check` · [样本清单](retained-records.json) |
| Python 和原生结构差分 | `toolbox.py project run etm.equivalence -- --help` |
| 静态块、查询和完整索引 | `tools/validate_etm_native_images.py`、`tools/validate_etm_native_queries.py`、`tools/validate_etm_complete_index.py` |
| 当前 H743 RAW4 板测 | [历史 CDC ELF 同板复验](validation/h743-cdc-golden-requal-20261123/README.md) |

需要原版历史流程和固定输入时，使用 tag `archive/main-before-etm-cpp-20261103` 及 [融合前档案](validation/README.md#融合前档案)。旧实验输入与既有问题按清理前提交中的说明取回。
