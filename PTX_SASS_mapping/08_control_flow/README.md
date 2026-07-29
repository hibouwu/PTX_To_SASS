# 08 · 控制流

状态：`NOT_STARTED`

## 范围

覆盖条件/无条件 branch、return、基本块布局，以及与分支直接相关的 predicate 和
特殊寄存器 consumer。特殊寄存器本身的 lowering 归 `09_special_reg`。

## 优先上下文

- predicate 来源、取反、uniform/divergent 和 P/UP 结果；
- fallthrough、目标块布局、汇合、循环和分支距离；
- 跨块 producer/consumer、live range 和 phi-like merge；
- leaf/non-leaf、call/return、内联和 ABI；
- compare-branch folding、code motion 和不可跨越副作用。

## 本族完成门槛

必须区分 PTX 源布局、优化后 CFG 和最终 SASS 布局；源码相邻或距离不能直接当作已实现结果。

