# 18 · Activation

状态：`IN_PROGRESS`（族级实验设计与 `sm_110a` 助记符/合法面校准完成，见
[实验设计.md](实验设计.md)；`tanh` 已建成自包含静态套件并通过本机 CUDA 13.0 O0–O3 自检，`ex2` 处于
`DESIGNED`）

## 范围

覆盖 tanh、ex2 等 F16/F16x2/BF16/BF16x2/F32 activation lowering，以及它们与常见
epilogue pattern 的组合。

## 具体指令目录

- [`tanh`](tanh/)：F16/F16x2/BF16/BF16x2/F32（`FRAMEWORK_VALIDATED`，[套件](tanh/thor_ptx90/)）；
- [`ex2`](ex2/)：F16/F16x2/BF16 等低精度 activation（`DESIGNED`）。

F32/F64 的通用 `ex2` lowering 由 `06_cuda_core_fp` 持有。

## 族级设计

[实验设计.md](实验设计.md) 记录：两个 opcode 的结构分类（A 单指令直译 / L 拆 lane 序列，未观测到多项式
模拟形态）、`sm_110a` 实测助记符总表（`MUFU.TANH`/`MUFU.TANH.F16`/`MUFU.TANH.BF16`/`MUFU.EX2.F16`/
`MUFU.EX2.BF16`）、与 epilogue（mul/cvt/双链/guard）组合的融合/不融合实测、已校准合法面（含
"`.ftz` 合法性不能跨 opcode 或跨 dtype 类推"这条 P0-2 核心教训）、对 tcgen05 对抗式审查 P0/P1 缺口的
对应设计，以及 `ex2` 套件的建设路线。全部结论为 `STATIC_ONLY`：数值近似精度、误差度量、输入域和特殊值
策略均未验证，不满足本族完成门槛所指的"可替换规则"标准，见文末边界声明。

## 优先上下文

- dtype、scalar/packed、approx、FTZ 和 modifier；
- `±0`、小量、饱和区、Inf、NaN 和边界邻域；
- convert → activation、activation → mul/add、clamp 和 pack；
- single/multi-use、predicate 和 dead-result elimination；
- 精度/吞吐候选、辅助多项式序列和寄存器压力。

## 本族完成门槛

候选只记录 ptxas 已观察 lowering；数值 oracle 必须声明误差度量、输入域和特殊值策略，
不能把观察到的近似序列直接当作可替换规则。
