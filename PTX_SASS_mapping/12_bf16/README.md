# 12 · BF16 与 BF16x2

状态：`NOT_STARTED`

## 范围

覆盖 BF16/BF16x2 add/sub/mul/fma、min/max 和 unary modifier。

## 优先上下文

- scalar/packed lane、rounding、sat 和 operand modifier；
- F32↔BF16 producer/consumer 与转换折叠；
- accumulation 类型、FMA contraction 和 mixed-precision pattern；
- 特殊浮点 bit pattern 与两个 packed lane 的非对称输入；
- GPR/UR 路由、single-use 和 predicate compatibility。

## 本族完成门槛

BF16 与 F16 的相同表面 pattern 不共享结论；每个候选必须保留自己的精度和允许结果约束。

