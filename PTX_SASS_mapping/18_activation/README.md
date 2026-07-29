# 18 · Activation

状态：`NOT_STARTED`

## 范围

覆盖 tanh、ex2 等 F16/F16x2/BF16/BF16x2/F32 activation lowering，以及它们与常见
epilogue pattern 的组合。

## 优先上下文

- dtype、scalar/packed、approx、FTZ 和 modifier；
- `±0`、小量、饱和区、Inf、NaN 和边界邻域；
- convert → activation、activation → mul/add、clamp 和 pack；
- single/multi-use、predicate 和 dead-result elimination；
- 精度/吞吐候选、辅助多项式序列和寄存器压力。

## 本族完成门槛

候选只记录 ptxas 已观察 lowering；数值 oracle 必须声明误差度量、输入域和特殊值策略，
不能把观察到的近似序列直接当作可替换规则。

