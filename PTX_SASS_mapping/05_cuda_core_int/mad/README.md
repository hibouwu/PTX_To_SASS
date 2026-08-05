# `mad`

状态：`FRAMEWORK_VALIDATED`（Thor/PTX 9.0 静态套件见 [thor_ptx90/](thor_ptx90/)：35 syntax + 43 expanded case × O0–O3 共 312 次编译/归属 PASS，9 个带诊断锚定的负向探针（含 2 条补集抽样）全部按预期拒绝；forward rule 172、inverse signature 57）

负责整数 `mad.lo/hi/wide`、sat、源槽和乘加融合。

核心实测结论（详见 [../实验设计.md](../实验设计.md)）：`mad.lo` → `IMAD`；`mad.hi.{s32,u32}` 非 sat 形态 → 单条 `IMAD.HI[.U32]` 且第三槽为物化零（c 不参与累加，套件内用 `hi_accumulate_anchor` case 复现）；`mad.hi.sat.s32` → 6 条钳位序列（c 正确折入）；16-bit `mad.hi` → `IMAD`+`LEA.HI`；`mad.wide.{s32,u32}` → `IMAD.WIDE[.U32]`+进位加法对；`.sat` 合法面仅 `mad.hi.sat.s32` 一点；乘数槽 0/±1 立即数触发代数折叠（`empty_target_allowed` 坐标类）。
