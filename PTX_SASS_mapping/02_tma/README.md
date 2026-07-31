# 02 · TMA 与异步搬运

状态：`NOT_STARTED`

## 范围

覆盖 tensor bulk load/store/reduce/prefetch、multicast、classic `cp.async`、
bulk group、commit 和 wait。

## 具体指令目录

- [`cp.async`](cp.async/)：经典 global→shared 异步拷贝；
- [`cp.async.commit_group`](cp.async.commit_group/) 与
  [`cp.async.wait_group`](cp.async.wait_group/)：经典 async group；
- [`cp.async.bulk`](cp.async.bulk/) 与
  [`cp.reduce.async.bulk`](cp.reduce.async.bulk/)：非 tensor bulk copy/reduce；
- [`cp.async.bulk.tensor`](cp.async.bulk.tensor/) 与
  [`cp.reduce.async.bulk.tensor`](cp.reduce.async.bulk.tensor/)：tensor-map copy/reduce；
- [`cp.async.bulk.prefetch.tensor`](cp.async.bulk.prefetch.tensor/)：tensor-map 预取；
- [`cp.async.bulk.commit_group`](cp.async.bulk.commit_group/) 与
  [`cp.async.bulk.wait_group`](cp.async.bulk.wait_group/)：bulk group 完成协议。

## 优先上下文

- tensor rank、tile shape、element type、坐标和 tensor map 来源；
- global/shared 地址、对齐、swizzle、stride、multicast mask；
- mbarrier completion、transaction bytes、commit/wait group；
- async/tensormap proxy fence、scope、predicate 和 leader 选择；
- producer/consumer 距离、跨基本块关系和相邻访存别名。

## 跨族依赖

组合协议可依赖 `03_mbarrier`、`04_fence` 和 `15_cluster_dsmem`，但 testcase 和结论由
本目录独立持有。
