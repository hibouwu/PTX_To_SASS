# `atom.global`

状态：`FRAMEWORK_VALIDATED`（Thor/PTX 9.0 静态套件见 [thor_ptx90/](thor_ptx90/)：28 syntax + 24 expanded case × O0–O3 共 208 次编译/归属 PASS，11 个带诊断锚定的负向探针（含 3 条补集抽样）全部按预期拒绝；forward rule 96、inverse signature 38）

负责有返回值的 global atomic；operation、dtype、order 和 scope 属于语义形态。

核心实测结论（详见 [../实验设计.md](../实验设计.md)）：`ATOMG.E.<OP>[.STRONG.<SCOPE>]`（scope 映射 无/cluster/gpu→GPU、cta→SM、sys→SYS）；`.release/.acq_rel` 前置 `MEMBAR.ALL.<scope>`，`.relaxed/.acquire` 无额外指令；死结果降级 `REDG`（exch/cas 除外，保留 ATOMG + RZ 目的）；uniform 地址触发 warp 聚合改写；`cas.b16` 合法。
