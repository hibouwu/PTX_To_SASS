# 01 · tcgen05

状态：`IN_PROGRESS`（`tcgen05.mma` 已有完整规则研究；其余 10 个 opcode 已建立并通过 Thor/PTX 9.0 静态实验框架的本机 CUDA 13.0 O0–O3 自检，但尚未形成与 MMA 同等深度的人类规则文档）

## 范围

计划覆盖 tcgen05 MMA、稀疏/非稀疏形态、CTA group、TMEM copy/load/store/shift、alloc/dealloc、commit、wait、fence，以及完整参与和完成生命周期。当前 `tcgen05.mma` 已达到系统规则归纳阶段；其余指令分别拥有自包含的 syntax/expanded 生成、O0–O3 编译反汇编、专用归属、规则候选与阴性边界流水线。各目录借鉴相同的实验分层，但不依赖跨指令共享脚本。

## 指令目录

| PTX opcode | 状态 | 独立研究重点 |
|---|---|---|
| [`tcgen05.alloc`](tcgen05.alloc/) | `FRAMEWORK_VALIDATED` | TMEM 分配、CTA group、结果发布和 warp 参与 |
| [`tcgen05.dealloc`](tcgen05.dealloc/) | `FRAMEWORK_VALIDATED` | TMEM 回收、前序异步完成和资源复用 |
| [`tcgen05.relinquish_alloc_permit`](tcgen05.relinquish_alloc_permit/) | `FRAMEWORK_VALIDATED` | 分配许可状态和 collective 生命周期 |
| [`tcgen05.cp`](tcgen05.cp/) | `FRAMEWORK_VALIDATED` | TMEM copy、shape、地址来源和 commit 完成 |
| [`tcgen05.ld`](tcgen05.ld/) | `FRAMEWORK_VALIDATED` | TMEM→寄存器、`LDTM`、布局和 `wait::ld` |
| [`tcgen05.st`](tcgen05.st/) | `FRAMEWORK_VALIDATED` | 寄存器→TMEM、`STTM`、布局和 `wait::st` |
| [`tcgen05.wait`](tcgen05.wait/) | `FRAMEWORK_VALIDATED` | load/store 同线程异步完成和 anti-dependency |
| [`tcgen05.mma`](tcgen05.mma/) | `IN_PROGRESS` | MMA 核心选择、上下文 lowering、编码与协议见证 |
| [`tcgen05.commit`](tcgen05.commit/) | `FRAMEWORK_VALIDATED` | `UTCBAR`、mbarrier arrive、multicast 和 CTA group |
| [`tcgen05.fence`](tcgen05.fence/) | `FRAMEWORK_VALIDATED` | before/after thread sync 与跨线程排序 |
| [`tcgen05.shift`](tcgen05.shift/) | `FRAMEWORK_VALIDATED` | 独立 TMEM shift、地址区域和完成协议；不与 MMA `.ashift` 混同 |

## 优先上下文

- kind、shape、dtype、sparsity、CTA group 和 accumulator 形态；
- descriptor/tmem address 的来源、编码、寄存器类别与 materialization；
- GPR/UR、P/UP 路由及 producer/consumer guard；
- warp/CTA 参与方式、ELECT、commit/wait/fence 和跨 CTA 协议；
- 结果单次/多次使用、跨同步边界活跃和寄存器压力。

## 本族完成门槛

结构 lowering、静态合法性和规范语义必须分层记账；只有成功汇编不能升级为运行时语义结论。协议指令必须保留在完整 effect slice 中，再进行 core/preparation 二级标注。本项目当前的完成状态只覆盖静态 PTX→SASS 映射，不设置运行时 `SEMANTIC_PASS` 门槛。

## 当前用例

- [`tcgen05.mma/thor_ptx90/`](tcgen05.mma/thor_ptx90/)：Thor `.version 9.0`/`.target sm_110a` 专用矩阵；语法集为 1,152 个源码实现/896 个 semantic form，扩展集为 9,216 个源码实现/7,168 个 logical design，另有 34 个 `CTX.protocol`、8 个完整 `effect_slice` case；全部通过 CUDA 13.0 `ptxas` 的 O0/O1/O2/O3 汇编，另含 3 个 capability/非法组合预期拒绝探针。
- 其余 10 个 `thor_ptx90/` 静态套件：syntax 共 162 个 case、expanded 共 202 个 case；CUDA 13.0 下 O0–O3 共 1,456 次编译与反汇编全部通过，16 个预期拒绝探针全部通过。该结果验证实验框架，不替代后续的人类规则归纳和运行时语义研究。
