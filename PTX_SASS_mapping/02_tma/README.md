# 02 · TMA 与异步搬运

状态：`NOT_STARTED`

## 范围

覆盖 tensor bulk load/store/reduce/prefetch、multicast、classic `cp.async`、
bulk group、commit 和 wait。

## 优先上下文

- tensor rank、tile shape、element type、坐标和 tensor map 来源；
- global/shared 地址、对齐、swizzle、stride、multicast mask；
- mbarrier completion、transaction bytes、commit/wait group；
- async/tensormap proxy fence、scope、predicate 和 leader 选择；
- producer/consumer 距离、跨基本块关系和相邻访存别名。

## 跨族依赖

组合协议可依赖 `03_mbarrier`、`04_fence` 和 `15_cluster_dsmem`，但 testcase 和结论由
本目录独立持有。

