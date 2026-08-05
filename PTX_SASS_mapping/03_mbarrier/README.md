# 03 · mbarrier

状态：`IN_PROGRESS`（族级实验设计与 `sm_110a` 助记符/合法面校准完成，见 [实验设计.md](实验设计.md)；`mbarrier.arrive` 已建成自包含静态套件并通过本机 CUDA 13.0 O0–O3 自检，其余 8 个 opcode 处于 `DESIGNED`）

## 范围

覆盖 init、arrive、arrive_drop、expect_tx、complete_tx、try/test wait、inval、
连续 phase reuse 和 remote arrive。

## 具体指令目录

- [`mbarrier.init`](mbarrier.init/)
- [`mbarrier.arrive`](mbarrier.arrive/)：`FRAMEWORK_VALIDATED`，[套件](mbarrier.arrive/thor_ptx90/)；
- [`mbarrier.arrive.expect_tx`](mbarrier.arrive.expect_tx/)
- [`mbarrier.arrive_drop`](mbarrier.arrive_drop/)
- [`mbarrier.expect_tx`](mbarrier.expect_tx/)
- [`mbarrier.complete_tx`](mbarrier.complete_tx/)
- [`mbarrier.test_wait`](mbarrier.test_wait/)
- [`mbarrier.try_wait`](mbarrier.try_wait/)
- [`mbarrier.inval`](mbarrier.inval/)

## 族级设计

[实验设计.md](实验设计.md) 记录：9 个 opcode 的结构分类（全部为 A 单指令直译，含两处类内变体——`arrive`/`arrive_drop` 的 `sem × scope` 决定指令组大小 1→5，`try_wait` 的 `suspendTimeHint` 操作数触发编译器合成的单次重试）、`sm_110a` 实测助记符总表（`SYNCS.EXCH.64`/`SYNCS.ARRIVE.TRANS64`/`SYNCS.PHASECHK.TRANS64`/`SYNCS.CCTL.IV`）、已校准合法面（含 3 处"预期非法却接受"的 P0-2 发现）、对 tcgen05 对抗式审查 P0/P1 缺口的对应设计，以及余下套件的建设路线。

## 优先上下文

- shared/cluster 地址来源、对齐和 remote rank；
- arrival count、transaction count、phase/parity 与 token 使用；
- acquire/release/relaxed、CTA/cluster scope；
- predicate、leader/全线程参与、循环等待和分支形态；
- 初始化、发布、消费、复用、关闭的完整生命周期。

## 本族完成门槛

静态 lowering 和协议语义分别记录；未初始化 barrier、错误参与数或非法 phase 的 case
只能作为负向 corpus，不能进入候选实现集合。
