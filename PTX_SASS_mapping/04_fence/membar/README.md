# `membar`

状态：`FRAMEWORK_VALIDATED`（[thor_ptx90/](thor_ptx90/) 套件已通过本机 CUDA 13.0 O0–O3 自检：3 syntax + 11 expanded case、6 个带诊断锚定/补集抽样的负向探针）

传统 `membar.cta/gl/sys`（**不是** `.gpu`——`gpu` 是新式 `fence` 独有的拼写，`membar.gpu`
语法拒绝，已实测校准）。三档 level 已证是 [`../fence/`](../fence/) 的 `fence.sc.{cta,gpu,sys}` 的
严格子集，逐位相同：`membar.cta`≡`fence.sc.cta`（`MEMBAR.SC.CTA`），`membar.gl`≡`fence.sc.gpu`≡
`fence.sc.cluster`，`membar.sys`≡`fence.sc.sys`（均为 `MEMBAR.SC.*`+`ERRBAR`+`CGAERRBAR`+`CCTL.IVALL`）。
族级设计与校准记录见 [../实验设计.md](../实验设计.md)。
