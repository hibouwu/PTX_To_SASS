# `brx.idx`

状态：`FRAMEWORK_VALIDATED`（[thor_ptx90/](thor_ptx90/) 套件已通过本机 CUDA 13.0 O0–O3 自检：18 syntax + 25 expanded case、7 个带诊断锚定的负向探针）

负责 indexed indirect branch、跳转表、索引范围和目标布局。
实测映射：O0 恒为 `BRX`（GPR）；O1–O3 索引 warp-uniform 时切换为 `BRXU`（UR），索引
divergent（`%tid`/`%laneid` 派生）时仍为 `BRX`。越界/编译期常量索引无静态边界检查，
仅由 O3 的激进 UB 假设优化处理。`@%p brx.idx` 合法，divergent 谓词下触发
`BSSY.RECONVERGENT`/`BSYNC.RECONVERGENT`，是本族 P0-1 对应物的直接证据。
族级设计与全部实测记录见 [../实验设计.md](../实验设计.md)。
