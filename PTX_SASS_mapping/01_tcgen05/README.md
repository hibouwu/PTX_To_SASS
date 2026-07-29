# 01 · tcgen05

状态：`NOT_STARTED`

## 范围

覆盖 tcgen05 MMA、稀疏/非稀疏形态、CTA group、TMEM copy/load/store、
alloc/dealloc、commit、fence，以及完整参与和完成生命周期。

## 优先上下文

- kind、shape、dtype、sparsity、CTA group 和 accumulator 形态；
- descriptor/tmem address 的来源、编码、寄存器类别与 materialization；
- GPR/UR、P/UP 路由及 producer/consumer guard；
- warp/CTA 参与方式、ELECT、commit/wait/fence 和跨 CTA 协议；
- 结果单次/多次使用、跨同步边界活跃和寄存器压力。

## 本族完成门槛

结构 lowering 与合法生命周期的语义验证分开记账；只有成功汇编不能升级为
`SEMANTIC_PASS`。协议指令必须保留在完整 effect slice 中，再进行 core/preparation
二级标注。

