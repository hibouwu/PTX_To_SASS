# tcgen05 异步语义接入现有 PTX→NVVM Pipeline 的设计

## 1. 文档目的

本文回答两个实现问题：

1. 为当前 ZLUDA PTX→NVVM pipeline 增加 `tcgen05` 时，是否需要修改全部 19 个变换 pass。
2. `tcgen05.ld/st`、`tcgen05.wait::ld/st`、`tcgen05.commit` 和 `tcgen05.fence` 带有异步完成或编译器排序语义，前端是否需要新增专门的异步 pass。

结论是：**不需要逐个重写 19 个 pass，也不应在第一版增加一个负责机器调度的大型异步 pass；但需要审计所有通用 visitor，并重点修改 target 模型、操作数类型系统、`insert_explicit_load_store`、`insert_implicit_conversions` 和 LLVM emitter。支持复杂 CFG 后，建议在 CFG 规范化之后增加一个窄职责的 `validate_and_annotate_tcgen05_async` pass。**

这里的“异步 pass”只分析 PTX 语义状态和验证合法性，不计算 SASS scoreboard，不安排机器指令，也不编码 SASS 控制位。当前推荐后端仍是：

```text
PTX AST
  → ZLUDA 规范化 pass
  → llvm.nvvm.tcgen05.* intrinsic
  → LLVM NVPTX backend
  → tcgen05 PTX
  → ptxas
  → SASS opcode 与控制位
```

## 2. 先区分四种依赖表示

讨论 `tcgen05.wait` 和 `tcgen05.fence` 时，最容易混淆的是“LLVM IR 有没有 DAG”和“最终有没有同名 SASS 指令”。它们发生在不同层次。

### 2.1 ZLUDA 内部 IR：线性 statement 与 CFG

当前 parser AST 使用线性 `Statement::Instruction` 序列。谓词规范化后，控制流变为标签、条件分支和基本块。这个表示足以保留 PTX 源程序中：

```ptx
tcgen05.ld ...;
tcgen05.wait::ld.sync.aligned;
use_loaded_registers;
```

的词法顺序，但它没有显式表示“前面的 `ld` 结果在 wait 之后才 ready”。因此，通用 pass 可以搬运节点，却不能凭普通 SSA def-use 自动理解完成协议。

### 2.2 LLVM IR：SSA、CFG 和 effectful intrinsic

LLVM IR 没有一个覆盖全部语义的单一显式 DAG。它同时使用：

- SSA def-use graph 表示值依赖。
- CFG 表示控制依赖。
- intrinsic/function attributes 和 memory effects 表示不可删除、不可越过或不可任意合并的副作用。
- `convergent` 表示调用不能随意跨越会改变参与线程集合的控制流变换。

vendored LLVM 已定义：

| PTX 操作 | NVVM intrinsic | LLVM 语义属性 |
| --- | --- | --- |
| `tcgen05.wait::ld` | `llvm.nvvm.tcgen05.wait.ld` | `IntrConvergent`、`IntrInaccessibleMemOnly` |
| `tcgen05.wait::st` | `llvm.nvvm.tcgen05.wait.st` | `IntrConvergent`、`IntrInaccessibleMemOnly` |
| `tcgen05.fence::before_thread_sync` | `llvm.nvvm.tcgen05.fence.before.thread.sync` | `IntrNoMem`、`IntrHasSideEffects` |
| `tcgen05.fence::after_thread_sync` | `llvm.nvvm.tcgen05.fence.after.thread.sync` | `IntrNoMem`、`IntrHasSideEffects` |

这些 intrinsic 即使没有普通输入输出值，也不是 NOP。LLVM 必须保留调用，并在 NVPTX lowering 中生成对应 PTX 操作。

### 2.3 LLVM 后端：SelectionDAG/GlobalISel 与 ScheduleDAG

进入 LLVM 后端后，intrinsic 会被选择成 NVPTX 机器指令。此时 LLVM 使用 SelectionDAG 或 GlobalISel 表示选择依赖，并由 MachineScheduler 的调度图约束机器指令顺序。ZLUDA 不需要复制这一层。

### 2.4 ptxas：SASS 指令和控制位

本仓库 `PTX_SASS_mapping/01_tcgen05` 的实验说明，部分 wait/fence 最终可能没有独立 SASS opcode，作用体现在前后指令的 scoreboard、wait mask、依赖屏障控制字段或必要的 NOP 分隔上。

因此必须坚持以下边界：

```text
ZLUDA：保留并发射语义节点
LLVM：保留 intrinsic 副作用并生成合法 tcgen05 PTX
ptxas：将 PTX 完成/排序语义编码为最终 SASS 调度约束
```

不能因为 SASS 中没有同名 opcode，就在 ZLUDA emitter 中把 wait/fence 返回为 `Ok(())`。

## 3. 为什么不需要修改每一个 pass

`ptx_parser_macros::generate_instruction_type!` 会依据每个 instruction variant 声明的参数信息生成 visitor。大量 pass 只调用 `ast::visit_map`，并不按 opcode 解释语义。只要新增 tcgen05 AST 时准确声明：

- 哪个参数是 destination。
- 哪个参数是 source。
- 参数对应的 PTX/LLVM 类型。
- 参数属于 `.reg`、`.shared`、TMEM 或其他状态空间。
- 哪些 modifier 是 enum，哪些值必须是立即数。

这些 pass 通常可以自动遍历新指令。Rust 穷尽匹配可能要求补一个透传分支，但这属于编译适配，不代表该 pass 需要实现 tcgen05 算法。

另一方面，“visitor 可以遍历”不等于“语义天然正确”。凡是会插入前后指令、改变地址空间、改变 CFG 或将指令替换为 helper 的 pass，都必须进行定向审计。

## 4. 现有 19 个变换 pass 的逐项影响

下表把改动分成四级：

- **必须改**：没有修改就无法正确表示或发射 tcgen05。
- **可能改**：通用 visitor 能覆盖大部分行为，但特定形态需要专门处理。
- **无需专用逻辑，必须测试**：预计源码不需要 tcgen05 match arm，但必须用测试证明透传不破坏语义。
- **无关**：职责与 tcgen05 基本不相交。

| 序号 | Pass | 影响等级 | tcgen05 接入要求 |
| ---: | --- | --- | --- |
| 1 | `normalize_identifiers` | 无需专用逻辑，必须测试 | visitor 会把寄存器、地址和标签解析成 ID。需要覆盖大寄存器 tuple、TMEM 地址寄存器和 descriptor 参数。 |
| 2 | `replace_known_functions` | 无关 | 处理已知外部函数重命名，不应接触 tcgen05 instruction。 |
| 3 | `normalize_predicates` | 无需专用逻辑，必须测试 | 会把谓词化 tcgen05 指令放入显式 CFG。需要验证 PTX ISA 是否允许对应指令被谓词化；不允许的组合应在 parser/validator 拒绝。 |
| 4 | `optimize_function_arguments` | 无关 | 只处理特定 `.param b8[]` 参数布局。 |
| 5 | `resolve_function_pointers` | 无关 | 只识别函数符号地址。 |
| 6 | `fix_special_registers` | 无需专用逻辑，必须测试 | 通用 visitor 会处理出现在参数表达式中的特殊寄存器；tcgen05 本身不需要新特殊寄存器时无需专用代码。 |
| 7 | `expand_operands` | 可能改 | 必须支持 tcgen05 的寄存器 tuple、TMEM 地址、shared descriptor 和立即数 flag。尤其要确认大于传统 v4 的寄存器包不会被错误当成普通 LLVM vector 语法。 |
| 8 | `insert_post_saturation` | 无关 | tcgen05 不使用普通算术 `.sat` 后处理。 |
| 9 | `deparamize_functions` | 无需专用逻辑，必须测试 | 普通函数边界中的 descriptor/TMEM 地址必须保持正确位宽和状态空间；kernel 不走普通函数 ABI 改写。 |
| 10 | `rcp_f64_into_div` | 无关 | 只处理 reciprocal。 |
| 11 | `replace_instructions_with_functions_fp_required` | 无关 | 只处理特殊浮点 helper 与模式要求。 |
| 12 | `normalize_basic_blocks` | 无需专用逻辑，必须测试 | 不应跨 instruction 重排，但它为后续异步 CFG 分析提供稳定基本块。 |
| 13 | `remove_unreachable_basic_blocks` | 无需专用逻辑，必须测试 | 可删除不可达 tcgen05 操作；可达路径中的异步状态合并必须留给后续 validator。 |
| 14 | `instruction_mode_to_global_mode` | 无需专用逻辑，必须测试 | 只分析浮点模式，但可能插入块或重定向边。必须验证插入的 `SetMode` 不破坏 tcgen05 邻接要求。 |
| 15 | `insert_explicit_load_store` | **必须改** | 当前会在每个 `.reg` destination 后立即插入 local store。`tcgen05.ld` 的结果在 `wait::ld` 前不能被普通指令消费，不能按普通 destination 立即写回。 |
| 16 | `convert_32bit_to_64bit` | 可能改 | 第一版建议对含 tcgen05 的 `.address_size 32` 模块直接报不支持。TMEM 地址本身为 32 位不代表整个 PTX module 使用 32 位地址模型。 |
| 17 | `insert_implicit_conversions` | **必须改** | 需要表示 TMEM `addrspace(6)`，并区分“32 位 TMEM 地址”与普通 32 位整数/通用 pointer。禁止错误转换成 generic/global pointer。 |
| 18 | `replace_instructions_with_functions` | 可能改 | tcgen05 应保持专用 AST 到 emitter，或转换成真正的 NVVM intrinsic call；不能进入普通 ZLUDA helper。必须确保通配分支不会提前吞掉它。 |
| 19 | `hoist_globals` | 无需专用逻辑，必须测试 | tcgen05 不改变 global 提升规则。若以后引入特殊 shared descriptor 声明，需确认仍保持 module 合法布局。 |

除 19 个变换 pass 外，还有四个必须修改的非 pass 边界：

| 边界 | 必需工作 |
| --- | --- |
| parser/AST | 增加 tcgen05 子族、shape、CTA group、pack/unpack、collector、kind 等强类型表示。 |
| module target | 保留 PTX version 和 `sm_110a` 的 `a` 后缀；不能退化成 `sm_110`。 |
| LLVM address-space mapping | 增加 TMEM `addrspace(6)`，并限制可对其执行的转换和操作。 |
| LLVM emitter | 使用标准 `llvm.nvvm.tcgen05.*` intrinsic；wait/fence 绝不能作为 NOP。 |

## 5. `insert_explicit_load_store` 是首要风险点

### 5.1 当前 pass 的普通寄存器模型

当前 pass 将函数体内的 PTX `.reg` 变量转为 `.local` slot。每次读取前插入 load，每次写入后插入 store。普通指令近似变换为：

```text
PTX: add.u32 %r0, %r1, %r2

内部 IR:
  %v1 = load local_slot(%r1)
  %v2 = load local_slot(%r2)
  %result = add %v1, %v2
  store %result, local_slot(%r0)
```

这能避免前端自行构造完整 SSA，后续 LLVM 优化还可以将 allocas/load/store 提升回 SSA。

### 5.2 tcgen05.ld 的结果不是普通“立即 ready”结果

PTX 典型序列为：

```ptx
tcgen05.ld.sync.aligned.16x64b.x1.b32 {%r0}, [%taddr];
tcgen05.wait::ld.sync.aligned;
mov.b32 %sink, %r0;
```

如果沿用普通 destination 的 post-store，内部顺序会变成：

```text
%pending = call @llvm.nvvm.tcgen05.ld...()
store %pending, %r0.slot
call @llvm.nvvm.tcgen05.wait.ld()
```

这里的 store 已经是对 pending result 的使用。即使最终优化可能把 slot 提升成 SSA，也不能依赖优化器“碰巧”把 store 或真实 consumer 移到 wait 后面。异步完成边界必须在前端表示中保持明确。

### 5.3 推荐的第一版处理

第一版应让 `insert_explicit_load_store` 对 `Tcgen05Ld` 使用专用路径：

1. `Tcgen05Ld` destination 映射到内部 pending SSA ID，不立即生成 post-store。
2. 记录 `原 PTX 寄存器 → pending SSA ID / local slot / 所属异步 epoch`。
3. 遇到 `Tcgen05Wait::Ld` 时先保留 wait 节点，再把当前 epoch 的 pending 值写回对应 local slot。
4. wait 之后的普通读取继续使用现有 pre-load 逻辑。
5. 基本块结束时若仍有 pending ld，第一版直接报错；不要把值静默带过未知 CFG 边。

目标顺序是：

```text
%pending = call @llvm.nvvm.tcgen05.ld...()
call @llvm.nvvm.tcgen05.wait.ld()
store %pending, %r0.slot
%ready = load %r0.slot
```

这是一种保守但容易验证的实现。以后可以把 pending/ready 状态提升为独立分析 pass，再让 Pass 15 只消费标注。

### 5.4 tcgen05.st 的方向不同

`tcgen05.st` 在发起操作时读取普通寄存器作为输入，因此这些 source load 必须发生在 `tcgen05.st` 之前。`wait::st` 约束的是先前 store 操作的完成，不产生一个待写回的普通寄存器值。

因此：

- `tcgen05.st` 的 source 可以继续使用 Pass 15 的 pre-load。
- `tcgen05.wait::st` 必须作为 effectful intrinsic 保留。
- 不能把 `wait::st` 当作“没有返回值，所以没用”的节点删除。

## 6. 是否应该新增异步 pass

答案分为三个支持阶段。

### 6.1 阶段 A：只打通 wait/fence 和无 CFG 的最小闭环

不需要新增 pass。实现：

- parser/AST 增加 `Tcgen05Wait` 和 `Tcgen05Fence`。
- 通用 pass 原样透传。
- emitter 发射标准 NVVM intrinsic。
- 限制测试 kernel 为单基本块、无谓词、无循环。

这时还没有 pending 普通寄存器结果，适合验证 target、intrinsic declaration、LLVM verifier 和 NVPTX codegen。

### 6.2 阶段 B：支持直线 tcgen05.ld/st

仍可暂时不新增独立 pass，但必须给 `insert_explicit_load_store` 增加局部 pending-result 状态。支持边界应明确限制为：

- 单基本块。
- `tcgen05.ld` 与对应 `wait::ld` 位于同一块。
- pending 结果在 wait 前没有任何普通 use。
- 块结束时 pending 集合为空。
- 不允许把 pending 状态跨 call、branch、return 或循环回边传播。

这种实现适合快速打通端到端闭环，但不适合作为完整 tcgen05 控制流语义的最终结构。

### 6.3 阶段 C：支持分支、循环和多批异步操作

此时建议新增：

```text
validate_and_annotate_tcgen05_async
```

推荐位置：

```text
normalize_basic_blocks
remove_unreachable_basic_blocks
instruction_mode_to_global_mode
validate_and_annotate_tcgen05_async   ← 新增
insert_explicit_load_store
```

放在这里的原因是：

1. CFG 已经规范化且不可达块已删除，可以做基本块数据流分析。
2. 浮点模式 pass 可能增加 prologue block 和重定向边，因此异步分析应看到它的最终 CFG。
3. PTX `.reg` 尚未被 Pass 15 转成 local slot，分析仍能直接识别源 PTX 寄存器的 pending/ready 状态。

## 7. 新异步分析 pass 的职责边界

### 7.1 应该负责的内容

建议状态至少包含：

```rust
struct Tcgen05AsyncState {
    pending_ld: Map<RegisterId, PendingLd>,
    pending_st: bool,
    allocation: TmemAllocationState,
    epoch: u32,
}

struct PendingLd {
    producer: InstructionId,
    epoch: u32,
}
```

pass 应完成：

- `tcgen05.ld` 将 destination 加入 `pending_ld`。
- 普通指令读取 pending register 时报告错误。
- `wait::ld` 将当前约束范围内的 pending ld 标记为 ready。
- `tcgen05.st` 标记存在尚未完成的 store 操作。
- `wait::st` 关闭对应 pending store 状态。
- 检查 alloc、dealloc、relinquish permit 的明显生命周期错误。
- 检查要求相同 CTA group 的操作组合。
- 检查 return/dealloc 前是否仍有不允许遗留的 pending 操作。
- 给 Pass 15 或 emitter 附加 pending epoch/ready point 标注。

### 7.2 CFG 数据流

对每个基本块维护 `IN[B]` 和 `OUT[B]`：

$$
IN[B] = \operatorname{merge}_{P \in pred(B)} OUT[P]
$$

然后按块内指令顺序执行 transfer function：

$$
OUT[B] = F_B(IN[B])
$$

第一版 merge 应保守处理。若同一寄存器在不同前驱具有不同状态，例如一条路径 pending、另一条路径 ready，不要自动猜测；应报“tcgen05 async state differs at CFG merge”。等直线和结构化分支验证稳定后，再研究是否能用显式 epoch phi 或路径敏感分析支持更多情况。

循环需要不动点迭代。若循环回边携带未完成异步状态，第一版同样可以拒绝，避免错误接受无法证明的协议。

### 7.3 不应该负责的内容

这个 pass 不应：

- 调整 tcgen05 指令顺序以追求性能。
- 计算 SASS barrier index、wait mask 或 reuse flag。
- 将 wait/fence 删除成 NOP。
- 根据映射实验手工展开 `tcgen05.alloc` 的 SASS 协议。
- 模拟 LLVM SelectionDAG 或 ptxas 调度器。

这些职责属于 LLVM NVPTX backend 或 `ptxas`。只有未来绕过 PTX/ptxas、直接生成 SASS 时，才需要在序列 IR 和机器调度阶段实现零编码 pseudo-instruction、调度边和控制位分配。

## 8. target 和合法性验证应单独处理

异步状态分析不应同时承担所有 target 检查。建议另设一个早期窄职责 validator，或在 parser module validation 中完成：

```text
validate_target_features
```

至少验证：

- 输入 PTX version 满足对应 tcgen05 形式的最低要求。
- target 完整保留 `sm_110a`，不是只保存数字 110。
- 当前 LLVM subtarget 的 `hasTcgen05Instructions` 条件成立。
- shape、CTA group、source format、pack/unpack、kind、collector usage 组合合法。
- 必须为立即数的 intrinsic flag 在 AST 中确实是编译期常量。
- 第一阶段仅接受 `.address_size 64` module。

当前 `ptx_parser::Module` 已保存 `ptx_version` 和数字 `sm_version`，但没有保存 target suffix。接入 tcgen05 前必须扩展完整 target descriptor，否则 `.target sm_110a` 会退化为 `sm_110`，后端 gating 将失败。

## 9. TMEM 类型与地址空间不能只当作 u32

LLVM NVPTX 使用 `addrspace(6)` 表示 TMEM pointer。虽然 PTX 文本中的 TMEM 地址经常由 32 位寄存器承载，但在内部类型系统中不能把它永久当作无语义的普通 `u32`，否则 Pass 17 可能：

- 把它转换成 local/shared pointer。
- 把它错误扩展成 generic 64 位地址。
- 允许普通 LLVM load/store 解引用 TMEM。
- 在同宽 bitcast 中丢失 TMEM 语义。

建议增加 `StateSpace::Tmem`，映射到 LLVM `addrspace(6)`，并只允许：

- 从合法的 32 位 TMEM 地址表示构造 TMEM pointer。
- 传给声明接受 `llvm_tmem_ptr_ty` 的 tcgen05 intrinsic。
- 执行 PTX ISA 明确允许的 TMEM 地址算术。

普通 `ld`、`st` 和 generic address-space cast 不应自动接受 `StateSpace::Tmem`。

## 10. emitter 的正确实现方式

wait/fence 的 emitter 分支应直接发射：

```text
Tcgen05Wait::Ld
  → call void @llvm.nvvm.tcgen05.wait.ld()

Tcgen05Wait::St
  → call void @llvm.nvvm.tcgen05.wait.st()

Tcgen05Fence::BeforeThreadSync
  → call void @llvm.nvvm.tcgen05.fence.before.thread.sync()

Tcgen05Fence::AfterThreadSync
  → call void @llvm.nvvm.tcgen05.fence.after.thread.sync()
```

应通过 `LLVMLookupIntrinsicID` 和 `LLVMGetIntrinsicDeclaration` 获取 LLVM 注册的 intrinsic declaration，而不是只用 `LLVMAddFunction` 创建同名普通函数。这样可以让声明获得 LLVM intrinsic 注册表定义的签名和属性，并由 verifier 检查错误参数。

对于 tcgen05 ld/st/mma 等带 overloaded 类型或大型 vector/tuple 的 intrinsic，应以 vendored LLVM 的 `IntrinsicsNVVM.td` 签名为唯一 ABI 依据。`PTX_SASS_mapping` 用来验证最终 PTX/SASS 行为，不用来反推 LLVM 函数签名。

## 11. 推荐的分阶段实施顺序

### P0：target 与构建基础

1. 扩展 module target descriptor，保留 PTX version、SM 数字、`a/f` 后缀和 address size。
2. emitter 生成 `target-cpu="sm_110a"` 和对应 PTX feature。
3. LLVM 构建加入 NVPTX target。
4. 增加 TMEM `addrspace(6)` 常量和状态空间表示。

验收：一个不含 tcgen05 指令的最小 kernel 能以 `sm_110a + PTX 9.0` 通过 LLVM verifier 和 NVPTX codegen。

### P1：零操作数 effectful 指令

实现 wait、fence、relinquish permit。

验收：

- O0/O3 LLVM IR 中 intrinsic 均未消失。
- `llc` 输出对应 tcgen05 PTX。
- `ptxas` 接受输出。
- fence/wait 在 SASS 中即使没有独立 opcode，其控制位差分仍与 mapping 探针一致。

### P2：资源和同步操作

实现 alloc、dealloc、commit、shift，并完成 CTA group 与 shared/TMEM pointer 类型检查。

验收：非法 target、列数、CTA group 和 pointer space 在前端或 LLVM verifier 阶段稳定报错。

### P3：直线 ld/st

修改 Pass 15，支持单基本块 pending ld 延迟写回；Pass 17 支持 TMEM pointer；实现 vector tuple lowering。

验收：

```text
ld → wait.ld → use
st → wait.st → dealloc/return
```

在 O0/O3 下保持顺序，并通过 PTX、SASS 控制位和硬件数值测试。

### P4：CFG 异步状态分析

新增 `validate_and_annotate_tcgen05_async`，支持结构化分支，并保守拒绝无法合并的 pending 状态和未证明安全的循环。

验收：覆盖同路径 wait、分支双侧 wait、单侧漏 wait、merge 状态冲突、循环回边 pending 和 return 前 pending 六类用例。

### P5：mma 和高级协议

最后实现基础 mma，再逐步加入 sparse、block scale、WS、disable-output-lane 和 collector 组合。此阶段复用同一 target validator 和异步状态框架，不新建第二套协议分析。

## 12. 测试矩阵

### 12.1 每个通用 pass 的最低测试

不需要为每个 pass 添加 tcgen05 专用代码，但应有 pass dump 或断言证明：

| 检查点 | 不变量 |
| --- | --- |
| `normalize_identifiers` 后 | tcgen05 所有寄存器和地址均变为唯一 ID。 |
| `normalize_predicates` 后 | 指令不再携带 `PredAt`；不允许谓词化的 tcgen05 形式已被拒绝。 |
| `expand_operands` 后 | TMEM 地址、立即数和 tuple 不再含未展开的文本操作数。 |
| `normalize_basic_blocks` 后 | wait/fence 仍处于原控制路径，未被复制到不同参与线程集合。 |
| `insert_explicit_load_store` 后 | pending ld 结果第一次普通 use 严格位于 `wait::ld` 之后。 |
| `insert_implicit_conversions` 后 | TMEM 参数为 `addrspace(6)`，没有错误 generic cast。 |
| `replace_instructions_with_functions` 后 | tcgen05 未进入 `__zluda_ptx_impl_*` 普通 helper。 |
| LLVM emit 后 | 标准 NVVM intrinsic 声明和属性存在，module verifier 通过。 |

### 12.2 异步负例

至少覆盖：

```ptx
// wait 前消费 ld 结果
tcgen05.ld ... {%r0}, ...;
mov.b32 %r1, %r0;
tcgen05.wait::ld.sync.aligned;

// 一条分支遗漏 wait
@%p bra HAS_WAIT;
bra MERGE;
HAS_WAIT:
tcgen05.wait::ld.sync.aligned;
MERGE:
mov.b32 %r1, %r0;

// return 前仍有未完成操作
tcgen05.st ...;
ret;
```

第一版不必自动修复这些程序，应提供稳定、带指令位置的诊断。

### 12.3 后端与硬件验证

测试必须分层，不能只看 LLVM IR：

1. parser/AST 正反例。
2. ZLUDA pass 不变量。
3. LLVM verifier。
4. O0/O3 下 intrinsic 保留与顺序。
5. `llc -march=nvptx64 -mcpu=sm_110a -mattr=+ptx90` 输出检查。
6. `ptxas` 静态接受。
7. SASS opcode 和控制字差分。
8. SM110a 硬件运行时数值、同步和压力测试。

## 13. 与 PTX_SASS_mapping 的关系

`PTX_SASS_mapping/01_tcgen05` 对本设计有三类直接帮助：

- 提供 shape、modifier、CTA group 和合法组合的 parser/validator 测试语料。
- 验证 LLVM→PTX→ptxas 后是否仍产生预期 SASS family。
- 对 wait/fence 做控制字差分，确认零独立 opcode 时语义仍被编码。

它不能替代：

- LLVM `IntrinsicsNVVM.td` 定义的 intrinsic ABI。
- LLVM NVPTX CodeGen tests 定义的 lowering 预期。
- 前端 CFG 上的 pending/ready 合法性分析。
- 硬件运行时正确性测试。

特别是 mapping 中观察到 `tcgen05.alloc` 展开成多条 SASS，或 wait/fence 没有独立 SASS，都不意味着 ZLUDA 应复制这些展开。ZLUDA 仍应发射一条语义准确的 NVVM intrinsic。

## 14. 最终决策

当前阶段的工程决策如下：

1. **不修改全部 19 个 pass。** 利用 AST 自动 visitor 让大部分 pass 透传，只对会改变语义边界的 pass 做定向修改。
2. **第一版不增加机器调度型异步 pass。** wait/fence 作为 effectful intrinsic 交给 LLVM 和 ptxas。
3. **直线 tcgen05.ld 必须修改 Pass 15。** pending result 不能在 wait 前被自动 post-store 消费。
4. **完整 CFG 支持时增加窄职责分析 pass。** `validate_and_annotate_tcgen05_async` 只验证 pending/ready、资源生命周期和 CFG merge，不编码 SASS。
5. **target validation 与异步分析分离。** `sm_110a`、PTX 9.0、立即数 flag 和 modifier 合法性属于 target/grammar validator。
6. **NVVM intrinsic 是当前 lowering 的语义边界。** LLVM 负责生成 tcgen05 PTX，ptxas 负责最终 SASS 调度控制位。

按此设计，最小可验证改动集中在 parser/AST、完整 target、TMEM 类型、Pass 15、Pass 17 和 emitter；其余 pass 主要承担回归测试，而不是逐个加入 tcgen05 专用分支。
