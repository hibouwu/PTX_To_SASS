# `lop3`

状态：`FRAMEWORK_VALIDATED`（Thor/PTX 9.0 静态套件见 [thor_ptx90/](thor_ptx90/)：37 syntax + 61 expanded case × O0–O3 共 392 次编译/归属 PASS，15 个带诊断锚定的负向探针全部按预期拒绝；forward rule 244、inverse signature 95）

负责三输入 LUT 逻辑、LUT 立即数全集/分区、源槽和 pattern fusion。

核心实测结论（详见 [../实验设计.md](../实验设计.md)）：`LOP3.LUT` 硬件只有 b 槽一个立即数位——a/c 槽的 PTX 立即数触发操作数交换与 immLut 代数置换（0x30 → a 槽 0xc、c 槽 0x50）；字面 0 编码为 RZ（第三操作数类）；immLut 越界静默截断（0x100→0x0、-1→0xff，正向 discovery 记账）；`lop3.{and,or}.b32 d|p` 双消费时一对二 lower 成两条 `LOP3.LUT.PAND`；guard 不存活（无条件计算 + SEL）；O0 不 CSE / O3 CSE。
