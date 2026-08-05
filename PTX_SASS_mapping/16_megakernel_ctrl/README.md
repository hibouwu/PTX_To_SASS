# 16 · Megakernel control

状态：`IN_PROGRESS`（[实验设计.md](实验设计.md) 已完成全族 7 opcode 的实测校准；`bar.warp.sync` 套件已建成并通过首轮自检：11 syntax + 26 expanded case × O0–O3 共 148 次编译/归属 PASS，7 个带诊断锚定的负向探针全部按预期拒绝）

## 范围

覆盖 warp barrier、nanosleep、grid dependency launch/wait、global prefetch 及长生命周期
kernel 中的控制协议。

## 具体指令目录

- [`bar.warp.sync`](bar.warp.sync/)：`FRAMEWORK_VALIDATED`，套件见 [`bar.warp.sync/thor_ptx90/`](bar.warp.sync/thor_ptx90/)；O0 恒为 `WARPSYNC.COLLECTIVE`+`ENDCOLLECTIVE`，O1–O3 无 guard 时被收敛分析消除为零指令（D′ 类）、带 guard 时存活为 `WARPSYNC.ALL`/`WARPSYNC Rn`
- [`nanosleep`](nanosleep/)：`DESIGNED`，A 类单指令直译（`NANOSLEEP`），校准见实验设计.md
- [`griddepcontrol.launch_dependents`](griddepcontrol.launch_dependents/)：`DESIGNED`，A 类单指令直译
- [`griddepcontrol.wait`](griddepcontrol.wait/)：`DESIGNED`，A 类单指令直译
- [`prefetch.global`](prefetch.global/)：`DESIGNED`，A 类单指令直译（L1/L2/L2::evict_last）
- [`clusterlaunchcontrol.try_cancel`](clusterlaunchcontrol.try_cancel/)：`DESIGNED`，B 类编译器合成协议（锚点 `UGETNEXTWORKID.SELFCAST`），sm_110a 合法
- [`clusterlaunchcontrol.query_cancel`](clusterlaunchcontrol.query_cancel/)：`DESIGNED`，E 类（吸收进通用 ALU，无专属助记符），归属方法论见实验设计.md

## 优先上下文

- predicate、循环、退避次数和分支布局；
- grid dependency producer/consumer 与跨 kernel 关系；
- prefetch 地址、cache level、重复/无用结果；
- barrier 前后副作用、async 操作和 cluster/CTA scope；
- 长 live range、寄存器压力和 call boundary。

## 本族完成门槛

明确区分“指令被执行”“协议完成”和“产生性能收益”；三者不能用同一个 PASS 状态表示。
