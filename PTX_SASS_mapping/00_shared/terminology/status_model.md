# 状态模型

族或 opcode 使用 `NOT_STARTED`、`DESIGNED`、`GENERATED`、`OBSERVED`、`VALIDATED`、`BLOCKED`。状态描述的是整个冻结实验范围，不等于某个 testcase 的结果。

单个 testcase 使用 `SPEC_ILLEGAL`、`TARGET_UNSUPPORTED`、`COMPILE_REJECTED`、`TARGET_ELIMINATED`、`DESIGN_NOT_REALIZED`、`ATTRIBUTION_UNKNOWN`、`OBSERVED_VARIANT`、`SEMANTIC_PASS`或`SEMANTIC_FAIL`。每个 case 只能有一个最终状态，但可以另外记录各阶段事件。

`COMPILE_REJECTED` 不能自动解释成 `SPEC_ILLEGAL`；`ptxas` 可能因为目标 capability 或工具链限制拒绝规范合法形态。`VALIDATED` 也不能只由全部 case 成功汇编得到，必须满足预注册的停止条件并公开未覆盖空间。
