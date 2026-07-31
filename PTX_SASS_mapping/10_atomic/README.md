# 10 · Atomic 与 reduction

状态：`NOT_STARTED`

## 范围

覆盖 global/shared atomic、reduction、常见算术/CAS 操作和不同位宽。

## 具体指令目录

- [`atom.global`](atom.global/)
- [`atom.shared`](atom.shared/)
- [`red.global`](red.global/)
- [`red.shared`](red.shared/)

add/min/max/inc/dec/cas/exch/and/or/xor 等 operation 作为各目录内的 `SF`，不重复建目录。

## 优先上下文

- operation、dtype、width、state space、memory order 和 scope；
- 返回值 dead/single/multi-use，以及 `atom` 与 `red` 选择；
- 地址对齐、别名、相邻普通访问和 fence；
- compare-exchange 结果拆分、predicate consumer 和 branch；
- 低/高 contention 语义、跨 CTA/cluster 参与范围。

## 本族完成门槛

静态 opcode 候选之外，memory-order 与原子性结论必须由并发 litmus 的允许结果集合验证。
