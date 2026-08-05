# `fence`

状态：`FRAMEWORK_VALIDATED`（[thor_ptx90/](thor_ptx90/) 套件已通过本机 CUDA 13.0 O0–O3 自检：16 syntax + 29 expanded case、9 个带诊断锚定/补集抽样的负向探针）

普通 memory fence；`sem`（`sc`/`acq_rel`/`acquire`/`release`，实测四档而非常见资料强调的两档）与
`scope`（`cta`/`cluster`/`gpu`/`sys`，`cluster`≡`gpu` 逐位坍缩）是主要实验坐标。
实测映射：`sc`/`acq_rel` 展开为 `MEMBAR.{SC,ALL}.<scope>`（+`ERRBAR`+`CGAERRBAR`+`CCTL.IVALL`，scope>cta 时）；
`acquire`/`release` 是可分解出的裸部分，`fence.acquire.cta` 零指令（D 类）；
省略 sem 的 `fence.<scope>;` 合法且默认等价 `acq_rel`（不是更符合直觉的 `sc`）。
`membar` 只作为实测别名出现，规则由 [`../membar/`](../membar/) 独立持有。
族级设计与校准记录见 [../实验设计.md](../实验设计.md)。
