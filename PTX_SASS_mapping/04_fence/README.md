# 04 · Fence 与 barrier

状态：`NOT_STARTED`

## 范围

覆盖 proxy async/tensormap fence、mbarrier init fence、memory fence、
cluster barrier、`bar.arrive` 和 `bar.sync`。

## 具体指令目录

- [`fence`](fence/) 与 [`membar`](membar/)
- [`fence.proxy.async`](fence.proxy.async/)
- [`fence.proxy.tensormap`](fence.proxy.tensormap/)
- [`fence.proxy.alias`](fence.proxy.alias/)
- [`fence.mbarrier_init`](fence.mbarrier_init/)
- [`barrier.cluster.arrive`](barrier.cluster.arrive/)
- [`barrier.cluster.wait`](barrier.cluster.wait/)
- [`bar.arrive`](bar.arrive/)
- [`bar.sync`](bar.sync/)

## 优先上下文

- memory order、thread scope、proxy kind 和 state space；
- 前后 load/store/atomic/async 操作及别名关系；
- 相同或不同 predicate、分支和循环边界；
- barrier id、参与 count、cluster/CTA 布局；
- 可删除、可合并、可移动和不可跨越边界的对照。

## 本族完成门槛

编译差分只产生候选约束；涉及可见性和顺序的结论必须关联 litmus 或其他允许结果 oracle。
