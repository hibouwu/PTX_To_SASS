# `bar.warp.sync`

状态：`FRAMEWORK_VALIDATED`（Thor/PTX 9.0 静态套件见 [thor_ptx90/](thor_ptx90/)：11 syntax + 26 expanded case × O0–O3 共 148 次编译/归属 PASS，7 个带诊断锚定的负向探针全部按预期拒绝；forward rule 104、inverse signature 16）

负责 warp barrier、member mask、收敛前提和前后副作用。

核心实测结论（详见 [../实验设计.md](../实验设计.md)）：本指令是 D′/A 双形态——O0 恒为 `WARPSYNC.COLLECTIVE`+`ENDCOLLECTIVE`；O1–O3 无 guard 时在全部已测上下文中被 ptxas 的 `BSSY`/`BSYNC` 收敛分析证明冗余而消除为零指令，带 `@%p` guard 时存活（满掩码立即数 → `WARPSYNC.ALL`，部分/寄存器掩码 → `WARPSYNC Rn`）。
