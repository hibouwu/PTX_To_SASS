# Pass 13：`remove_unreachable_basic_blocks`

源码：[`../ptx/src/pass/remove_unreachable_basic_blocks.rs`](../ptx/src/pass/remove_unreachable_basic_blocks.rs)

## 契约与变换

输入函数体必须已由 Pass 12 规范化且首项为 label。本 Pass 为每个函数构建 intra-procedural CFG，从首块 BFS，删除不可达块；同时收集 call target，最后保留 kernel 和被调用 method。

输出不变量：每个保留函数体只含入口可达块；未被任何直接 call 引用的非 kernel directive 可能被删除。

## 顺序依赖

必须在规范 CFG 后运行，并在浮点/异步数据流分析前移除不可达语义需求。

## 现代指令接入

普通 opcode 无需修改。新增 branch/terminator/call-like 指令必须加入 CFG edge 和 reachable-function 收集；异步状态合并不属于本 Pass。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| `FunctionPointer` statement | 明确 `return Err(error_todo())` | 间接调用 pipeline 未打通 |
| unreachable 块中的 call | 扫描时先收集所有 call，再做 BFS 过滤 | 目标函数会被保守保留，不影响正确性但不精确 |
| 新 terminator 未建 edge | match 只识别 Conditional/Bra | 可能错误删除可达块；必须更新 |

## 测试要求

当前无专属 fixture。补 diamond、loop、死块、死块 call、直接/间接 call、未知 branch target 和新控制流指令测试。
