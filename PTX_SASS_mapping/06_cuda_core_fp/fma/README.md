# `fma`

状态：`FRAMEWORK_VALIDATED`（套件：[`thor_ptx90/`](thor_ptx90/)，20 syntax + 77 expanded case，O0–O3 共 388 次编译/归属 PASS，10 负向探针含 2 条 P0-2 补集抽样全部匹配预期诊断）

负责 F32/F64 fused multiply-add 的 rounding、FTZ、源槽和 neg/abs modifier。

实测摘要：`.rnd` 对 `fma` 是**强制**的（省略即拒绝，与 add/sub/mul 的默认 `.rn` 不同）；
`.rn` 不进 SASS 助记符，`.rz`/`.rm`/`.rp` 追加 `.RZ`/`.RM`/`.RP`；`.ftz`/`.sat` 仅
`.f32` 合法；PTX 语法不接受 `fma` 操作数位直接写 `-%reg`/`|%reg|`，但独立的
`neg.f32`/`abs.f32` 生产者会折叠进消费它的 `FFMA`/`DFMA` 源修饰符；guard 谓词
在 O0–O3 均被 if-conversion 成无条件执行 + `FSEL`/`DSEL`，从不以 `@P FFMA`
字面形式出现。完整校准表见族级 [`实验设计.md`](../实验设计.md)。
