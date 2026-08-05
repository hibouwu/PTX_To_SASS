# `ex2`（低精度 activation）

状态：`DESIGNED`（dtype × `.ftz` 合法面、拆 lane 序列结构、f32 越界对照已在
[../实验设计.md](../实验设计.md) 中校准；尚未建立 `thor_ptx90/` 套件）

负责 F16/F16x2/BF16 等低精度 ex2、approx/FTZ、特殊值和 epilogue consumer。

实测映射：`ex2.approx.f16`/`.f16x2` → `MUFU.EX2.F16`（标量 1:1 / `f16x2` 拆 lane 序列，结构与
`tanh.f16x2` 同构）；`ex2.approx.bf16`/`.bf16x2` **必须**带 `.ftz`（不带则拒绝）→
`MUFU.EX2.BF16`。`.ftz` 在 `f16` 上非法、在 `bf16` 上强制——按 dtype 反向，不能从 `tanh`（全 dtype
统一禁用 `.ftz`）或从 `f16` 类推到 `bf16`。`f32`/`f64` 通用形态归 `06_cuda_core_fp` 持有，不在本目录
范围内；仅在设计文档中作为"范围规约协议是 f32 精度特有"的边界对照记录。
