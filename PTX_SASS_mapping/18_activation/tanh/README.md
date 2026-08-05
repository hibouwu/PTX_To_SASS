# `tanh`

状态：`FRAMEWORK_VALIDATED`（[thor_ptx90/](thor_ptx90/) 套件已通过本机 CUDA 13.0 O0–O3 自检：15 syntax
+ 25 expanded case、10 个带诊断锚定的负向探针，含 2 条补集抽样）

负责 F16/F16x2/BF16/BF16x2/F32 tanh、approx、特殊值和 epilogue consumer。

实测映射：`tanh.approx.{f32,f16,bf16}` → `MUFU.TANH`/`MUFU.TANH.F16`/`MUFU.TANH.BF16`（1:1 直译）；
`tanh.approx.{f16x2,bf16x2}` → 拆 lane 序列（两条标量 `MUFU.TANH.*` + `PRMT` 打包/解包，O3 免显式解包）。
`.approx` 在全部 dtype 上强制，`.rn`/`.ftz`/`.sat` 在全部 dtype 上非法（与 `ex2` 等兄弟 approx 指令的
`.ftz` 合法面不能类推）。epilogue 组合（mul/cvt/双链/guard）均不与 `tanh` 融合。族级设计与校准记录见
[../实验设计.md](../实验设计.md)。
