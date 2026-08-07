# PTX→NVVM Pass Pipeline 总览

## 1. 范围与证据

本文只描述当前 `ptx/src/pass/mod.rs::to_llvm_module()` 实际执行的层次、顺序和层间契约。每个 Pass 的实现细节、风险与测试要求放在 [`PASS_DESIGN/`](PASS_DESIGN/README.md)，避免总览和单项文档重复维护。

当前输出是 NVPTX/NVVM 风格 LLVM IR，不是 PTX、cubin 或 SASS：

```text
PTX text
  → parser AST
  → 19 个前端变换 Pass
  → LLVM/NVVM emitter
  → LLVM NVPTX backend（当前默认构建未包含）
  → PTX/ptxas/SASS
```

本文的事实依据：

- 当前顺序：[`ptx/src/pass/mod.rs`](ptx/src/pass/mod.rs)
- 公共 statement/visitor：同文件中的 `Statement` 与 `visit_map`
- LLVM 发射：[`ptx/src/pass/llvm/emit.rs`](ptx/src/pass/llvm/emit.rs)
- 每项源码证据与反例：[`PASS_DESIGN/README.md`](PASS_DESIGN/README.md)

## 2. 当前层次

| 层 | Pass | 输入重点 | 层后不变量 |
| --- | --- | --- | --- |
| L1 符号与谓词 | 01–04 | 字符串名称、作用域、指令谓词、PTX 参数布局 | 唯一 ID；谓词进入显式控制流；特定 param 数组已规范化 |
| L2 操作数与 ABI | 05–09 | 函数符号、特殊寄存器、复合 operand、`.sat`、`.param` ABI | operand 扁平化；特殊语义成为 statement；普通函数边界使用 reg ABI |
| L3 浮点与 CFG | 10–14 | compliant rcp、rounding div、非规范 CFG、指令级 FP 模式 | 显式规范 CFG；不可达块删除；FP 模式变为 `SetMode`/kernel attributes |
| L4 存储与类型 | 15–17 | `.reg/.param` 变量、可选 32 位地址、隐式 PTX 类型规则 | load/store、地址宽度和 conversion 全部显式 |
| L5 最终 lowering | 18–19 | 尚未直接可发射的 opcode、函数体 global | helper/intrinsic call 明确；全局对象位于 module 层 |
| E 发射 | 非变换 Pass | 完整 resolver 与 final statements | 主 LLVM module、属性 module、metadata、FP 模式标志 |

层间依赖是单向的：前层消除一种隐式语义，后层不得重新猜测原始文本信息。

## 3. 精确执行顺序

| # | Pass | 是否改变 IR | 独立文档 |
| ---: | --- | --- | --- |
| 01 | `normalize_identifiers` | 是 | [01](PASS_DESIGN/01_normalize_identifiers.md) |
| 02 | `replace_known_functions` | 是 | [02](PASS_DESIGN/02_replace_known_functions.md) |
| 03 | `normalize_predicates` | 是 | [03](PASS_DESIGN/03_normalize_predicates.md) |
| 04 | `optimize_function_arguments` | 是 | [04](PASS_DESIGN/04_optimize_function_arguments.md) |
| 05 | `resolve_function_pointers` | 是 | [05](PASS_DESIGN/05_resolve_function_pointers.md) |
| 06 | `fix_special_registers` | 是 | [06](PASS_DESIGN/06_fix_special_registers.md) |
| 07 | `expand_operands` | 是 | [07](PASS_DESIGN/07_expand_operands.md) |
| 08 | `insert_post_saturation` | 是 | [08](PASS_DESIGN/08_insert_post_saturation.md) |
| 09 | `deparamize_functions` | 是 | [09](PASS_DESIGN/09_deparamize_functions.md) |
| 10 | `rcp_f64_into_div` | 是 | [10](PASS_DESIGN/10_rcp_f64_into_div.md) |
| 11 | `replace_instructions_with_functions_fp_required` | 是 | [11](PASS_DESIGN/11_replace_instructions_with_functions_fp_required.md) |
| 12 | `normalize_basic_blocks` | 是 | [12](PASS_DESIGN/12_normalize_basic_blocks.md) |
| 13 | `remove_unreachable_basic_blocks` | 是 | [13](PASS_DESIGN/13_remove_unreachable_basic_blocks.md) |
| 14 | `instruction_mode_to_global_mode` | 是 | [14](PASS_DESIGN/14_instruction_mode_to_global_mode.md) |
| 15 | `insert_explicit_load_store` | 是 | [15](PASS_DESIGN/15_insert_explicit_load_store.md) |
| 16 | `convert_32bit_to_64bit` | 条件执行 | [16](PASS_DESIGN/16_convert_32bit_to_64bit.md) |
| 17 | `insert_implicit_conversions` | 是 | [17](PASS_DESIGN/17_insert_implicit_conversions.md) |
| 18 | `replace_instructions_with_functions` | 是 | [18](PASS_DESIGN/18_replace_instructions_with_functions.md) |
| 19 | `hoist_globals` | 是 | [19](PASS_DESIGN/19_hoist_globals.md) |

之后依次执行：

1. `get_fp_mode`：只读扫描，不是变换 Pass。
2. `llvm::emit::run`：生成主 module。
3. `llvm::attributes::run`：生成独立属性 module。
4. 聚合 kernel metadata、可选 `ModuleMetadata32Bit` 与 `constrained_fp`。

## 4. IR 形态演进

```text
Directive<ParsedOperand<&str>>
  │ 01 名称绑定
  ▼
NormalizedDirective2
  │ 03 谓词显式化
  ▼
UnconditionalDirective
  │ 05–09 operand/ABI 展开
  ▼
ExpandedStatement
  │ 10–14 FP + CFG 规范化
  ▼
CFG-stable ExpandedStatement
  │ 15–17 存储、地址、类型显式化
  ▼
Typed/explicit ExpandedStatement
  │ 18–19 lowering 与 module 布局
  ▼
Emitter-ready directives
```

核心 statement 包括：`Instruction`、`Label`、`Conditional`、`Constant`、`Conversion`、`PtrAccess`、`RepackVector`、`Call`、`SetMode` 和 `RetValue`。`SpirvWord` 只是本内部 IR 的唯一 ID，并不表示最终目标是 SPIR-V。

## 5. 层间必须保持的顺序

| 前置 | 后置 | 原因 |
| --- | --- | --- |
| 01 | 全部后续 | resolver 的 ID/type/space 是共同基础 |
| 03 | 12 | 谓词先变成边，才能规范 CFG |
| 05/06 | 07 | 函数符号和特殊 operand 要在复合形态消失前识别 |
| 07 | 08–19 | 后续 visitor 假设 instruction operand 已是 ID |
| 08 | 18 | `.sat` 必须在原 opcode 消失前显式化 |
| 09 | 15 | 先决定函数 ABI，再统一变量存储 |
| 10/11 | 14 | 新 Div/helper 模式要求必须进入 FP 求解 |
| 12 | 13/14 | 两者依赖显式块和 terminator |
| 13 | 14 | 不可达 FP 要求不应进入求解 |
| 15 | 16/17 | 先确定真实存储空间，再做地址与类型转换 |
| 16 | 17 | 32 位 BitToPtr 规则依赖 hidden ABI 已建立 |
| 17 | 18 | 原 PTX operand 规则要在 opcode helper 化前完成 |
| 19 | emit | LLVM global 必须是 module directive |

## 6. 新现代指令族如何接入

先按语义分类，不按指令名称分类。

### 6.1 单条、立即完成的指令

例如一个有明确输入输出、可直接映射 NVVM intrinsic 的新 opcode：

1. parser/AST 保存所有 modifier、shape 和 operand role；
2. 更新 Pass 8、14 等穷尽分类；
3. 检查 Pass 7 和 17 的 operand/type/space；
4. 在 Pass 18 或 emitter 选择标准 intrinsic；
5. 添加 target gating 和 LLVM verifier/codegen 测试。

这类通常不需要新 Pass。

### 6.2 新地址空间、handle 或 descriptor

扩展 resolver 的值语义、Pass 7/15/16/17、LLVM address-space mapping 和 ABI。storage 与 pointee/handle 语义必须分开；例如 `.reg .b32` 承载 TMEM 地址时，变量 storage 仍是 Reg。

这类通常需要修改既有类型层，不一定需要新 Pass。

### 6.3 跨指令/跨 CFG 的异步协议

例如 `ld → wait → use`、commit group、mbarrier phase、resource ownership：普通 SSA/词法顺序不能完整表达。建议在 Pass 14 后、Pass 15 前插入窄职责 validator/materializer。tcgen05 的具体设计见 [`TCGEN05_ASYNC_PIPELINE_DESIGN.md`](TCGEN05_ASYNC_PIPELINE_DESIGN.md)，建议 Pass 契约见 [`PASS_DESIGN/PROPOSED_PASSES.md`](PASS_DESIGN/PROPOSED_PASSES.md)。

这类需要新 Pass，但新 Pass 不做机器调度。

### 6.4 最终 SASS 调度语义

scoreboard、wait mask、barrier index 和 control bits 属于 LLVM NVPTX backend/ptxas。前端只保留 effect、convergence 和显式协议依赖，不增加模拟 SASS scheduler 的 Pass。

## 7. 当前对抗式审查结论

以下反例已由源码确认，尚不能用“pipeline 已闭合”掩盖：

| 问题 | 影响 | 处理方向 |
| --- | --- | --- |
| Pass 01 对 function `shared_mem` 使用 `assert!` | 非结构化 panic | 改为诊断并补负例 |
| Pass 05 边扫描边收集函数 ID | 后置声明函数地址识别失败 | 两遍收集/改写 |
| Pass 11 匹配所有 rounding float div，非 F64 均走 f32 helper | 文档与类型边界错误 | 限定 f32/f64或扩展低精度 helper |
| Pass 12 消费首 label | branch-to-entry 可能失去目标 | 明确入口约定并补回边测试 |
| Pass 13 遇 `FunctionPointer` 返回 TODO | 间接调用未打通 | 完整 CFG/call target 设计 |
| Pass 14 是 AMDGPU 全局模式模型 | NVPTX 语义未证明 | NVPTX 对照测试或目标化裁剪 |
| Pass 17 对 cluster/ParamFunc 可 `todo!()` | 合法输入可能 panic | 结构化 reject/实现 |
| Pass 18 只按 helper 名称去重声明 | 同名异签名可能错误复用 | key 加签名并校验 |
| Pass 19 不 hoist CTA/cluster shared | 新空间可能残留函数体 | 先定义对象模型再扩展 |

逐项证据和测试门槛见各 Pass 文档。当前审查结论是“结构已厘清，但多项风险仍待代码和测试关闭”，不是“19 个 Pass 均已验证正确”。

## 8. 验证方式

每次修改一个 Pass，至少执行三层检查：

1. Pass fixture：直接验证该 Pass 的输入/输出不变量及负例诊断。
2. 相邻层组合：验证前一 Pass 输出能被本 Pass 消费，本 Pass 输出满足下一 Pass。
3. 端到端：parser → 19 Pass → LLVM verifier → `opt -O3` → NVPTX `llc`；并发/异步语义再进入 ptxas 与硬件测试。

当前 `ptx/src/pass/test` 的专属 fixture 主要集中在 Pass 07、12、14、17，不能覆盖其余 Pass 的文档主张。新增现代指令前应优先补齐每个独立文档列出的最低测试。
