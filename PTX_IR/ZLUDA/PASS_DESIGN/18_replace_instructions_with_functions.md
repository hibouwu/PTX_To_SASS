# Pass 18：`replace_instructions_with_functions`

源码：[`../ptx/src/pass/replace_instructions_with_functions.rs`](../ptx/src/pass/replace_instructions_with_functions.rs)

## 契约与变换

本 Pass 把选定的浮点、warp、矩阵、纹理和 helper opcode 改为 extern `Call`，并用有序 map 生成确定顺序的声明。名称含 `.` 时按完整 LLVM/intrinsic 名称使用，否则添加 `__zluda_ptx_impl_` 前缀。部分指令会展开为 call 加 repack/cvt；未匹配 instruction 通过通配分支原样保留。

输出不变量：被选定组合已成为确定签名的 call；其他 opcode 交给 emitter。不是所有同名 opcode 的 modifier 都一定匹配。

## 顺序依赖

必须在 Pass 17 完成原 PTX operand 类型规则之后，在 globals hoist 和 emit 之前。

## 现代指令接入

标准 NVVM intrinsic 应优先通过 LLVM intrinsic registry 声明，尤其是 overloaded、大 vector、effectful/convergent 指令。不能只因名称包含 `.` 就按普通 extern 函数生成。新 opcode 的默认透传不会报错，必须明确决定“direct emit / intrinsic / helper / reject”。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 新 instruction 未加入任何分支 | 末尾 `i => i` | 会静默透传，直到 emitter；需审计清单 |
| 同一 helper 名称出现不同签名 | 声明 map 只按名称 key，Occupied 不比较签名 | 可能复用错误声明；未通过 |
| `shfl.sync` 带 `dst_pred` | `run_statements` 已专门 call+repack+cvt | 当前已支持该 lowering，旧支持矩阵结论过时 |
| 标准 NVVM overloaded intrinsic | 当前仍构造普通 extern declaration | attributes/ABI 可能不完整，需 registry API |

## 测试要求

当前无专属 fixture。按每个匹配组合补 helper 名、签名、声明去重、未匹配负例；新增同名异签名冲突测试和 NVVM intrinsic ID/declaration/attribute verifier 测试。
