# 07 · LSU

状态：`NOT_STARTED`

## 范围

覆盖 global/shared/local/const/param 的标量与向量 load/store，以及 cache、
eviction、volatile、order 和 scope modifier。

## 优先上下文

- 命名符号、立即地址、寄存器地址和寄存器加偏移；
- 正负偏移、缩放、编码边界、对齐和访问宽度；
- generic 与明确 state space、地址转换和 provenance；
- 不别名、可能别名、同址、部分重叠和宽度差异；
- address-add folding、load-arithmetic、arithmetic-store 和 memory order。

## 高风险簇

`state-space × width × alignment × alias × order × scope` 使用受约束组合覆盖；
非法或语义未定义的访问单独记账。

