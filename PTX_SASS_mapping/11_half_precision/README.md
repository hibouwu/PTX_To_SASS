# 11 · F16 与 F16x2

状态：`NOT_STARTED`

## 范围

覆盖 F16/F16x2 add/sub/mul/fma、min/max、neg/abs 和 compare。

## 具体指令目录

- [`add`](add/)、[`sub`](sub/)、[`mul`](mul/)、[`fma`](fma/)
- [`min`](min/)、[`max`](max/)、[`abs`](abs/)、[`neg`](neg/)
- [`set`](set/)、[`setp`](setp/)

标量与 `x2` packed 形态保存在同一 opcode 目录内；低精度 activation 归
`18_activation`。

## 优先上下文

- scalar/packed 形态、lane 复制/交换和 half selector；
- rounding、FTZ、sat、neg/abs modifier 和 predicate；
- pack/unpack producer、F32 conversion consumer 和 FMA contraction；
- `±0`、subnormal 边界、Inf、NaN bit pattern；
- 单次/多次使用、寄存器复用和 packed operand source slot。

## 本族完成门槛

packed 两个 lane 的输入和 oracle 独立变化，避免只测试两个 lane 相同的退化情况。
