# `tcgen05.fence`

状态：`FRAMEWORK_VALIDATED`（静态实验框架已通过 CUDA 13.0 O0–O3 自检；规则文档待由结果继续归纳）

实验入口：[`thor_ptx90/`](thor_ptx90/)

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

必须提供静态 CFG/def-use、O0–O3 代码移动对照、完整相邻 effect slice 和空 lowering 证据，明确区分代码生成观察与 PTX 规范语义；NOP 或 barrier 位置变化不能直接升级为独立 fence opcode 规则。实机 litmus 不属于完成条件。
