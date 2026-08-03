# 01 · tcgen05

状态：`IN_PROGRESS`（`tcgen05.mma` 已有 Thor/PTX 9.0 受约束穷举静态用例，其他 opcode 已建立独立研究入口但尚未开始；旧的 sm_100a 首轮用例已删除）

## 范围

计划覆盖 tcgen05 MMA、稀疏/非稀疏形态、CTA group、TMEM copy/load/store/shift、alloc/dealloc、commit、wait、fence，以及完整参与和完成生命周期。当前只有 `tcgen05.mma` 达到系统实验和规则归纳阶段，其他目录的 `NOT_STARTED` 表示只有范围设计，不能作为已有映射证据。

## 指令目录

| PTX opcode | 状态 | 独立研究重点 |
|---|---|---|
| [`tcgen05.alloc`](tcgen05.alloc/) | `NOT_STARTED` | TMEM 分配、CTA group、结果发布和 warp 参与 |
| [`tcgen05.dealloc`](tcgen05.dealloc/) | `NOT_STARTED` | TMEM 回收、前序异步完成和资源复用 |
| [`tcgen05.relinquish_alloc_permit`](tcgen05.relinquish_alloc_permit/) | `NOT_STARTED` | 分配许可状态和 collective 生命周期 |
| [`tcgen05.cp`](tcgen05.cp/) | `NOT_STARTED` | TMEM copy、shape、地址来源和 commit 完成 |
| [`tcgen05.ld`](tcgen05.ld/) | `NOT_STARTED` | TMEM→寄存器、`LDTM`、布局和 `wait::ld` |
| [`tcgen05.st`](tcgen05.st/) | `NOT_STARTED` | 寄存器→TMEM、`STTM`、布局和 `wait::st` |
| [`tcgen05.wait`](tcgen05.wait/) | `NOT_STARTED` | load/store 同线程异步完成和 anti-dependency |
| [`tcgen05.mma`](tcgen05.mma/) | `IN_PROGRESS` | MMA 核心选择、上下文 lowering、编码与协议见证 |
| [`tcgen05.commit`](tcgen05.commit/) | `NOT_STARTED` | `UTCBAR`、mbarrier arrive、multicast 和 CTA group |
| [`tcgen05.fence`](tcgen05.fence/) | `NOT_STARTED` | before/after thread sync 与跨线程排序 |
| [`tcgen05.shift`](tcgen05.shift/) | `NOT_STARTED` | 独立 TMEM shift、地址区域和完成协议；不与 MMA `.ashift` 混同 |

## 优先上下文

- kind、shape、dtype、sparsity、CTA group 和 accumulator 形态；
- descriptor/tmem address 的来源、编码、寄存器类别与 materialization；
- GPR/UR、P/UP 路由及 producer/consumer guard；
- warp/CTA 参与方式、ELECT、commit/wait/fence 和跨 CTA 协议；
- 结果单次/多次使用、跨同步边界活跃和寄存器压力。

## 本族完成门槛

结构 lowering 与合法生命周期的语义验证分开记账；只有成功汇编不能升级为 `SEMANTIC_PASS`。协议指令必须保留在完整 effect slice 中，再进行 core/preparation 二级标注。

## 当前用例

- [`tcgen05.mma/thor_ptx90/`](tcgen05.mma/thor_ptx90/)：Thor `.version 9.0`/`.target sm_110a` 专用矩阵；语法集为 1,152 个源码实现/896 个 semantic form，扩展集为 9,216 个源码实现/7,168 个 logical design，另有 34 个 `CTX.protocol`、8 个完整 `effect_slice` case；全部通过 CUDA 13.0 `ptxas` 的 O0/O1/O2/O3 汇编，另含 3 个 capability/非法组合预期拒绝探针。
