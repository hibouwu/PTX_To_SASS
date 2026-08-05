# `ld.global`

状态：`FRAMEWORK_VALIDATED`（[`thor_ptx90/`](thor_ptx90/)：70 syntax + 79 expanded case，O0–O3 共 596 次编译/归属全 PASS；10 负向探针诊断精确匹配）

负责 global load 的宽度、向量形态、cache、order、scope、地址和对齐。

一句话实测映射摘要：weak cache-op（`.ca/.cg/.cv`）与显式内存序 scope（`relaxed`/`acquire` × `cta/gpu/sys`）在本机上产生逐位相同的 `LDG.E...STRONG.{SM,GPU,SYS}` 编码，`.cs`→`EF`/`.lu`→`LU` 独立；寄存器+偏移仅在 O1–O3 折进 `LDG` 自身、且窗口为有符号 24 位 `[-0x800000,0x7fffff]`；`.b128` 标量合法（推翻直觉假设），`ldu` 与同宽度 `ld.global` 编码逐位相同（无独立 uniform SASS 形态）。详见 [`../实验设计.md`](../实验设计.md) 与 [`thor_ptx90/README.md`](thor_ptx90/README.md)。
