# 04 · Fence 与 barrier

状态：`IN_PROGRESS`（族级实验设计与 `sm_110a` 助记符/合法面校准完成，见 [实验设计.md](实验设计.md)；`fence` 与 `membar` 已建成自包含静态套件并通过本机 CUDA 13.0 O0–O3 自检，其余 8 个 opcode 处于 `DESIGNED`）

## 范围

覆盖 proxy async/tensormap fence、mbarrier init fence、memory fence、
cluster barrier、`bar.arrive` 和 `bar.sync`。

## 具体指令目录

- [`fence`](fence/)：`FRAMEWORK_VALIDATED`，[套件](fence/thor_ptx90/) — 与 [`membar`](membar/)（`FRAMEWORK_VALIDATED`，[套件](membar/thor_ptx90/)）互为实测别名（`membar.{cta,gl,sys}` 逐位等于 `fence.sc.{cta,gpu,sys}`）；
- [`fence.proxy.async`](fence.proxy.async/)：async proxy fence，裸形态≡`.shared::cluster`；
- [`fence.proxy.tensormap`](fence.proxy.tensormap/)：tensormap proxy 的 acquire/release，release 侧 cta/cluster/gpu 三档坍缩、acquire 侧四档全部坍缩（scope 不进编码）；
- [`fence.proxy.alias`](fence.proxy.alias/)：唯一形态，lowering 为运行时构型条件分支（常量库谓词 + `MEMBAR.SC.GPU`/`MEMBAR.SC.SYS` 二选一）；
- [`fence.mbarrier_init`](fence.mbarrier_init/)：唯一合法拼写 `.release.cluster`，零指令 lowering；
- [`barrier.cluster.arrive`](barrier.cluster.arrive/) 与 [`barrier.cluster.wait`](barrier.cluster.wait/)：split-phase cluster barrier，同为运行时构型条件分支；`wait` 假分支退化为 `BAR.SYNC.DEFER_BLOCKING 0x0`，与 [`bar.sync`](bar.sync/) 的 `bar.sync 0` 逐位相同；
- [`bar.arrive`](bar.arrive/)：CTA split-phase barrier 的到达半阶段，必须双操作数；
- [`bar.sync`](bar.sync/)：CTA barrier 同步，寄存器双操作数会先打包再进 `BAR.SYNC.DEFER_BLOCKING`。

## 优先上下文

- memory order、thread scope、proxy kind 和 state space；
- 前后 load/store/atomic/async 操作及别名关系；
- 相同或不同 predicate、分支和循环边界；
- barrier id、参与 count、cluster/CTA 布局；
- 可删除、可合并、可移动和不可跨越边界的对照。

## 族级设计

[实验设计.md](实验设计.md) 记录：10 个 opcode 的结构分类（一对多固定序列是本族常态；`fence.acquire.cta`/`fence.mbarrier_init` 属 tcgen05 式 D 类零指令；`fence.proxy.alias`/`barrier.cluster.arrive`/`barrier.cluster.wait` 属本族新增的 R 类——编译器插入运行时构型条件分支，两条候选序列都要归属）、`sm_110a` 实测助记符总表（`MEMBAR.{SC,ALL}.{CTA,GPU,SYS}`/`ERRBAR`/`CGAERRBAR`/`CCTL.IVALL`/`FENCE.VIEW.ASYNC.{S,G}`/`UTMACCTL.IV`/`UCGABAR_ARV`/`UCGABAR_WAIT`/`BAR.SYNC.DEFER_BLOCKING`/`BAR.ARV`）、已校准合法面（含三条推翻常见假设的发现：`fence` 实际接受四个 sem 而非两个、省略 sem 默认是 `acq_rel` 而非 `sc`、`fence.sc.cta` 单独合法）、对 tcgen05 对抗式审查 P0/P1 缺口的对应设计，以及余下 8 个 opcode 的建设路线。

## 本族完成门槛

编译差分只产生候选约束；涉及可见性和顺序的结论必须关联 litmus 或其他允许结果 oracle。litmus（或其他运行时 oracle）目前不在项目工具链范围内，是本族当前全部产物（含两个 `FRAMEWORK_VALIDATED` 套件）的显式边界外事项；`FRAMEWORK_VALIDATED` 只代表静态编译差分闭环，不满足把族状态推进到本条门槛所要求的 `VALIDATED`。
