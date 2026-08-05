# `mbarrier.arrive`

状态：`FRAMEWORK_VALIDATED`（[thor_ptx90/](thor_ptx90/) 套件已通过本机 CUDA 13.0 O0–O3 自检：15 syntax + 24 expanded case、7 个带诊断锚定的负向探针）

负责普通 arrive、memory order、scope、返回 token 和 remote arrive。
实测映射恒为 `SYNCS.ARRIVE.TRANS64`，靠正交后缀区分角色：`.A1T0`/`.ART0` 由 count
操作数是否显式给出决定，`.TMASK.ART0` 对应 `.noComplete`，`.RED` 对应
`.shared::cluster`（remote）地址；`sem=.release` 与 `scope=.cluster` 同时成立时会在
核心指令前插入固定的 `MEMBAR.ALL.CTA`+`MEMBAR.ALL.GPU`+`ERRBAR`+`CGAERRBAR`
前导序列，`.relaxed` 不触发。族级设计与全部 9 个 opcode 的校准记录见
[../实验设计.md](../实验设计.md)。
