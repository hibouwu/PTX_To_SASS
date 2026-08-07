# Pass 05：`resolve_function_pointers`

源码：[`../ptx/src/pass/resolve_function_pointers.rs`](../ptx/src/pass/resolve_function_pointers.rs)

## 契约与变换

本 Pass 收集非 kernel method ID，并把源为已知函数 ID 的 `mov.u64` 改成 `Statement::FunctionPointer { dst, src }`。非 `u64` 形式返回类型错误。

输出不变量：已识别的函数地址不再伪装成整数 move。注意当前 LLVM statement emitter 对 FunctionPointer 路径仍未完整实现，因此“识别成功”不等于可 codegen。

## 顺序依赖

必须在 `expand_operands` 前保留 `Mov` 的 `ParsedOperand::Reg` 形态，在 identifier normalization 后获得函数 ID。

## 现代指令接入

与大多数现代 opcode 无关。若新增虚调用、calltargets 或函数表语义，需要完整的间接调用设计，而不是继续扩大这个模式匹配 Pass。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| move 引用后置函数声明 | 函数集合在遍历 directive 时边收集边使用 | 识别受声明顺序影响；审查未通过 |
| function pointer 进入不可达块删除 | Pass 13 对 `FunctionPointer` 返回 TODO | 当前完整 pipeline 仍会失败 |
| 非 u64 地址 move | 显式 `error_mismatched_type` | 已拒绝 |

## 测试要求

当前无专属 fixture。必须增加前置/后置声明等价性、声明与定义、间接 call、不可达块和最终 LLVM codegen 测试。建议先全量收集函数 ID，再做第二遍改写。
