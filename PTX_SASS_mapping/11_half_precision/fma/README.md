# `fma`（F16/F16x2）

状态：`FRAMEWORK_VALIDATED`（[`thor_ptx90/`](thor_ptx90/)：本机 CUDA 13.0，8 个 syntax + 21 个 expanded case 于 O0–O3 共 116 次编译、反汇编与 `HFMA2` 归属全部通过；10 个负向探针全部按预期拒绝且诊断子串匹配；基线零命中检查通过）

负责 F16/F16x2 fused multiply-add、accumulator、packed lane 和 modifier。实测：`fma.rn{.ftz}{.sat}.f16` 与 `.f16x2` 均映射 `HFMA2`；`.rn` 是唯一合法舍入档且强制显式书写（省略报 "Rounding modifier required"，`.rz/.rm/.rp` 报 "Illegal rounding modifier"，均不进 SASS 助记符）；标量三个源操作数一律带 `.H0_H0` selector，packed 不带；`neg.f16`/`abs.f16` 喂给 fma 乘数时在 O3 折叠进同一条 `HFMA2` 的操作数符号/绝对值位，不产生独立指令。详见 [`11_half_precision/实验设计.md`](../../实验设计.md)。
