# Pass 17：`insert_implicit_conversions`

源码：[`../ptx/src/pass/insert_implicit_conversions.rs`](../ptx/src/pass/insert_implicit_conversions.rs)

## 契约与变换

本 Pass 比较 resolver 中 operand 的实际 type/space 与 instruction visitor 声明的期望 type/space，在 statement 前后插入 `Conversion`。覆盖同宽 bitcast、relaxed source/destination、AddressOf、BitToPtr、PtrToPtr，以及 32 位 module 的部分指针规则。Tex 还会根据 pointer operand 形态修正 `TexType`。

输出不变量：emitter 不再负责 PTX 隐式类型兼容；每个被访问 operand 都应满足 instruction 的精确签名。

## 顺序依赖

必须在 Pass 15/16 确定最终变量空间和地址模型后、Pass 18 让 opcode 消失前执行。

## 现代指令接入

新增地址空间和语义化 handle 是高风险修改点。TMEM `.reg .b32` 应保留 Reg storage，并用 `TmemAddress32` 等值类别在 intrinsic 边界构造 `addrspace(6)`；不能简单增加 `StateSpace::Tmem` 给变量。cluster/shared::cta/ParamFunc 必须先消除当前 panic/TODO。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| `SharedCluster/SharedCta/ParamFunc` 进入 `is_addressable` | 分支调用 `todo!()` | 会 panic；健壮性未通过 |
| 同宽普通 u32 与 TMEM address | resolver 只保存 type/space | 无法区分，需扩展值语义 |
| relaxed vector/scalar bitcast | 有专门 size 规则 | 基础路径已有 fixture，但大 vector 仍需测 |

## 测试要求

现有 fixture 覆盖默认、relaxed 和部分 vector/scalar bitcast。仍需补所有 address space、32 位路径、panic 改错误、TMEM/descriptor 值类别、非法 generic cast 和 intrinsic ABI pointer 测试。
