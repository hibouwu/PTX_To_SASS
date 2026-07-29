# 06 · CUDA Core 浮点与转换

状态：`NOT_STARTED`

## 范围

覆盖 F32/F64 add/mul/fma、min/max、abs/neg、ex2/lg2/rcp/rsqrt/sqrt，以及整数、
F16、BF16 与 F32/F64 之间的转换。

## 优先上下文

- rounding、FTZ、approx、sat 和 modifier 组合；
- `±0`、normal/subnormal 边界、`±Inf`、多个 NaN bit pattern；
- producer/consumer 转换折叠、FMA contraction 和 neg/abs folding；
- 源槽立即数能力、constant materialization 和寄存器类别；
- packed conversion、宽位结果和 O0/O3 的存活差异。

## 本族完成门槛

浮点 oracle 必须按指令语义区分 bit-exact、允许结果集合和误差界，不能统一使用一种比较。

