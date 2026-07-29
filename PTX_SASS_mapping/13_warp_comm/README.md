# 13 · Warp communication

状态：`NOT_STARTED`

## 范围

覆盖 shuffle、redux、vote、match 和 elect。

## 优先上下文

- active mask、lane source、clamp、width 和 member mask；
- 完整/部分 warp、收敛/发散控制流和 predicate；
- uniform/varying 输入输出与 GPR/UR、P/UP 路由；
- collective 结果作为 arithmetic、branch、address 或另一个 collective 的输入；
- 连续 collective、同步边界和跨块使用。

## 本族完成门槛

所有 runtime case 必须定义参与线程集合和收敛前提；违反 collective 前提的 case 单独作为负向测试。

