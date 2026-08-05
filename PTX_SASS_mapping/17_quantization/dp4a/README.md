# `dp4a`

状态：`FRAMEWORK_VALIDATED`（套件 [`thor_ptx90/`](thor_ptx90/)：14 syntax + 26 expanded case，O0–O3 共 160 次编译/归属 PASS，0 编译失败、0 目标缺失；10 负向探针全绿且诊断子串匹配）

负责四路整数点积累加、signedness、accumulator、源槽和融合。实测：`dp4a.atype.btype d,a,b,c`（`atype`/`btype` ∈ `{u32,s32}`）→ `IDP.4A.{U8,S8}.{U8,S8} d,a,b,c`；`b`/`c` 均接受立即数（O3 下 `b` 走 `UR`、`c` 仍是 GPR，不对称）；`.sat` 是非法修饰符；guard 谓词不进 `IDP.4A` 编码，由后置 `SEL` 处理。详见族文档 [`../实验设计.md`](../实验设计.md)。
