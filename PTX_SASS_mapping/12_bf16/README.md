# 12 · BF16 与 BF16x2

状态：`IN_PROGRESS`（族级实验设计与 `sm_110a` 助记符/合法面校准完成，见 [实验设计.md](实验设计.md)；全部结论来自独立的 bf16 探针，未引用 `11_half_precision`。`fma` 已建成自包含静态套件并通过本机 CUDA 13.0 O0–O3 自检——8 syntax + 25 expanded case、11 负向探针全 PASS；其余 9 个 opcode 处于 `DESIGNED`）

## 范围

覆盖 BF16/BF16x2 add/sub/mul/fma、min/max 和 unary modifier。

## 具体指令目录

- [`add`](add/)、[`sub`](sub/)、[`mul`](mul/)、[`fma`](fma/)（`FRAMEWORK_VALIDATED`，[套件](fma/thor_ptx90/)）
- [`min`](min/)、[`max`](max/)、[`abs`](abs/)、[`neg`](neg/)
- [`set`](set/)、[`setp`](setp/)

标量与 `x2` packed 形态保存在同一 opcode 目录内；BF16 conversion 归
`06_cuda_core_fp`，activation 归 `18_activation`。

## 优先上下文

- scalar/packed lane、rounding、sat 和 operand modifier；
- F32↔BF16 producer/consumer 与转换折叠；
- accumulation 类型、FMA contraction 和 mixed-precision pattern；
- 特殊浮点 bit pattern 与两个 packed lane 的非对称输入；
- GPR/UR 路由、single-use 和 predicate compatibility。

## 本族完成门槛

BF16 与 F16 的相同表面 pattern 不共享结论；每个候选必须保留自己的精度和允许结果约束。
