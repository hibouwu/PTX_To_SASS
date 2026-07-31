# 01 · tcgen05

状态：`IN_PROGRESS`（当前只维护 Thor/PTX 9.0 受约束穷举静态用例；
旧的 sm_100a 首轮用例已删除）

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

## 当前用例

- [`tcgen05.mma/thor_ptx90/`](tcgen05.mma/thor_ptx90/)：Thor
  `.version 9.0`/`.target sm_110a` 专用矩阵；语法集为 1,152 个源码实现/
  896 个 semantic form，扩展集为 9,216 个源码实现/7,168 个 logical design，
  另有 34 个 `CTX.protocol`、8 个完整 `effect_slice` case；全部通过 CUDA
  13.0 `ptxas` 的 O0/O1/O2/O3 汇编，另含 3 个 capability/非法组合预期拒绝
  探针。
