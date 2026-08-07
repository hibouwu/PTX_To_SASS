# Pass 12：`normalize_basic_blocks`

源码：[`../ptx/src/pass/normalize_basic_blocks.rs`](../ptx/src/pass/normalize_basic_blocks.rs)

## 契约与变换

本 Pass 为函数入口和 terminator 后续补 label，在 label 前补显式 `bra`，把内部 call 当作“假 terminator”并生成 call 后 continuation branch；普通函数多个 `ret` 合并到单一返回块。kernel 不合并 ret。

输出不变量：每个基本块以 label 开始，边由显式 terminator 表达；内部 call 后有 Pass 14 预期的 continuation branch。

## 顺序依赖

必须在谓词展开后、不可达块删除和全局模式 CFG 分析前。建议异步协议 Pass 位于 Pass 14 后，看到最终模式 prologue/重定向后的 CFG。

## 现代指令接入

普通 opcode 无需修改。新增控制流终结指令、call-like、exit-like 或改变 CFG 的现代指令必须更新 `is_block_terminator`；仅靠生成 visitor 不会自动完成分类。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 输入 body 首 statement 已是 label | 实现会消费该 label，不放回 result | 依赖“首 label 仅是入口占位”的隐含假设；需 branch-to-entry 反例测试 |
| internal call | 明确插 continuation branch | 满足 Pass 14 的跨函数 CFG 模型 |
| 新 terminator 未分类 | 默认 `TerminatorKind::Not` | 会构造错误块；必须显式更新 |

## 测试要求

现有专属 fixture 主要覆盖 `trap`。必须补 fallthrough、连续 label、首 label 被回边引用、多个 ret、internal/external call、exit 和每个新增 terminator。
