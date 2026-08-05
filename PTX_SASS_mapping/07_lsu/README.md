# 07 · LSU

状态：`FRAMEWORK_VALIDATED`（部分）—— 实验设计与全族校准见
[`实验设计.md`](实验设计.md)；旗舰套件 [`ld.global/thor_ptx90/`](ld.global/thor_ptx90/)
首轮自检 70 syntax + 79 expanded case、O0–O3 共 596 次编译/归属全 PASS、
10 负向探针诊断精确匹配。其余 10 个 opcode 目录轴与负向面已在
`实验设计.md` 校准完毕，状态为 `DESIGNED`（待写 `suite_spec.py`）。

## 范围

覆盖 global/shared/local/const/param 的标量与向量 load/store，以及 cache、
eviction、volatile、order 和 scope modifier。

## 具体指令目录

- global：[`ld.global`](ld.global/)（`FRAMEWORK_VALIDATED`，见
  [`thor_ptx90/`](ld.global/thor_ptx90/)）、[`ld.global.nc`](ld.global.nc/)、
  [`st.global`](st.global/)；
- shared：[`ld.shared`](ld.shared/)、[`st.shared`](st.shared/)；
- local：[`ld.local`](ld.local/)、[`st.local`](st.local/)；
- const/param：[`ld.const`](ld.const/)、[`ld.param`](ld.param/)、
  [`st.param`](st.param/)；
- uniform load：[`ldu`](ldu/)。

除 `ld.global` 外的 10 个目录状态为 `DESIGNED`：轴、已校准合法面和负向诊断
已写入 [`实验设计.md`](实验设计.md)，尚未各自建立 `thor_ptx90/` 套件。两个
意外发现值得注意：`ldu` 语法合法但与同宽度 `ld.global` 产生逐位相同的
`LDG.E` 编码（没有独立的 uniform-load SASS 形态）；`.func` ABI 中的
`st.param`/`ld.param` 完全折叠进寄存器调用约定，没有自己的目标 SASS 家族。

cluster shared 的远程访问由 `15_cluster_dsmem` 持有，prefetch 由
`16_megakernel_ctrl` 持有。

## 优先上下文

- 命名符号、立即地址、寄存器地址和寄存器加偏移；
- 正负偏移、缩放、编码边界、对齐和访问宽度；
- generic 与明确 state space、地址转换和 provenance；
- 不别名、可能别名、同址、部分重叠和宽度差异；
- address-add folding、load-arithmetic、arithmetic-store 和 memory order。

## 高风险簇

`state-space × width × alignment × alias × order × scope` 使用受约束组合覆盖；
非法或语义未定义的访问单独记账。
