# 13 · Warp communication

状态：`IN_PROGRESS`（[实验设计.md](实验设计.md) 已完成全 6 opcode 的实测校准；`shfl.sync` 套件已建成并通过首轮自检：34 syntax + 46 expanded case × O0–O3 共 320 次编译/归属 PASS，6 个带诊断锚定的负向探针全部按预期拒绝。关键发现：membermask 不是 SHFL 操作数而是 WARPSYNC 发射决策的输入；uniform 源的 SHFL 被整条消除；redux/elect 结果路由进 UR 文件；activemask 无专用指令 = `VOTE.ANY PT` 形态）

## 范围

覆盖 shuffle、redux、vote、match 和 elect。

## 具体指令目录

- [`shfl.sync`](shfl.sync/)
- [`vote.sync`](vote.sync/)
- [`match.sync`](match.sync/)
- [`redux.sync`](redux.sync/)
- [`elect.sync`](elect.sync/)
- [`activemask`](activemask/)

## 优先上下文

- active mask、lane source、clamp、width 和 member mask；
- 完整/部分 warp、收敛/发散控制流和 predicate；
- uniform/varying 输入输出与 GPR/UR、P/UP 路由；
- collective 结果作为 arithmetic、branch、address 或另一个 collective 的输入；
- 连续 collective、同步边界和跨块使用。

## 本族完成门槛

所有 runtime case 必须定义参与线程集合和收敛前提；违反 collective 前提的 case 单独作为负向测试。
