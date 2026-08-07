# Pass 06：`fix_special_registers`

源码：[`../ptx/src/pass/fix_special_registers.rs`](../ptx/src/pass/fix_special_registers.rs)

## 契约与变换

本 Pass 预先添加 `SpecialRegistersMap` 中全部外部函数声明；读取特殊寄存器时，在当前 statement 前插入 call，并用返回临时 ID 替换 operand。向特殊寄存器写入会报类型错误；向量 axis 由 `(special register, member)` 选择对应声明。

输出不变量：后续 Pass 不再看到可识别的特殊寄存器 operand，只看到普通 call result。

## 顺序依赖

必须在 `expand_operands` 前处理 `RegOffset/VecMember/VecPack` 内的特殊 ID；其输出 call 和临时值则继续走通用操作数/类型 Pass。

## 现代指令接入

若现代架构新增特殊寄存器，应扩展 `SpecialRegistersMap`、返回类型、axis 规则和 NVVM intrinsic 名称。普通现代 opcode 不需改本 Pass。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 未使用任何特殊寄存器 | `foreach_declaration` 仍添加全部声明 | IR 会含未使用 extern；功能可行但冗余 |
| 写特殊寄存器 | `is_dst` 时返回类型错误 | 已拒绝 |
| 特殊寄存器出现在 VecPack | `map_operand` 逐元素替换 | 已覆盖，但需要测试 axis/非 axis 差异 |

## 测试要求

当前无专属 fixture。补齐 scalar、x/y/z、VecPack、非法 destination、未使用声明策略以及 intrinsic signature/verifier 测试。
