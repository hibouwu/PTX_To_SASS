# `cp.async`

状态：`FRAMEWORK_VALIDATED`（[thor_ptx90/](thor_ptx90/) 套件已通过本机 CUDA 13.0 O0–O3 自检：18 syntax + 27 expanded case、7 个带诊断锚定的负向探针）

经典 global→shared 异步拷贝；cache operator、字节数和 zero-fill 属于本目录内的语义形态。
实测映射 `LDGSTS.E{.64,.128}{.BYPASS}{.ZFILL}{.LTC64B/.LTC128B/.LTC256B}`；
`cp.async.commit_group`/`cp.async.wait_group` 只作为 observation 上下文出现，
规则由各自目录持有。族级设计与校准记录见 [../实验设计.md](../实验设计.md)。
