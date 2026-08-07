# Pass 14：`instruction_mode_to_global_mode`

源码：[`../ptx/src/pass/instruction_mode_to_global_mode/mod.rs`](../ptx/src/pass/instruction_mode_to_global_mode/mod.rs)

## 契约与变换

本 Pass 把 PTX 指令级 FTZ/rounding 需求转成全局模式状态。它构建包含 internal call/return 的全 module CFG，分别求解 f32 与 f16/f64 的 denormal、rounding 状态，用 HiGHS 选择插入点，再生成 `SetMode`、模式 prologue block 和重定向边；kernel 初始模式写入 `KernelAttributes`。

输出不变量：所有被 `get_modes` 或 `FpModeRequired` 标记的 statement 在可达路径上观察到所需模式。该设计源于 AMDGPU 全局模式，不是 NVPTX 固有 Pass。

## 顺序依赖

需要 Pass 12 的 label/terminator/call-continuation 形态和 Pass 13 的可达 CFG；必须晚于 Pass 10/11 产生的 Div/模式标记。异步协议分析应在其后读取最终 CFG。

## 现代指令接入

`get_modes` 是穷尽 `match`，新增 instruction variant 必须明确分类为无模式或给出模式需求。矩阵/async/同步指令通常是 none；新低精度浮点算术可能需要扩展模式维度，而非硬塞入 f16/f64 组。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 新 instruction variant | `get_modes` 穷尽匹配 | 编译强制分类，是正向防线 |
| virtual/indirect call | 注释明确 TODO，CFG 依赖 direct func ID | 尚不支持 |
| solver 失败 | HiGHS 错误被映射为 `error_unreachable` | 诊断不可解释；健壮性未通过 |
| NVPTX 是否真的需要这些 SetMode | 注释和模型均以 AMD GPU 全局模式为目标 | 必须做 NVPTX 语义复核，不能视为天然正确 |

## 测试要求

现有测试覆盖若干 mode conflict、图求解和 call-with-mode。仍需补 loop、递归/间接 call 拒绝、f16/bf16、新 opcode 分类、solver failure 诊断，以及 NVPTX O0/O3 结果对照。
