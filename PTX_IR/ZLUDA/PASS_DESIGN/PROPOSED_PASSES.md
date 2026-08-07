# 建议新增的窄职责 Pass

这些 Pass 尚未出现在当前 `to_llvm_module()` 中。本页把建议与现状分开，避免总览把设计草案误写成已实现行为。

## `validate_target_features`

推荐位置：标识符规范化后、任何可能丢失原始 modifier/target 信息的变换前。

输入契约：完整保存 PTX version、SM 数字、`a/f` 后缀和 address size 的 module descriptor。

职责：检查 opcode、shape、type、scope、立即数 flag 与目标能力的组合；拒绝 backend 不认识的 processor；不改写指令顺序。

输出不变量：后续 Pass 可以假设所有指令在声明 target 上语法和 feature 合法。它不能证明运行时同步协议正确。

## `validate_and_materialize_tcgen05_async`

推荐位置：`instruction_mode_to_global_mode` 后、`insert_explicit_load_store` 前。

输入契约：CFG 已规范化；tcgen05.ld tuple 已由 Pass 7 表示成 non-emitting pending-unpack marker，而不是普通 `RepackVector`。

职责：验证 pending register 在 wait 前不可读取/重定义；在 `wait::ld` 后物化 `RepackVector`；检查直线版或 CFG 版协议状态；输出不得残留 marker。

输出不变量：Pass 15 只处理 ready 的普通 destination，不需要保存 tcgen05 专用状态。

## 对抗式结论

- 把 target 检查混入异步 Pass，会让“单条指令非法”和“跨指令协议非法”难以区分，因此拒绝合并。
- 把 pending 状态放进 Pass 15 太晚：Pass 7 已经可能通过 `RepackVector` 消费结果，因此拒绝该方案。
- 把机器调度放进前端无法证明最终 SASS 控制位，且复制 LLVM/ptxas 职责，因此拒绝该方案。
