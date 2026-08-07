# PTX→NVVM Pass 文档索引

本目录把当前 pipeline 的 19 个变换 Pass 分开记录。总览只说明顺序和层次；实现细节、输入输出契约、现代指令接入点和对抗式审查结论以各 Pass 文档为准。

## 阅读规则

- “当前”表示 `ptx/src/pass/mod.rs::to_llvm_module()` 已执行的代码。
- “建议”表示接入现代 PTX 指令族时的设计，不代表已经实现。
- 每个结论必须能指向源码分支、测试或明确缺失；仅仅“编译通过”不是语义证据。
- 新增 AST variant 后，所有穷尽 `match` 都要重新分类；带通配分支的 Pass 也要做定向测试，不能把静默透传当成正确。

## 当前顺序

| # | Pass | 核心输出不变量 | 独立文档 |
| ---: | --- | --- | --- |
| 01 | `normalize_identifiers` | 名称绑定为唯一 ID | [01](01_normalize_identifiers.md) |
| 02 | `replace_known_functions` | 已知运行时符号完成重命名 | [02](02_replace_known_functions.md) |
| 03 | `normalize_predicates` | instruction 不再携带谓词 | [03](03_normalize_predicates.md) |
| 04 | `optimize_function_arguments` | 特定 `.param b8[]` 规范为 `b32[]` | [04](04_optimize_function_arguments.md) |
| 05 | `resolve_function_pointers` | 函数地址 move 变为专用 statement | [05](05_resolve_function_pointers.md) |
| 06 | `fix_special_registers` | 特殊寄存器读取变为 call result | [06](06_fix_special_registers.md) |
| 07 | `expand_operands` | instruction operand 全部扁平化为 ID | [07](07_expand_operands.md) |
| 08 | `insert_post_saturation` | 浮点 `.sat` 变为显式后处理 | [08](08_insert_post_saturation.md) |
| 09 | `deparamize_functions` | 普通函数跨边界使用寄存器 ABI | [09](09_deparamize_functions.md) |
| 10 | `rcp_f64_into_div` | compliant reciprocal 变为 `1/x` | [10](10_rcp_f64_into_div.md) |
| 11 | `replace_instructions_with_functions_fp_required` | rounding div 变为带模式标记的两段 helper | [11](11_replace_instructions_with_functions_fp_required.md) |
| 12 | `normalize_basic_blocks` | CFG 块和 terminator 规范化 | [12](12_normalize_basic_blocks.md) |
| 13 | `remove_unreachable_basic_blocks` | 函数体只保留入口可达块 | [13](13_remove_unreachable_basic_blocks.md) |
| 14 | `instruction_mode_to_global_mode` | 指令级 FP 模式变为显式全局模式状态 | [14](14_instruction_mode_to_global_mode.md) |
| 15 | `insert_explicit_load_store` | `.reg/.param` 变量使用显式化 | [15](15_insert_explicit_load_store.md) |
| 16 | `convert_32bit_to_64bit` | 32 位模块获得 64 位承载与 metadata | [16](16_convert_32bit_to_64bit.md) |
| 17 | `insert_implicit_conversions` | 类型和地址空间转换全部显式 | [17](17_insert_implicit_conversions.md) |
| 18 | `replace_instructions_with_functions` | 选定 opcode 变为显式 helper/intrinsic call | [18](18_replace_instructions_with_functions.md) |
| 19 | `hoist_globals` | 可发射全局对象位于 module 层 | [19](19_hoist_globals.md) |

`get_fp_mode`、`llvm::emit::run` 和 `llvm::attributes::run` 是后续决策/发射阶段，不计入 19 个变换 Pass。

## 现代指令族是否需要新 Pass

| 新语义 | 处理位置 | 新 Pass？ |
| --- | --- | --- |
| 独立 opcode，操作数和结果立即可用 | AST、既有分类 Pass、emitter/intrinsic | 通常不需要 |
| 新 shape/type/modifier | parser 类型、Pass 7/8/14/17/18 的相应规则 | 通常不需要 |
| 新 target feature 或立即数合法组合 | module validator | 建议新增早期 `validate_target_features`，也可放 parser validation |
| 跨指令 pending/ready、commit/wait、资源生命周期 | CFG 数据流与物化 | 需要窄职责协议 Pass |
| SASS scoreboard、wait mask、reuse/control bits | LLVM NVPTX backend/ptxas | 不应新增前端 Pass |

建议 Pass 的契约见 [PROPOSED_PASSES.md](PROPOSED_PASSES.md)。是否新增 Pass 的判断标准不是“opcode 新不新”，而是语义是否跨越多条 statement 或 CFG 边。

## 对抗式审查门槛

每个 Pass 的审查均回答四个问题：

1. 有什么输入能反驳文档所称的不变量？
2. 源码是显式拒绝、panic、静默透传还是正确处理？
3. 现有测试是否覆盖该反例？
4. 接入现代指令时应修改本 Pass，还是在其前后建立新语义边界？

只有反例被源码约束或测试覆盖，才标记“通过”；否则文档明确记录风险与补测条件。
