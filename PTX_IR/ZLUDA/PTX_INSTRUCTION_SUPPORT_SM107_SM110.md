# PTX 指令支持程度审计：SM107 与 SM110

## 1. 结论摘要

本文审计当前 `ZLUDA/ptx` 的 PTX 到 NVVM LLVM IR 转换能力，目标是回答两个不同的问题：当前代码能识别和 lower 哪些 PTX 指令；这些输出是否适合继续面向 `sm_107` 或 `sm_110` 做 NVPTX codegen。结论以当前仓库源码为准，不把“parser 能解析”“emitter 有 match arm”“生成了 LLVM IR”和“最终可在目标 GPU 正确执行”混为一件事。Pass 内部结构不在本文重复，统一链接到 [`PASS_DESIGN/`](PASS_DESIGN/README.md)。

当前 parser 的内部 `Instruction` 枚举共有 81 个变体。最终 emitter 对这 81 个变体具有穷尽分发，其中 59 个进入直接发射函数，17 个要求先由 pass 替换为 NVVM intrinsic 或 ZLUDA helper call，5 个被直接当成 NOP。这个数字只说明内部枚举的分发闭合，不能理解为支持 PTX ISA 的 81 条完整指令，更不能理解为 81 个 opcode 的所有类型、修饰符、地址空间和同步语义均已正确实现。

从目标架构看，当前前端可以把数字 `.target sm_NNN` 写成 LLVM 函数的 `target-cpu="sm_NNN"`。vendored LLVM 的 NVPTX processor 表明确包含 `sm_110`、`sm_110a` 和 `sm_110f`，但不包含 `sm_107`。因此：

- `sm_110`：可以生成带该 `target-cpu` 的 NVVM LLVM IR，vendored NVPTX 源码也认识该处理器；但 SM110 相关的新 PTX 指令族远未覆盖，且本项目默认构建没有编入 NVPTX backend。特别是 vendored LLVM 的 tcgen05 predicate 只把 `sm_110a + PTX 9.0` 列为 SM110-family 合法组合，不能把 `sm_110` 与 `sm_110a` 混写。
- `sm_107`：parser 会接受数字 107，前端也会生成 `target-cpu="sm_107"`，但 vendored NVPTX backend 不认识该处理器。当前状态不能声称具备 SM107 codegen 支持。
- `sm_110a` / `sm_110f`：parser 语法能读出单字符后缀，但构造 `ptx_parser::Module` 时会丢弃后缀，只保存 `110`。当前输出会退化成 `target-cpu="sm_110"`，无法保留 architecture-specific 或 family-specific 目标语义。

如果目标是常规标量、简单控制流、普通 global/shared/local load/store、基础原子、传统 warp 操作和一部分 `mma/ldmatrix`，当前实现已经具备可继续验证的基础。若输入依赖 Hopper/Blackwell 时代的 TMA、`mbarrier`、cluster shared memory、`wgmma`、`tcgen05`、新 fence/proxy 或 tensormap 语义，当前实现不能满足 SM110 目标。

## 2. 支持等级定义

本文使用以下等级，避免笼统地写“支持”：

| 等级 | 含义 |
| --- | --- |
| A：直接支持 | parser 有对应表示，pass 可完成合法化，emitter 直接生成 LLVM IR 或明确的 LLVM/NVVM intrinsic；未发现该基础形态的显式 TODO |
| B：helper 支持 | 指令会被替换为 `llvm.nvvm.*` 或 `__zluda_ptx_impl_*` 调用；正确运行依赖 intrinsic 声明、helper bitcode、属性 module 和后续链接 |
| C：部分支持 | opcode 有路径，但仅支持部分类型、shape、modifier、scope 或返回形式，或者语义被降级 |
| D：仅解析/NOP | parser 可接受或 enum 有变体，但 emitter 丢弃操作，不能保留完整 PTX 语义 |
| E：不支持 | parser 没有该指令族，或 lowering/地址空间映射明确返回 `Todo`、`Unreachable`、`todo!()` |
| U：未验证 | 源码存在路径，但缺少该组合的端到端 PTX→NVVM IR 测试，不能仅凭静态分支断言运行正确 |

一个指令可能同时属于 B 和 C。例如 `ldmatrix` 通过 helper 实现，因此是 B；但只接受有限 shape/number/type，因此整体评级是 C。A/B 也不代表所有 modifier 均支持，表格中的限制列优先于等级列。

## 3. 统计口径

内部指令全集定义在 [`ptx_parser/src/ast.rs`](ptx_parser/src/ast.rs) 的 `generate_instruction_type!` 宏调用中。最终分发位于 [`ptx/src/pass/llvm/emit.rs`](ptx/src/pass/llvm/emit.rs) 的 `emit_instruction()`：

| emitter 分发结果 | 变体数 | 应如何理解 |
| --- | ---: | --- |
| 调用具体 `emit_*` | 59 | 有直接发射入口，但某些 variant 可能更早被 helper pass 截获，具体 modifier 仍可能受限 |
| 必须由前置 pass 替换为 call | 17 | 若原指令抵达 emitter，会返回内部错误；支持程度取决于 [`replace_instructions_with_functions.rs`](ptx/src/pass/replace_instructions_with_functions.rs) 是否覆盖该具体组合 |
| 直接 NOP | 5 | 转换可继续，但操作本身被删除，不能算语义支持 |
| 合计 | 81 | 只覆盖当前 parser 内部枚举，不是 PTX ISA 9.x 的完整指令集 |

parser 中存在大量针对同一 enum 变体的语法规则，例如 `ld`、`st`、`atom` 和 `cvt` 的不同类型与 modifier。语法规则数量不能作为指令支持率，因为多个规则会汇聚到同一个 enum 变体，而且部分规则包含尚未实现的修饰符分支。

仓库当前也缺少覆盖全部 opcode 的端到端测试集。`ptx/src/pass/test` 主要验证 `expand_operands`、`insert_implicit_conversions`、`normalize_basic_blocks` 和 `instruction_mode_to_global_mode` 等 pass 不变量；[`ptx/examples/dump_ir.rs`](ptx/examples/dump_ir.rs) 可以运行完整转换，但不是系统性的指令语义测试。因此本文对多数指令给出的是“静态代码路径支持度”，不是硬件执行验证结果。

## 4. 当前 81 个内部指令变体的总体矩阵

### 4.1 基础数据移动、算术和逻辑

| 指令或指令族 | 路径 | 等级 | 已知限制与风险 |
| --- | --- | --- | --- |
| 普通 `mov` | 直接 emit | A/U | 普通标量、向量或地址值 move 以 parser 已接受的类型为边界 |
| `mov.u64 dst, function_symbol` | 先转 `Statement::FunctionPointer` | E | statement emitter 对 `FunctionPointer` 仍是 `todo!()`，当前函数地址取得路径未打通 |
| `ld`, `st` | 直接 emit | A/C/U | generic/global/shared/local/const/param-entry 主路径存在；`ParamFunc`、`SharedCta`、`SharedCluster` 无地址空间映射；部分 cache/prefetch modifier 未完整建模 |
| `add`, `sub`, `mul`, `mad`, `fma`, `div` | 直接 emit，部分 variant 转 helper | A/B/C/U | 整数与常见浮点主路径存在；舍入、FTZ、饱和和部分除法会进入 constrained FP 或 helper；组合覆盖不等于 PTX ISA 全覆盖 |
| `add.cc/addc`, `sub.cc/subc`, `mad.cc/madc` 对应内部 extended 变体 | 直接 emit | A/U | 内部变体为 `AddExtended`、`SubExtended`、`MadExtended`；需用真实 carry 链用例继续验证 |
| `abs`, `neg` | 直接 emit | A/C/U | 受 scalar type 与 FTZ 规则约束 |
| `min`, `max` | 直接 emit | A/C/U | parser 中 `.relu` 等现代组合并未完整实现 |
| `rem` | 直接 emit | A/U | 以 parser 已接受的整数类型为边界 |
| `and`, `or`, `xor`, `not` | 直接 emit | A/U | 基础标量位逻辑路径存在 |
| `shl`, `shr`, `shf` | 直接 emit | A/C/U | 基础 shift/funnel shift 存在；不要与 `vshr` 的 wrap 限制混淆 |
| `clz`, `brev`, `popc`, `bfind` | 直接 emit | A/U | `bfind` 当前内部形式仅覆盖既有 parser 规则，不代表全部 signed/shiftamt modifier |
| `bfe`, `bfi`, `bmsk`, `prmt` | ZLUDA helper | B/U | 依赖 helper bitcode；`bmsk` 当前固定使用 clamp helper，其他模式未体现 |
| `sad` | 直接 emit | A/U | 基础整数绝对差累加路径存在 |
| `selp` | 直接 emit | A/U | 基础谓词选择路径存在 |

### 4.2 比较、转换和控制流

| 指令或指令族 | 路径 | 等级 | 已知限制与风险 |
| --- | --- | --- | --- |
| `set`, `set` 布尔组合 | 直接 emit | A/C/U | 内部由 `Set`、`SetBool` 表示；类型和 compare modifier 受 parser 枚举限制 |
| `setp`, `setp` 布尔组合 | 直接 emit | C | 单目标支持；带两个 predicate 目标的形式明确返回 `setp with two dst arguments not yet supported` |
| `cvt` | 直接 emit，部分 FP8 转 helper | A/B/C/U | 常见整数/浮点转换存在；f32→e4m3x2/e5m2x2 走 helper；特殊 rounding/satfinite/relu 组合需逐项验证 |
| `cvt.pack` | 直接 emit | C/U | 当前内部签名固定为特定 32 位输入/输出形态，不代表全部现代 packed conversion |
| `cvta` | 直接 emit | A/C/U | 依赖目标状态空间映射；cluster/param-func 相关空间不支持 |
| `bra` | 谓词先变 CFG，再直接 emit | A/U | 谓词化 branch 会在前置 pass 展开 |
| `call`, `ret` | ABI pass + 直接 emit | A/C/U | `.param` 通过 `deparamize_functions` 桥接；间接函数指针路径仍有实现风险；复杂 `ParamFunc` 不支持 |
| `exit` | 直接 emit | C | 只允许 kernel；普通 `.func` 中出现会返回 TODO |
| `trap` | `llvm.trap` + unreachable | A/U | 基础路径存在 |

### 4.3 浮点特殊函数

| 指令 | 路径 | 等级 | 已知限制与风险 |
| --- | --- | --- | --- |
| `rcp.approx.f32` | `llvm.nvvm.rcp.approx.f` | B/U | 无 FTZ 或 FTZ=false 的匹配进入 NVVM intrinsic；compliant reciprocal 会先改写为 `1/x` |
| `rsqrt.approx.f32` | `llvm.nvvm.rsqrt.approx.f` | B/U | 已验证的静态映射集中在 f32 approximate 形式 |
| `sqrt.approx.f32` | `llvm.nvvm.sqrt.approx.f` | B/U | 其他 `sqrt.rn.f32` 可能走 ZLUDA helper；不能概括为所有 sqrt 均为 NVVM intrinsic |
| `ex2.approx.f32` | `llvm.nvvm.ex2.approx.f` | B/U | 仅已有 parser/FTZ 组合 |
| `sin.approx.f32`, `cos.approx.f32` | emitter 中的 NVVM/LLVM 发射路径 | A/B/U | 需继续用 NVPTX verifier/codegen 验证 intrinsic 签名 |
| `tanh` | ZLUDA helper | B/U | 不是直接 NVVM intrinsic；依赖 helper 实现 |
| `copysign` | `llvm.copysign.*` | A/U | 参数顺序在 emitter 中显式调整 |

### 4.4 内存一致性、原子与同步

| 指令或指令族 | 路径 | 等级 | 已知限制与风险 |
| --- | --- | --- | --- |
| `atom`, `atom.cas` | LLVM atomic 发射 | C/U | 常见 global/shared 与 cta/gpu/sys scope 有路径；cluster scope 明确不支持；部分类型、vector qualifier 和新 atom 操作未覆盖 |
| `membar` | LLVM fence 发射 | C/U | `.cta/.gl/.sys` 主路径存在；cluster scope 不支持；现代 `fence.*`、proxy fence、mbarrier-init restriction 未实现 |
| `bar.sync` | ZLUDA helper | B/C/U | 依赖 `bar_sync` helper，不是 NVVM barrier intrinsic 的完整原生建模 |
| `bar.red` | ZLUDA helper | C | and/or predicate reduction 可走 helper；带 `src_threadcount` 的形式明确 TODO |
| `bar.warp.sync` | `llvm.nvvm.bar.warp.sync` | C | parser 保留输入 member mask，但 emitter 不读取该值，固定向 intrinsic 传 `0xffffffff`；仅全 lane mask 情况语义可能匹配 |
| `cp.async` | 同步 load + zero-extend + store | C | 能生成 IR，但异步语义被降级为同步 copy；不能验证 pipeline overlap 或 async-group 行为 |
| `cp.async.commit_group` | NOP | D | 操作被删除 |
| `cp.async.wait_group` | NOP | D | 操作被删除 |
| `cp.async.wait_all` | NOP | D | 操作被删除 |
| `prefetch` | NOP | D | hint 被删除；通常不改变功能结果，但不保留缓存/性能语义 |
| `createpolicy.fractional` | 返回常量 0 | D | 不是实际 cache policy 编码，所有策略语义丢失 |
| `griddepcontrol` | NOP | D | 跨 kernel 依赖控制语义未实现 |

### 4.5 Warp、矩阵和纹理

| 指令或指令族 | 路径 | 等级 | 已知限制与风险 |
| --- | --- | --- | --- |
| `activemask` | ZLUDA helper | B/U | 依赖 helper bitcode |
| `vote.sync` | ZLUDA helper | B/C/U | any/all/ballot 有映射；仅限 parser 当前形式 |
| `redux.sync` | ZLUDA helper | B/C/U | add/min/max 有映射，其他 reduction kind 不在该 lowering 集合 |
| `shfl.sync` | ZLUDA helper | B/C/U | 无 `dst_pred` 时直接 helper 化；有 `dst_pred` 时 Pass 18 已展开为返回 v2.u32 的 helper call、`RepackVector` 和 predicate `cvt`。仍需验证 helper ABI 与 member mask 语义。 |
| `match.sync` | ZLUDA helper | B/C/U | 当前 helper 名为 `match_any_sync_*`，不能据此声称支持全部 match 模式 |
| `nanosleep` | ZLUDA helper | B/U | 依赖 helper 实现 |
| `dp4a` | `llvm.nvvm.idp4a.*.*` | C | u/u 与 s/s 支持；u/s 或 s/u 混合 signedness 明确 TODO |
| `dp2a` | ZLUDA helper | B/C/U | lo/hi 和当前 parser 类型组合走 helper |
| `mma.sync.aligned` | ZLUDA helper | C/U | 当前 helper 命名只覆盖 parser 已建模的有限 shape/type/layout；不是 WGMMA 或 tcgen05 |
| `ldmatrix.sync.aligned` | ZLUDA helper | C | 仅 `m8n8`、`x2/x4`、`b16`；`m16n16`、`x1`、`b8` 明确 TODO |
| `tex` | ZLUDA helper | B/C/U | texref/texobj、1D/2D/3D 和当前 dtype/coord 组合；依赖 helper 与纹理对象 ABI |
| `vshr` | 直接 emit | C | clamp 支持；wrap 明确 TODO；当前只实现 `VshOp::Add` |

## 5. 明确不支持或缺失的现代 PTX 指令族

下面这些不是“缺少一个 modifier”，而是当前 `Instruction` enum 和 parser 中没有完整指令表示，或 lowering 核心空间明确拒绝。它们对 SM110 尤其重要。

| 指令族/能力 | 当前状态 | 对 SM110 的影响 |
| --- | --- | --- |
| `tcgen05.*` | parser/AST 无对应指令变体；vendored LLVM 对 SM110-family 的合法目标是 `sm_110a + PTX 9.0` | 当前不可用；即使补 parser，也不能在精确目标 `sm_110` 上误开 tcgen05 |
| `wgmma.*` | parser/AST 无对应指令变体 | Warpgroup MMA 不可用 |
| `cp.async.bulk*` / TMA bulk copy | parser/AST 无对应指令变体 | TMA global/shared/tensor bulk movement 不可用 |
| `mbarrier.*` | parser/AST 无完整指令族 | TMA 与异步 pipeline 常用完成机制不可用 |
| `tensormap.*` | parser/AST 无完整指令族 | Tensor map 创建、替换、代理访问不可用 |
| `fence.*` / `fence.proxy.*` | parser 源码只有待实现注释，实际仅有旧 `membar` 路径 | async proxy、tensormap proxy、cluster fence 语义不可用 |
| cluster state-space 与 scope | parser 部分位置能表示，LLVM 地址空间和 scope lowering 明确 TODO | `shared::cluster`、cluster atom/fence 无法发射 |
| `stmatrix` | parser/AST 无对应指令变体 | 矩阵寄存器到 shared memory 的对应现代路径不可用 |
| `mma.sp` | parser/AST 无对应独立变体 | structured sparsity MMA 不可用 |
| `wmma.*` | parser/AST 无对应完整指令族 | 旧 WMMA API 级 PTX 指令也不能依赖当前前端 |
| `multimem.*` | parser/AST 无对应指令族 | 多播/多内存访问语义不可用 |
| cluster/CTA rank 与 map 指令，如 `mapa`、cluster rank 查询 | parser/AST 无完整覆盖 | thread-block cluster 地址和 rank 操作不可用 |
| 新 cluster launch control 指令 | parser/AST 无对应指令族 | SM10x/SM11x 的相关调度控制能力不可用 |

这些缺失意味着：即使输入写 `.target sm_110`，前端也不会因为目标较新而自动获得这些指令。当前 pipeline 没有按 `sm_version` 选择不同 parser、pass 或 intrinsic lowering；`sm_version` 基本只被用于输出 `target-cpu` 和 kernel metadata。

## 6. 地址空间、scope 和 modifier 的横向限制

### 6.1 地址空间

[`ptx/src/pass/llvm/mod.rs`](ptx/src/pass/llvm/mod.rs) 当前可映射 `Generic`、`Global`、`Shared`、`Const`、`Local` 和内部 `ParamEntry`。以下空间明确返回 TODO：

- `ParamFunc`
- `SharedCta`
- `SharedCluster`

因此，不能因为 `ld/st` opcode 可用，就声称所有 `ld.shared::*`、函数参数地址或 cluster shared 访问均可用。状态空间是独立于 opcode 的支持维度。

### 6.2 memory scope

原子和 membar lowering 对 `Cta`、`Gpu`、`Sys` 有映射，但 `MemScope::Cluster` 明确返回 TODO。更值得注意的是，scope 名称和注释仍残留 AMDGPU 语义，例如 `workgroup-one-as`、`agent-one-as`。当前工程虽已将最终目标改为 NVPTX/NVVM，但这些 memory scope 映射没有完成系统性的 NVIDIA 内存模型审计，必须用 LLVM NVPTX verifier 和 litmus test 验证，不能只看 IR 能否打印。

### 6.3 cache、prefetch 与一致性 modifier

parser 对部分 `ld/st/atom` modifier 有规则，但实现不会完整保留所有 eviction policy、L2 prefetch size、cache hint 和 proxy semantics。`prefetch` 本身被当成 NOP，`createpolicy.fractional` 返回常量零。因此，功能结果可能在普通场景下仍正确，性能和缓存一致性意图却不一定保留。

### 6.4 浮点 modifier

舍入和 FTZ 会经过原 ZLUDA 的 `instruction_mode_to_global_mode`，必要时转 constrained FP 或 helper。该设计源自 AMDGPU 全局模式适配，不是 NVVM 原生逐指令语义的完整证明。`.rn/.rz/.rm/.rp`、`.ftz`、`.sat`、`.relu` 和不同 f16/f32/f64/bf16 组合应分别测试。尤其是 `.relu` 等较新 modifier，parser 源码中存在未完成注释或有限规则。

## 7. SM107 与 SM110 目标审计

### 7.1 `.target` 在当前前端中的传播

[`ptx_parser/src/lib.rs`](ptx_parser/src/lib.rs) 的 `shader_model()` 接受：

```text
sm_ + 十进制数字 + 可选的一个小写字母
```

因此 `sm_107`、`sm_110`、`sm_110a` 和 `sm_110f` 都能通过这一语法层。问题发生在 module 构造时：`target()` 返回 `(u32, Option<char>)`，但 `ptx_parser::Module` 只有 `sm_version: u32`，后缀被丢弃。之后 [`ptx/src/pass/llvm/emit.rs`](ptx/src/pass/llvm/emit.rs) 只执行：

```text
sm_version = 110 -> target-cpu="sm_110"
```

前端不会查询 LLVM 的合法 processor 表，也不会按 SM 对指令进行 feature gating。于是“能生成带 target-cpu 的 IR”只是字符串传播能力，不等于目标 CPU 真实受支持。

### 7.2 vendored LLVM 对处理器名称的认识

当前 vendored 源码版本是 LLVM 22.0.0git。其 [`ext/llvm-project/llvm/lib/Target/NVPTX/NVPTX.td`](ext/llvm-project/llvm/lib/Target/NVPTX/NVPTX.td) 包含：

```text
sm_110, sm_110a, sm_110f
```

但处理器列表中没有：

```text
sm_107
```

所以目标状态应写成：

| 目标 | 前端解析 | 生成 `target-cpu` | vendored NVPTX processor | 当前结论 |
| --- | --- | --- | --- | --- |
| `sm_110` | 是 | 是 | 是 | IR 目标名成立，但现代指令覆盖不足，需外部 NVPTX backend 验证 |
| `sm_110a` | 语法上是 | 实际退化为 `sm_110` | 是 | 后缀丢失，不能声称保留 `a` 特性 |
| `sm_110f` | 语法上是 | 实际退化为 `sm_110` | 是 | 后缀丢失，不能声称保留 `f` 特性 |
| `sm_107` | 是 | 是 | 否 | 仅能生成一个 backend 不认识的 CPU 字符串，当前不支持 codegen |

如果“SM107”是项目内部对某个未进入该 LLVM processor 表的硬件或虚拟目标的命名，需要额外提供目标别名或 backend patch；当前源码没有这层映射。如果实际目标是其他官方 processor 名称，应在调用方先校正目标值，而不是依赖当前 parser 自动纠错。

### 7.3 本项目默认 LLVM 构建不包含 NVPTX backend

[`llvm_zluda/build.rs`](llvm_zluda/build.rs) 当前设置：

```text
LLVM_TARGETS_TO_BUILD=AMDGPU
```

因此，vendored LLVM 源码中“存在 SM110 processor definition”和本项目默认构建“可以执行 NVPTX codegen”是两回事。当前 `dump_ir` 路径可用 LLVM C API 创建并打印 NVVM 风格 IR，但默认构建的 LLVM 库不提供完整 NVPTX backend codegen。要验证 IR→PTX，需要另行使用包含 NVPTX target 的 LLVM 构建，或者修改构建配置后重新构建相关组件。

## 8. 按目标给出的可用范围

### 8.1 面向 SM110 family

当前适合作为第一阶段验证输入的范围：

- 标量整数与常见 f16/f32/f64 算术
- 基础 bit operation、compare、select 和 branch
- 普通 kernel 参数及 64 位 global pointer
- global/shared/local/const 的基础 load/store
- cta/gpu/sys 范围内的基础原子和 membar，前提是完成 NVIDIA memory-scope 复核
- 特殊寄存器 `%tid/%ntid/%ctaid/%nctaid/%laneid` 等已映射部分
- 传统 warp vote/shuffle/redux，通过 helper 的有限形式
- `dp4a` 同 signedness 形式
- 有限的 `mma.sync.aligned` 与 `ldmatrix` helper 形式
- approximate f32 特殊函数的 NVVM intrinsic 路径

当前不适合声称支持的 SM110 核心能力：

- TMA / `cp.async.bulk*`
- `mbarrier.*`
- `wgmma.*`
- `tcgen05.*`
- cluster shared memory、cluster atom/fence
- tensormap 与 proxy fence
- 完整矩阵 shape/type/layout 空间
- cache policy、grid dependency 和 async group 的原始语义

其中 tcgen05 必须进一步限定为 `sm_110a + PTX 9.0`，不能因 processor 表同时存在 `sm_110/sm_110a/sm_110f` 就认为三者 feature 等价。因此对 SM110 family 的合理表述是：“基础 PTX 子集可生成 NVVM IR，精确 target 后缀尚未保留，Blackwell/新一代异步与 tensor 指令子集尚未实现”，而不是“支持 SM110 PTX”。

### 8.2 面向 SM107

在当前仓库中，SM107 的问题首先不是 opcode 覆盖，而是目标处理器身份不成立：

- parser 不验证数字 107 是否为已知 processor；
- emitter 会机械地产生 `target-cpu="sm_107"`；
- vendored LLVM NVPTX processor 表没有 `sm_107`；
- 默认 LLVM 构建还没有编入 NVPTX backend。

因此当前对 SM107 的支持评级为 E。除非目标工具链明确接受 `sm_107`，或者项目补充 processor 定义/别名和对应 feature set，否则不应将生成 IR 成功视为 SM107 支持。即使解决 processor 名称问题，仍需重新应用本文对指令、modifier、状态空间和现代指令族的限制。

## 9. 验证优先级

为了把静态支持矩阵推进到“可证明正确”，建议按以下顺序建立测试，不宜一开始追求 PTX ISA 全覆盖。

### P0：阻断性目标验证

1. 使用包含 NVPTX target 的 LLVM，对最小 `sm_110` module 执行 verifier 和 IR→PTX codegen。
2. 对 `sm_107` 执行同一命令，记录 unknown processor 或 feature 结果；在目标身份明确前停止扩大 SM107 指令测试。
3. 增加 `.target sm_110a` 和 `.target sm_110f` 测试，要求完整保留后缀；tcgen05 用例必须精确检查 `sm_110a + PTX 9.0`，不得静默按 `sm_110` 继续。

### P1：基础语义

1. 整数/浮点算术、compare、branch、loop、function call。
2. kernel `.param` 到 `addrspace(101)`，global/shared/local/const load/store。
3. atom/cas 和 cta/gpu/sys fence 的并发 litmus test。
4. 特殊寄存器 x/y/z 分量和 launch dimensions。

### P2：已存在但部分支持

1. `setp` 单目标与双目标。
2. `dp4a` 四种 signedness 组合。
3. `ldmatrix` 的 x1/x2/x4、m8n8/m16n16、b8/b16 组合。
4. `shfl.sync` 有无 predicate 目标，并验证 Pass 18 的 call→repack→cvt 顺序。
5. `bar.red` 有无 threadcount。
6. `vshr` clamp/wrap。
7. `cp.async` 与真实异步可见性、commit/wait 行为对照。

### P3：SM110 新指令补齐

优先依赖链应是：完整 target descriptor → cluster state-space/scope → `mbarrier` → TMA/tensormap/proxy fence → WGMMA/tcgen05。原因是后面的 tensor/async 指令通常依赖前面的目标、地址空间和同步基础；只增加 parser opcode 而没有这些语义层，仍然无法正确运行。具体应修改的既有 Pass 与新增协议 Pass 的判定见 [`PASS_DESIGN/README.md`](PASS_DESIGN/README.md)。

## 10. 维护时的判定规则

新增或审计一条 PTX 指令时，应依次回答：

1. parser 是否有语法规则，并且是否保留了所有影响语义的 modifier？
2. `Instruction` enum 是否能表示该 shape/type/scope，而不是把信息丢在解析阶段？
3. pass 是否会改写它；改写后是否保留谓词、地址空间、同步和浮点模式？
4. 最终是直接 LLVM IR、`llvm.nvvm.*`，还是 `__zluda_ptx_impl_*`？
5. helper 声明是否有实际 bitcode 定义，签名是否一致？
6. NVVM intrinsic 是否在所用 LLVM 版本和目标 SM 上合法？
7. 是否有 PTX→LLVM verifier→NVPTX codegen→硬件结果的端到端测试？

只有前六项成立并通过第七项，才应把该具体 opcode + modifier + type + state-space 组合标为“已验证支持”。

### 10.1 本轮对抗式复审

本轮用“找出能推翻支持结论的源码分支”复核矩阵，得到并修正了三项旧结论：

- `shfl.sync` 的 predicate destination 已有 Pass 18 专用展开，旧文档写成必然失败不再成立；但 helper ABI 尚未端到端验证，所以仍是 B/C/U。
- `lg2.approx.f32` 在表中重复出现，已删除重复行。
- tcgen05 不能笼统归入 `sm_110`：vendored LLVM 的 feature predicate 对 SM110-family 要求精确 `sm_110a + PTX 9.0`。

仍未通过的广义主张是“支持 SM110 PTX”：目标后缀丢失、默认 LLVM 缺 NVPTX backend、现代指令族缺失和大量 U 级组合都构成反例。因此本文只给具体组合评级，不给架构级“支持”标签。

## 11. 源码证据索引

- 指令 enum：[`ptx_parser/src/ast.rs`](ptx_parser/src/ast.rs)
- parser 与 `.target`：[`ptx_parser/src/lib.rs`](ptx_parser/src/lib.rs)
- pass 顺序与 `sm_version` 传播：[`ptx/src/pass/mod.rs`](ptx/src/pass/mod.rs)
- 特殊寄存器 lowering：[`ptx/src/pass/fix_special_registers.rs`](ptx/src/pass/fix_special_registers.rs)
- helper/NVVM intrinsic 替换：[`ptx/src/pass/replace_instructions_with_functions.rs`](ptx/src/pass/replace_instructions_with_functions.rs)
- 特殊浮点 helper：[`ptx/src/pass/replace_instructions_with_functions_fp_required.rs`](ptx/src/pass/replace_instructions_with_functions_fp_required.rs)
- LLVM emitter：[`ptx/src/pass/llvm/emit.rs`](ptx/src/pass/llvm/emit.rs)
- LLVM 类型与地址空间：[`ptx/src/pass/llvm/mod.rs`](ptx/src/pass/llvm/mod.rs)
- NVPTX processor 定义：[`ext/llvm-project/llvm/lib/Target/NVPTX/NVPTX.td`](ext/llvm-project/llvm/lib/Target/NVPTX/NVPTX.td)
- LLVM 构建目标配置：[`llvm_zluda/build.rs`](llvm_zluda/build.rs)

## 12. 最终评级

| 维度 | SM110 | SM107 |
| --- | --- | --- |
| parser 接受 `.target` | 是 | 是 |
| 正确保留目标后缀 | 否，`a/f` 会丢失 | 不适用 |
| 生成带 `target-cpu` 的 NVVM IR | 是 | 是，但只是字符串透传 |
| vendored LLVM 认识 processor | 是 | 否 |
| 默认本地 LLVM 构建可做 NVPTX codegen | 否 | 否 |
| 基础标量 PTX 子集 | 可继续验证 | 在 processor 问题解决前无有效目标结论 |
| cluster/TMA/mbarrier | 不支持 | 不支持 |
| wgmma/tcgen05 | 不支持；tcgen05 的未来目标还必须是精确 `sm_110a` | 不支持 |
| 综合评级 | C：基础子集可用，现代 SM110 能力缺失 | E：目标 processor 不成立，不能声称支持 |

当前最准确的项目能力描述是：**能够把一个有限、以传统 CUDA core 指令和部分 helper/intrinsic 为主的 PTX 子集转换成带 SM 数字属性的 NVVM LLVM IR；对 SM110 具备基础起点，但不覆盖关键新指令族；对 SM107 尚不具备有效的 backend 目标支持。**
