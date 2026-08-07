# tcgen05 接入 PTX→NVVM Pipeline 的异步设计

## 1. 范围与状态

本文只描述 tcgen05 对当前 ZLUDA pipeline 的增量设计，不重复 19 个 Pass 的通用职责。当前 Pass 顺序见 [`PTX_TO_NVVM_PASS_PIPELINE.md`](PTX_TO_NVVM_PASS_PIPELINE.md)，逐 Pass 契约见 [`PASS_DESIGN/`](PASS_DESIGN/README.md)。

当前状态：仓库 parser/AST 尚无完整 `tcgen05.*` 指令族，本文方案尚未实现。文中的“新增”均为建议，不得当作当前能力。

## 2. 决策摘要

1. wait/fence 的最小闭环不需要前端调度 Pass，但必须发射标准 effectful NVVM intrinsic。
2. 从支持 tcgen05.ld/st 起，需要一个窄职责 `validate_and_materialize_tcgen05_async` Pass。
3. 新 Pass 放在当前 Pass 14 后、Pass 15 前；它验证 pending/ready 并在 wait 后物化结果，不计算 SASS 调度。
4. Pass 7 必须改变 tcgen05.ld tuple 的展开方式；只修改 Pass 15 已经太晚。
5. TMEM `.reg .b32` 地址值和 LLVM `ptr addrspace(6)` 是两个层次，不能把变量 storage 直接改成 TMEM。
6. `sm_110`、`sm_110a`、`sm_110f` 不能混用；vendored LLVM 对 SM110-family tcgen05 要求精确 `sm_110a + PTX 9.0`。
7. intrinsic attributes 不是 consumer 顺序证明；P3 必须通过 O3 与 NVPTX codegen 的 ordering gate。

## 3. 当前实现中的四个断点

### 3.1 target 后缀丢失

parser 的 target 语法能读可选后缀，但 `ptx_parser::Module` 只保存数字 `sm_version`。因此 `.target sm_110a` 当前会退化为 `target-cpu="sm_110"`，无法触发 `hasTcgen05Instructions()` 的 `sm_110a` 分支。

必须先引入完整 target descriptor：

```rust
struct PtxTarget {
    ptx_version: (u8, u8),
    sm: u32,
    suffix: Option<TargetSuffix>, // a / f
    address_size: u8,
}
```

### 3.2 Pass 7 会提前消费 ld 结果

当前 `expand_operands::vec_pack(is_dst=true)` 生成 packed temporary，并在主指令后立即追加普通 `RepackVector`：

```text
%pending = tcgen05.ld ...
RepackVector %pending -> {%r0, %r1, ...}
tcgen05.wait::ld
```

`RepackVector` 已是对 pending result 的普通 use。之后 Pass 15 再延迟 local store，无法撤销这次提前消费。

### 3.3 类型系统不能区分 TMEM 地址值

当前 resolver 主要保存 `(Type, StateSpace)`。PTX 的 `%taddr` 通常是 `.reg .b32`：storage 是 Reg，但值语义是 TMEM address。只保存普通 b32 会允许错误的整数/通用 pointer 转换；把变量标成 `StateSpace::Tmem` 又混淆 storage 与 pointee。

### 3.4 LLVM 顺序没有现成证明

vendored LLVM 当前定义：

| 操作 | intrinsic 属性 |
| --- | --- |
| tcgen05.ld/st | `IntrConvergent + IntrArgMemOnly` |
| wait.ld/st | `IntrConvergent + IntrInaccessibleMemOnly` |
| fence.before/after.thread.sync | `IntrNoMem + IntrHasSideEffects`，不是 convergent |

ld result、wait 和后续 extract/store 之间没有天然的普通 SSA chain。前端把 consumer 写在 wait 后是必要条件，但仍需证明 optimizer 与 MachineScheduler 不会越过 wait。

## 4. 建议的内部表示

### 4.1 AST

parser/AST 应强类型保存：

- operation family：alloc/dealloc/commit/wait/fence/ld/st/cp/mma/shift/collector；
- CTA group、shape、kind、pack/unpack、source format；
- 每个 operand 的 source/destination、type、space、immediate 约束；
- PTX version 和精确 target feature requirement。

不能把 modifier 拼成字符串交给 emitter 再解析。

### 4.2 TMEM 地址值

在 variable storage 之外增加值类别，例如：

```rust
enum ValueKind {
    Plain,
    TmemAddress32,
}
```

PTX `%taddr` 表示为：

```text
(Type::B32, StateSpace::Reg, ValueKind::TmemAddress32)
```

另设 `PointerSpace::Tmem = 6` 或等价常量，只在 operand 期望类型与 LLVM intrinsic ABI 边界构造 `ptr addrspace(6)`。普通 `ld/st/cvta` 和 generic cast 不得自动接受该值类别。

### 4.3 pending-unpack marker

Pass 7 对 tcgen05.ld destination tuple 不生成普通 `RepackVector`，而生成不发射代码的 marker：

```rust
Statement::Tcgen05PendingUnpack(PendingUnpackDetails {
    packed: SpirvWord,
    unpacked: Vec<SpirvWord>,
    typ: ScalarType,
    relaxed_type_check: bool,
})
```

约束：

- visitor 可映射 ID，但 `unpacked` 尚未定义/ready；
- emitter 不为 marker 生成 LLVM 指令；
- marker 必须在 Pass 15 前被消费；
- pending destination 在 wait 前被读、重定义或再次登记时报告错误。

## 5. 新 Pass 的位置与职责

建议 pipeline 片段：

```text
12 normalize_basic_blocks
13 remove_unreachable_basic_blocks
14 instruction_mode_to_global_mode
   validate_and_materialize_tcgen05_async   ← 新增
15 insert_explicit_load_store
16 convert_32bit_to_64bit（条件）
17 insert_implicit_conversions
```

Pass 14 可能创建模式 prologue 和重定向边，因此异步分析应看到其最终 CFG；Pass 15 尚未把 PTX `.reg` 改为 local slot，因此仍能直接检查原寄存器 pending/ready 状态。

建议 Pass 的通用契约也记录在 [`PASS_DESIGN/PROPOSED_PASSES.md`](PASS_DESIGN/PROPOSED_PASSES.md)。

### 5.1 V0：直线 ld/st

V0 只承诺单基本块、单 CTA-group/async-kind：

```rust
struct PendingLdBundle {
    packed: SpirvWord,
    unpacked: Vec<SpirvWord>,
    epoch: u32,
}

struct Tcgen05AsyncStateV0 {
    pending_ld: Vec<PendingLdBundle>,
    pending_registers: Map<SpirvWord, u32>,
    pending_st: bool,
    epoch: u32,
}
```

transfer 规则：

1. pending marker 登记 packed/unpacked/epoch。
2. 普通 use 或 redefine pending register → 错误。
3. `wait::ld` 保留原位置，并在其后生成对应普通 `RepackVector`。
4. `tcgen05.st` 标记 pending store，`wait::st` 清除。
5. branch/call/return/块结束时 pending 非空 → V0 拒绝。
6. 输出残留 marker → 内部错误。

结果顺序：

```text
%pending = call @llvm.nvvm.tcgen05.ld...()
call @llvm.nvvm.tcgen05.wait.ld()
RepackVector %pending -> {%r0, %r1, ...}
```

随后 Pass 15 按通用规则在 `RepackVector` 后插 local stores，不保存 tcgen05 状态。

### 5.2 CFG 版本

扩展同一个 Pass，对每个块求解：

```text
IN[B]  = merge(OUT[pred(B)]...)
OUT[B] = transfer(B, IN[B])
```

第一版 merge 保守要求相同状态：一条前驱 pending、另一条 ready 时直接诊断；携 pending 的循环回边也先拒绝。wait 后物化规则与 V0 相同。

### 5.3 完整协议状态

V0 的一个 bool/epoch 不能表示 commit、cp、mma、mbarrier、collector 和不同 CTA group。完整版本至少按 `(CtaGroup, AsyncKind)` 分队列，并分别记录：

- allocation ownership 与 dealloc/relinquish；
- pending operation batches；
- commit group；
- mbarrier phase/arrival；
- collector acquire/use/release。

资源协议可由同一分析框架扩展，但不要伪装成 V0 已覆盖。

## 6. 现有 Pass 的最小改动

未列出的 Pass 只需回归测试；完整职责见各自独立文档。

| 边界 | 改动 |
| --- | --- |
| target/parser | 完整 target descriptor；tcgen05 强类型 AST；早期 feature validator |
| Pass 03 | 验证各 tcgen05 form 是否允许谓词化；允许时保持 CFG 路径 |
| Pass 07 | tuple destination 生成 pending marker，不生成立即 `RepackVector` |
| Pass 08 | 穷尽 match 将 tcgen05 分类为非 saturation |
| Pass 12–14 | marker 透传；Pass 14 `get_modes` 明确分类为无 FP 模式 |
| 新协议 Pass | 验证 pending/ready；wait 后物化；以后扩展 CFG/protocol |
| Pass 15 | 保持通用；仅断言 marker 不得漏入 |
| Pass 16 | 第一阶段对含 tcgen05 的 `.address_size 32` module 明确拒绝 |
| Pass 17 | 增加 TMEM 地址值到 addrspace(6) pointer 的受限转换 |
| Pass 18 | tcgen05 不得进入普通 `__zluda_ptx_impl_*` helper；标准 intrinsic 用 registry 获取 |
| emitter | 发射注册的 `llvm.nvvm.tcgen05.*`，绝不把 wait/fence 当 NOP |

## 7. emitter 与后端边界

通过 `LLVMLookupIntrinsicID` 和 `LLVMGetIntrinsicDeclaration` 获取声明；ID 为零时报告当前 LLVM 不支持，不能退回 `LLVMAddFunction` 创建同名普通函数。signature 以 vendored `IntrinsicsNVVM.td` 为唯一 ABI 依据。

职责分界：

```text
ZLUDA：保留 target、协议、effect 和 ready point
LLVM NVPTX：intrinsic selection 与机器依赖
ptxas：最终 SASS opcode、scoreboard 和控制位
```

前端不分配 barrier index、wait mask 或 reuse bits。

## 8. 分阶段实施

| 阶段 | 范围 | 完成门槛 |
| --- | --- | --- |
| P0 | 完整 target、PTX 9.0、SM110a、TMEM value/pointer 类型 | `sm_110a` 不再退化；最小 module verifier+NVPTX codegen |
| P1 | wait/fence/relinquish | O0/O3 不消失；llc 输出合法 tcgen05 PTX；ptxas 接受 |
| P2 | alloc/dealloc/commit/shift 单操作 | target、CTA group、columns、pointer space 正反例 |
| P3 | 直线 ld/st + pending marker/materializer | `ld→wait→use`、`st→wait→return`，ordering gate 与硬件数值通过 |
| P4 | CFG pending/ready | 双侧 wait、漏 wait、merge 冲突、loop、return pending |
| P5 | mma/cp/collector/完整资源协议 | 分组 protocol state、mbarrier、ownership 和压力测试 |

P2 只证明单操作合法性，不代表完整生命周期已验证。

## 9. 测试与证明门槛

### 9.1 Pass 不变量

| 检查点 | 必须证明 |
| --- | --- |
| parser/target 后 | 精确保存 `sm_110a + PTX 9.0`；非法 form 诊断 |
| Pass 07 后 | ld 后只有 pending marker，没有普通 `RepackVector` |
| Pass 08–14 后 | marker ID 正确且 unpacked 未被当作 ready destination |
| 新协议 Pass 后 | wait 后物化；marker 清零；wait 前 use/redefine 报错 |
| Pass 15 后 | extract/store 位于 wait 后；Pass 15 无 tcgen05 状态 |
| Pass 17 后 | TMEM 参数为 addrspace(6)，无 generic cast |
| LLVM emit 后 | intrinsic ID、签名、attributes 正确，verifier 通过 |

### 9.2 Ordering proof gate

测试必须真的消费 ld 返回值：

```text
tcgen05.ld → wait.ld → extract → arithmetic → observable store
```

同时检查：

1. `opt -O3` 后 consumer 没有越过 wait；
2. `llc -march=nvptx64 -mcpu=sm_110a -mattr=+ptx90` 输出顺序正确；
3. ptxas/SASS 控制位差分合理；
4. SM110a 硬件结果与压力测试正确。

现有 `tcgen05-ld.ll` 主要忽略返回值，不能作为该顺序证明。若 gate 失败，应在 NVPTX lowering 增加 chain/glue，或引入明确 pending→ready token/pseudo；不得用关闭优化作为正式方案。

## 10. 对抗式审查记录

| 被挑战方案 | 反例 | 修正后结论 |
| --- | --- | --- |
| “只改 Pass 15 延迟 store” | Pass 7 已立即生成 `RepackVector` | 必须先改 Pass 7，并在 Pass 15 前物化 |
| “增加 `StateSpace::Tmem` 即可” | `%taddr` 变量实际存于 `.reg` | storage 与 value/pointer kind 分层 |
| “wait/fence 都是 convergent” | fence TD 只有 `NoMem + HasSideEffects` | 分别记录真实 attributes |
| “源 LLVM IR 词法顺序足够” | wait 与 consumer 无普通 SSA/memory chain | 增加 O3/llc ordering gate；失败修 backend dependency |
| “一个 pending map/bool 可覆盖全部 tcgen05” | CTA group、commit、mbarrier、collector 可并行 | V0 明确限于直线 ld/st，完整 protocol state 后续实现 |
| “SM110 family 都能用 tcgen05” | `hasTcgen05Instructions` 对 110 只列 `sm_110a` | 精确 target gating，不接受 suffix 丢失 |

本轮设计审查在文档层通过：上述已知反例均不再与正文结论冲突。实现层仍未通过，因为 parser、marker、新 Pass、类型系统和 ordering tests 尚未落地。
