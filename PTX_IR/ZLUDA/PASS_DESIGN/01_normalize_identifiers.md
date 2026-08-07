# Pass 01：`normalize_identifiers`

源码：[`../ptx/src/pass/normalize_identifiers.rs`](../ptx/src/pass/normalize_identifiers.rs)

## 契约与变换

输入是带字符串名称和作用域的 parser AST。Pass 为函数、参数、变量、标签和操作数分配 `SpirvWord`，并在 resolver 中登记可知的类型/状态空间。它先收集同一 statement 列表中的全部 label，再解析引用，因此块内前向 branch 可工作；嵌套 block 使用独立 scope。

输出不变量：合法引用绑定到唯一 ID；instruction 仍可能携带 `PredAt`，操作数仍可能是 `ParsedOperand`。本 Pass 不做 target、opcode 或谓词合法性验证。

## 顺序依赖

必须是第一项。后续特殊寄存器、函数符号、临时值和类型查询都依赖 resolver。移动到谓词或操作数展开之后会丢失可靠的作用域绑定。

## 现代指令接入

若新 AST variant 的参数元数据由 visitor 完整描述，通常自动覆盖。descriptor、TMEM 地址或 mbarrier 参数若引入新的值类别，resolver 还需保存该语义，不能只保存同宽标量类型。

不需要为独立现代 opcode 新建 Pass；需要扩展符号表时修改本 Pass/Resolver。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 函数声明带 `shared_mem` | `run_function_decl` 使用 `assert!(shared_mem.is_none())` | 会 panic，而非结构化诊断；未通过健壮性审查 |
| branch 引用后置 label | `run_statements` 先遍历并注册 label | 该反例已处理 |
| 新 operand 字段未进入生成 visitor | `run_instruction` 只调用 `ast::visit_map` | 编译可能通过但引用不会被映射，必须加 visitor 覆盖测试 |

## 测试要求

当前 `pass/test` 下无专属 fixture。至少补：同名嵌套变量、前向/后向 label、数组初始化符号、新指令全部 operand 字段，以及 `shared_mem` 应返回错误而非 panic。
