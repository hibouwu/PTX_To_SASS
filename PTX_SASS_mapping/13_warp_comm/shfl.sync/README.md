# `shfl.sync`

状态：`FRAMEWORK_VALIDATED`（Thor/PTX 9.0 静态套件见 [thor_ptx90/](thor_ptx90/)：34 syntax + 46 expanded case × O0–O3 共 320 次编译/归属 PASS，6 个带诊断锚定的负向探针全部按预期拒绝；forward rule 184、inverse signature 62）

负责 bfly/up/down/idx shuffle、member mask、lane source、clamp 和 width。

核心实测结论（详见 [../实验设计.md](../实验设计.md)）：`shfl.sync.<mode>.b32` → `SHFL.{UP,DOWN,BFLY,IDX} {Pd|PT}, Rd, Ra, b, c`；membermask 从不作为 SHFL 操作数，只决定前置 `WARPSYNC` 的有无与形态（收敛点 + 立即数/uniform mask 省略；非 uniform 运行时 mask → `WARPSYNC Rn`；发散后满掩码 → `WARPSYNC.ALL`）；`a` 可证明 uniform 时 SHFL 整条消除（`empty_target_allowed` 坐标）；可证明常量的寄存器 b/c 仍折叠回立即数字段。
