# 16 · Megakernel control

状态：`NOT_STARTED`

## 范围

覆盖 warp barrier、nanosleep、grid dependency launch/wait、global prefetch 及长生命周期
kernel 中的控制协议。

## 具体指令目录

- [`bar.warp.sync`](bar.warp.sync/)
- [`nanosleep`](nanosleep/)
- [`griddepcontrol.launch_dependents`](griddepcontrol.launch_dependents/)
- [`griddepcontrol.wait`](griddepcontrol.wait/)
- [`prefetch.global`](prefetch.global/)
- [`clusterlaunchcontrol.try_cancel`](clusterlaunchcontrol.try_cancel/)
- [`clusterlaunchcontrol.query_cancel`](clusterlaunchcontrol.query_cancel/)

## 优先上下文

- predicate、循环、退避次数和分支布局；
- grid dependency producer/consumer 与跨 kernel 关系；
- prefetch 地址、cache level、重复/无用结果；
- barrier 前后副作用、async 操作和 cluster/CTA scope；
- 长 live range、寄存器压力和 call boundary。

## 本族完成门槛

明确区分“指令被执行”“协议完成”和“产生性能收益”；三者不能用同一个 PASS 状态表示。
