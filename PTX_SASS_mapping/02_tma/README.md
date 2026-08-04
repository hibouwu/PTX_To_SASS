# 02 · TMA 与异步搬运

状态：`IN_PROGRESS`（族级实验设计与 `sm_110a` 助记符/合法面校准完成，见 [实验设计.md](实验设计.md)；`cp.async` 与 `cp.async.bulk.tensor` 已建成自包含静态套件并通过本机 CUDA 13.0 O0–O3 自检，其余 9 个 opcode 处于 `DESIGNED`）

## 范围

覆盖 tensor bulk load/store/reduce/prefetch、multicast、classic `cp.async`、
bulk group、commit 和 wait。

## 具体指令目录

- [`cp.async`](cp.async/)：经典 global→shared 异步拷贝（`FRAMEWORK_VALIDATED`，[套件](cp.async/thor_ptx90/)）；
- [`cp.async.commit_group`](cp.async.commit_group/) 与
  [`cp.async.wait_group`](cp.async.wait_group/)：经典 async group；
- [`cp.async.bulk`](cp.async.bulk/) 与
  [`cp.reduce.async.bulk`](cp.reduce.async.bulk/)：非 tensor bulk copy/reduce；
- [`cp.async.bulk.tensor`](cp.async.bulk.tensor/) 与
  [`cp.reduce.async.bulk.tensor`](cp.reduce.async.bulk.tensor/)：tensor-map copy/reduce（前者 `FRAMEWORK_VALIDATED`，[套件](cp.async.bulk.tensor/thor_ptx90/)）；
- [`cp.async.bulk.prefetch.tensor`](cp.async.bulk.prefetch.tensor/)：tensor-map 预取；
- [`cp.async.bulk.commit_group`](cp.async.bulk.commit_group/) 与
  [`cp.async.bulk.wait_group`](cp.async.bulk.wait_group/)：bulk group 完成协议。

## 优先上下文

- tensor rank、tile shape、element type、坐标和 tensor map 来源；
- global/shared 地址、对齐、swizzle、stride、multicast mask；
- mbarrier completion、transaction bytes、commit/wait group；
- async/tensormap proxy fence、scope、predicate 和 leader 选择；
- producer/consumer 距离、跨基本块关系和相邻访存别名。

## 族级设计

[实验设计.md](实验设计.md) 记录：11 个 opcode 的结构分类（全部为 A 单指令直译或 C 完成节点，无 tcgen05 式 B/D 类）、`sm_110a` 实测助记符总表（`UTMALDG`/`UTMASTG`/`UTMAREDG`/`UTMAPF`/`UBLKCP`/`UBLKRED`/`UBLKPF`/`LDGSTS`/`LDGDEPBAR`/`UTMACMDFLUSH`/`DEPBAR`）、已校准合法面、对 tcgen05 对抗式审查 P0/P1 缺口的对应设计，以及余下套件的建设路线。

## 跨族依赖

组合协议可依赖 `03_mbarrier`、`04_fence` 和 `15_cluster_dsmem`，但 testcase 和结论由
本目录独立持有。mbarrier init 的 `SYNCS.EXCH.64` lowering 出现在本族 load case 的
PREPARATION 区，规则归 `03_mbarrier` 持有。
