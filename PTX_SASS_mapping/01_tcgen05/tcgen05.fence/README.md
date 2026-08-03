# `tcgen05.fence`

状态：`NOT_STARTED`

## 研究边界

研究 `tcgen05.fence::before_thread_sync` 与 `tcgen05.fence::after_thread_sync` 的静态 lowering 和运行时排序语义。fence 是 tcgen05 操作跨执行排序点的代码移动边界，不应预设每条 PTX fence 都有一条同名 SASS。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| 方向 | before、after | 两类约束是否具有不同核心或调度表达 |
| 相邻 tcgen05 操作 | MMA、cp、shift、ld/st | 约束覆盖哪些异步操作 |
| 排序点 | barrier、mbarrier、morally strong memory operation | 如何组成跨线程 happens-before |
| 位置 | 紧邻、隔开、跨基本块 | 编译器可移动范围和 effect slice |
| guard/issuer | uniform、divergent、不同线程 | fence 与实际参与线程的匹配条件 |

## 完成门槛

必须同时提供静态 CFG/def-use 证据和实机 litmus test，明确哪些结论是代码生成观察、哪些是内存模型语义；NOP 或 barrier 位置变化不能直接升级为独立 fence opcode 规则。
