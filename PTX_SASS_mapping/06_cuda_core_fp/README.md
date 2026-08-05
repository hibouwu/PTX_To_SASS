# 06 · CUDA Core 浮点与转换

状态：`DESIGNED`（族级实验设计与探针校准完成；旗舰套件 `fma/thor_ptx90/` 已 `FRAMEWORK_VALIDATED`：20 syntax + 77 expanded case，O0–O3 共 388 次编译/归属 PASS，10 负向探针含 2 条 P0-2 补集抽样全部匹配预期诊断；其余 16 个 opcode 目录轴已校准，待各自建套件——见 [`实验设计.md`](实验设计.md)）

## 范围

覆盖 F32/F64 add/mul/fma、min/max、abs/neg、ex2/lg2/rcp/rsqrt/sqrt，以及整数、
F16、BF16 与 F32/F64 之间的转换。

## 实验设计

族级实验设计、探针校准表（rounding/ftz/sat 到 SASS 修饰符映射、MUFU 家族清单、
`.rn` 全精度长序列结构、min/max f64 序列化、abs/neg/sub/cvt.f32.f16 折叠等）、
结构分类（直译/MUFU/序列/折叠）、审查缺口落实与套件路线图见
[`实验设计.md`](实验设计.md)。

## 具体指令目录

- 算术：[`add`](add/)、[`sub`](sub/)、[`mul`](mul/)、[`fma`](fma/)（`FRAMEWORK_VALIDATED`，见 [`fma/thor_ptx90/`](fma/thor_ptx90/)）、
  [`div`](div/)、[`min`](min/)、[`max`](max/)、[`abs`](abs/)、[`neg`](neg/)；
- 特殊函数：[`rcp`](rcp/)、[`sqrt`](sqrt/)、[`rsqrt`](rsqrt/)、
  [`sin`](sin/)、[`cos`](cos/)、[`lg2`](lg2/)、[`ex2.f32-f64`](ex2.f32-f64/)；
- 类型转换：[`cvt`](cvt/)。

低精度 `tanh/ex2` 由 `18_activation` 持有；F16/BF16 算术分别由
`11_half_precision` 和 `12_bf16` 持有。

## 优先上下文

- rounding、FTZ、approx、sat 和 modifier 组合；
- `±0`、normal/subnormal 边界、`±Inf`、多个 NaN bit pattern；
- producer/consumer 转换折叠、FMA contraction 和 neg/abs folding；
- 源槽立即数能力、constant materialization 和寄存器类别；
- packed conversion、宽位结果和 O0/O3 的存活差异。

## 本族完成门槛

浮点 oracle 必须按指令语义区分 bit-exact、允许结果集合和误差界，不能统一使用一种比较。
