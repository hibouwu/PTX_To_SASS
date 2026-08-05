# 10 · Atomic 与 reduction

状态：`IN_PROGRESS`（[实验设计.md](实验设计.md) 已完成 op × type 合法面全枚举（28 组合）与三条改写规则的正反对照校准；`atom.global` 套件已建成并通过首轮自检：28 syntax + 24 expanded case × O0–O3 共 208 次编译/归属 PASS，11 个带诊断锚定的负向探针全部按预期拒绝。关键发现：死结果 `ATOMG`→`REDG` 静默降级且与显式 `red` 逐字节相同、uniform 地址触发 VOTEU/POPC/SHFL warp 聚合改写、标量 f16 add 经 CAS 合成）

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
