# Pass 11：`replace_instructions_with_functions_fp_required`

源码：[`../ptx/src/pass/replace_instructions_with_functions_fp_required.rs`](../ptx/src/pass/replace_instructions_with_functions_fp_required.rs)

## 契约与变换

实际匹配条件是所有 `DivDetails::Float` 且 `DivFloatKind::Rounding(rnd)` 的指令，不只源码注释所说的 `div.rn.ftz.f32`。每条匹配指令变为：模式标记 → part1 helper call → 原要求模式标记 → part2 helper call。只要发生一次匹配，module 前会同时加入 f32 和 f64 两组 extern 声明。

输出不变量：被匹配的 rounding div 已消失，其两段 helper 的 FTZ/rounding 需求可被 Pass 14 观察。

## 顺序依赖

必须在 CFG 模式分析前；也要晚于 Pass 10，让 compliant reciprocal 产生的 div 进入同一规则。

## 现代指令接入

现代非浮点除法无需修改。新增 f16/bf16/fp8 division 时不能默认复用：当前代码仅区分 `type_ == F64`，其余全部选择 f32 helper。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| `div.rz.f32` 或非 FTZ div | pattern 接受任意 `Rounding(rnd)`，`ftz` 缺省为 false | 也会拆 helper；旧窄描述不成立 |
| f16 rounding div | `if type_ == F64 { f64 } else { f32 }` | 会错误选择 f32 ABI；必须拒绝或扩展 |
| module 只用 f32 | `FunctionImports` 初始化并 `get_functions` 两种类型 | 产生未使用 f64 声明，功能可行但冗余 |

## 测试要求

当前无专属 fixture。补全部 rounding、FTZ on/off、f32/f64 helper signature、低精度拒绝、声明去重及与 Pass 14 模式序列的组合测试。
