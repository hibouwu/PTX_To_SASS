# `tcgen05.mma` 规则权威源入口

> 本文仅规定权威数据源和查询路径。所有规则必须直接来自 `thor_ptx90/Docs/` 的原始分析，不得复述、简化或重新解释。  
> 适用范围：PTX ISA 9.0、NVIDIA Thor 架构、编译目标 `sm_110a`  
> 工具验证：CUDA 13.0、ptxas V13.0.88、nvdisasm V13.0.85

## 按问题查权威源

| 问题 | 权威来源 |
|---|---|
| 规则总导图及索引 | [`mapping_rules/README.md`](thor_ptx90/Docs/mapping_rules/README.md) |
| kind → SASS 家族、CTA group → 修饰符、TS/SS 操作数形式 | [`interactions.md`](thor_ptx90/Docs/mapping_rules/interactions.md#基础限定符与操作数契约)、[综合报告](thor_ptx90/Docs/tcgen05_mma_PTX到SASS映射规则报告.md#核心-sass-指令家族如何选择) |
| `.sp`、`.ws`、`.ws.sp` 的语义和编码 | [`variant.md`](thor_ptx90/Docs/mapping_rules/variant.md) |
| 分块缩放和缩放向量的合法组合 | [`block_scaling.md`](thor_ptx90/Docs/mapping_rules/block_scaling.md) |
| A/B collector 的状态转移和修饰符 | [`collector.md`](thor_ptx90/Docs/mapping_rules/collector.md) |
| `.ashift` 的合法条件 | [`interactions.md`](thor_ptx90/Docs/mapping_rules/interactions.md#基础限定符与操作数契约)、[综合报告](thor_ptx90/Docs/tcgen05_mma_PTX到SASS映射规则报告.md#ashift-直接映射为-ashift) |
| 五 UR 槽位、auxiliary 槽位、word 1 编码 | [`descriptor_and_encoding.md`](thor_ptx90/Docs/mapping_rules/descriptor_and_encoding.md) |
| commit、mbarrier、fence、wait 完整协议 | [`memory_consistency.md`](thor_ptx90/Docs/mapping_rules/memory_consistency.md) |
| guard、issuer、producer、enable、completion 的编译降级 | [`context_lowering.md`](thor_ptx90/Docs/mapping_rules/context_lowering.md) |
| 30 项非法组合的完整列表和诊断 | [`interactions.md`：完整阴性探针目录](thor_ptx90/Docs/mapping_rules/interactions.md#完整阴性探针目录) |
| SASS → PTX 候选生成和多对一字段 | [`reverse_mapping_rules.md`](thor_ptx90/Docs/mapping_rules/reverse_mapping_rules.md) |
| 三个完整的 PTX ↔ SASS 对照例子（二进制反汇编） | [综合报告：附录 A](thor_ptx90/Docs/tcgen05_mma_PTX到SASS映射规则报告.md#附录-a三个完整-ptx--sass-对照例子) |
| 64,548 个配对比较的详细分析和结论 | [综合报告](thor_ptx90/Docs/tcgen05_mma_PTX到SASS映射规则报告.md) |

## 数据源位置

### 一级：编译和反汇编数据

| 数据源 | 内容 | 位置 |
|---|---|---|
| 源码清单 | 1,152 个基础 PTX 实现的坐标 | `generated/manifest.jsonl` |
| 生成统计 | 总数和分类摘要 | `generated/summary.json` |
| SASS 归属 | 99,000 个 occurrence 的 PTX→SASS 配对 | `results/expanded/sass/sass_report.json` |
| 配对分析 | 64,548 个上下文配对的差分汇总 | `results/context-comparison/context_summary.csv` |
| 协议验证 | 49 个 commit/mbarrier/fence/wait case 编译 | `results/protocol-layers/compile_report.json` |
| 非法组合 | 30 项阴性探针的拒绝诊断 | `results/negative-probes/negative_probe_report.json` |

### 二级：规则分析文档

| 文档 | 关键内容 | 位置 |
|---|---|---|
| 索引 | 规则速览和问题导航 | `Docs/mapping_rules/README.md` |
| 主报告 | 64,548 个配对、对照例子、统计分析 | `Docs/tcgen05_mma_PTX到SASS映射规则报告.md` |
| variant | `.sp`/`.ws` 的编码规则 | `Docs/mapping_rules/variant.md` |
| collector | A/B 状态机、转移规则、修饰符 | `Docs/mapping_rules/collector.md` |
| block_scaling | kind 与 scale_vector 的合法组合 | `Docs/mapping_rules/block_scaling.md` |
| descriptor_and_encoding | [关键] 五槽位、auxiliary UR、word 1 编码 | `Docs/mapping_rules/descriptor_and_encoding.md` |
| memory_consistency | [关键] 完整协议矩阵 | `Docs/mapping_rules/memory_consistency.md` |
| context_lowering | guard、issuer、producer、completion 降级 | `Docs/mapping_rules/context_lowering.md` |
| interactions | [关键] 30 项非法组合、限定符联合约束 | `Docs/mapping_rules/interactions.md` |
| reverse_mapping | SASS → PTX 候选、多对一字段 | `Docs/mapping_rules/reverse_mapping_rules.md` |
| reproducibility | Thor 重跑、差异分析 | `Docs/mapping_rules/reproducibility.md` |

## 当前覆盖范围

| 维度 | 规模 | 状态 |
|---|---|---|
| 源码实现（syntax） | 1,152 | 0 反例 |
| 语义形态（semantic form） | 896 | 规范化完成 |
| 扩展实现（上下文组合） | 17,290 | 完整覆盖 |
| SASS 出现位置 | 99,000 | 完整配对 |
| 上下文配对 | 64,548 | 差分分析 |
| 协议 case | 49（196 个编译） | 编译通过 |
| 非法组合 | 30 | 30/30 拒绝 |

## 禁止清单（防止"双重真相"）

- [禁止] 创建规则集的简化版、总结版或"AI 特化版"
- [禁止] 复述维度文档中的规则内容
- [禁止] 基于报告重新解释或简化规则
- [禁止] 声称任何来源是"权威版本"（除 `Docs/` 本身）

## 许可清单

- [允许] 直接引用权威源的具体规则和片段
- [允许] 按权威源的原文实现编译器
- [允许] 生成指向权威源的导航和索引
- [允许] 给出权威源的具体位置和页码

---

**创建**：2026-08-04  
**性质**：权威源的**指引**，不是权威本身
