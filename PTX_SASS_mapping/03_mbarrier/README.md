# 03 · mbarrier

状态：`NOT_STARTED`

## 范围

覆盖 init、arrive、arrive_drop、expect_tx、complete_tx、try/test wait、inval、
连续 phase reuse 和 remote arrive。

## 优先上下文

- shared/cluster 地址来源、对齐和 remote rank；
- arrival count、transaction count、phase/parity 与 token 使用；
- acquire/release/relaxed、CTA/cluster scope；
- predicate、leader/全线程参与、循环等待和分支形态；
- 初始化、发布、消费、复用、关闭的完整生命周期。

## 本族完成门槛

静态 lowering 和协议语义分别记录；未初始化 barrier、错误参与数或非法 phase 的 case
只能作为负向 corpus，不能进入候选实现集合。

