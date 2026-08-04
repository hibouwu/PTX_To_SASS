# `cp.async.bulk.tensor`

状态：`FRAMEWORK_VALIDATED`（[thor_ptx90/](thor_ptx90/) 套件已通过本机 CUDA 13.0 O0–O3 自检：42 syntax + 52 expanded case、12 个带诊断锚定的负向探针）

负责 tensor-map 驱动的 bulk load/store，包括 rank、坐标、multicast 和完成机制。
实测映射 `UTMALDG.{1D..5D}{.GATHER4,.IM2COL,.W,.W128}{.MULTICAST}{.2CTA}` 与
`UTMASTG.{1D..5D}{.SCATTER4,.IM2COL}`；`shared::cta` 与 `shared::cluster` 不进助记符，
`.L2::cache_hint` 表现为额外 `desc[UR]` 操作数。族级设计与校准记录见
[../实验设计.md](../实验设计.md)。
