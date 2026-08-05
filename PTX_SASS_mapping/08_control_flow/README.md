# 08 · 控制流

状态：`IN_PROGRESS`（族级实验设计与 `sm_110a` 助记符/合法面校准完成，见 [实验设计.md](实验设计.md)；`brx.idx` 已建成自包含静态套件并通过本机 CUDA 13.0 O0–O3 自检，其余 4 个 opcode 处于 `DESIGNED`）

## 范围

覆盖条件/无条件 branch、return、基本块布局，以及与分支直接相关的 predicate 和
特殊寄存器 consumer。特殊寄存器本身的 lowering 归 `09_special_reg`。

本族核心方法论问题（见 [实验设计.md](实验设计.md)"过匹配与归属方法论"）：全部 5 个
opcode 的助记符（`BRA`/`BRX`/`CALL`/`RET`/`EXIT`）都与 kernel 尾部恒有的
`EXIT` + 自跳 `BRA` 收尾结构存在子串重叠或彼此重叠，逐指令归属必须基于块结构而非
子串匹配；`brx.idx` 的 `BRX`/`BRXU` 是唯一不受此污染、可用子串匹配验证的助记符，
因此被选为旗舰。

## 具体指令目录

- [`bra`](bra/)：`DESIGNED`——divergence/重汇聚机制（`BSSY.RECONVERGENT`/`BSYNC.RECONVERGENT`）已实测校准；
- [`brx.idx`](brx.idx/)：`FRAMEWORK_VALIDATED`，[套件](brx.idx/thor_ptx90/)；
- [`call`](call/)：`DESIGNED`——已实测 `ptxas` 从不内联、`CALL.REL.NOINC`/`RET.REL.NODEC` 恒定配对；
- [`ret`](ret/)：`DESIGNED`——entry 级恒为 `EXIT`，`.func` 级为 `RET.REL.NODEC`，提前返回重构为跳转而非谓词化 `RET`；
- [`exit`](exit/)：`DESIGNED`——谓词化 `exit` 直接产生 `@P EXIT`，不触发重汇聚簿记。

## 优先上下文

- predicate 来源、取反、uniform/divergent 和 P/UP 结果；
- fallthrough、目标块布局、汇合、循环和分支距离；
- 跨块 producer/consumer、live range 和 phi-like merge；
- leaf/non-leaf、call/return、内联和 ABI；
- compare-branch folding、code motion 和不可跨越副作用。

## 本族完成门槛

必须区分 PTX 源布局、优化后 CFG 和最终 SASS 布局；源码相邻或距离不能直接当作已实现结果。
