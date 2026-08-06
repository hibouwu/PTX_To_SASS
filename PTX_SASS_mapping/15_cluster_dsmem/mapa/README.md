# `mapa`

状态：`FRAMEWORK_VALIDATED`（Thor/PTX 9.0 静态套件见 [thor_ptx90/](thor_ptx90/)：10 syntax + 24 expanded case × O0–O3 共 136 次编译/归属 PASS，8 个带诊断锚定的负向探针全部按预期拒绝；forward rule 96、inverse signature 25）

负责 shared::cluster 地址映射、remote rank、地址位宽和 producer。

核心实测结论（详见 [../实验设计.md](../实验设计.md)）：本目标无 MAPA 指令，`mapa.shared::cluster.{u32,u64}` 合成为 `S2R SR_CgaCtaId`+`LEA`+`PRMT`（rank 字节嫁接）；`PRMT` 是唯一无污染归属锚点（`S2R SR_CgaCtaId` 在 `.reqnctapercluster` 下的任何 shared 地址计算中都会出现）；rank 操作数恒为 `.u32`；`.reqnctapercluster`、rank 越界、地址 provenance 均不静态检查（正向 discovery 记账）。
