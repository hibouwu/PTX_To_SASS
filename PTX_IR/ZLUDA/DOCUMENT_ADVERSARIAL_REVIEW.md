# 三份设计文档的对抗式审查记录

审查对象：

- [`PTX_TO_NVVM_PASS_PIPELINE.md`](PTX_TO_NVVM_PASS_PIPELINE.md)
- [`PTX_INSTRUCTION_SUPPORT_SM107_SM110.md`](PTX_INSTRUCTION_SUPPORT_SM107_SM110.md)
- [`TCGEN05_ASYNC_PIPELINE_DESIGN.md`](TCGEN05_ASYNC_PIPELINE_DESIGN.md)

目标是文档事实与当前源码一致、当前/建议分离、每层结构可定位、现代指令改动可执行，并避免三份文档互相复制。

## 第 1 轮：用反例推翻原主张

| 层 | 反例 | 源码证据 | 原结论 | 修正 |
| --- | --- | --- | --- | --- |
| L1 符号/目标 | `sm_110a` 被 module 丢成 110；function shared memory 使用 assert | parser Module、Pass 01 | 目标传播和 identifier 过度乐观 | 增加完整 target descriptor 建议；Pass 01 记录 panic 风险 |
| L2 operand/ABI | 后置函数声明不能被 Pass 05 识别；Pass 07 立即 repack async dst | Pass 05 单遍集合、`vec_pack` | 只改 Pass 15 即可 | Pass 05 记录两遍修复；tcgen05 改为 pending marker + 新 Pass |
| L3 FP/CFG | Pass 11 实际匹配所有 rounding float div；Pass 12 消费首 label | Pass 11 pattern、Pass 12 peek/next | 按文件名和注释描述范围 | 按真实 pattern 重写；增加低精度与 branch-to-entry 反例 |
| L3 FP/CFG | Pass 14 是 AMDGPU 全局模式模型 | 源码注释、HiGHS 求解 | 被写成 NVVM 必需层 | 改为历史边界并要求 NVPTX 对照验证 |
| L4 存储/类型 | Pass 17 对 cluster/ParamFunc 调用 `todo!()`；普通 b32 无法区分 TMEM 地址 | `is_addressable`、resolver type_space | “增加 TMEM state space 即可” | storage/value/pointer 分层；记录结构化 reject 门槛 |
| L5 lowering | `shfl.sync` 双目标已有新展开；helper 声明仅按名称去重 | Pass 18 `run_statements`、BTreeMap key | 支持矩阵过时且忽略签名冲突 | 修正 shfl 评级；新增同名异签名审查 |
| E backend | wait/fence attributes 不同；consumer 无普通 SSA chain | IntrinsicsNVVM.td | 属性被当作顺序证明 | 记录真实 attributes；加入 O3/llc ordering gate |

第 1 轮结果：不通过。三份原文存在事实过时、层次重复和实现/建议混写，已重构。

## 第 2 轮：逐层检查重构后的契约

| 层 | 检查问题 | 结果 | 证据位置 |
| --- | --- | --- | --- |
| L1 | 是否区分名称绑定、target validation 和谓词合法性？ | 通过 | Pass 01/03 文档、建议 `validate_target_features` |
| L2 | 是否说明普通 tuple 与 async destination 的差异？ | 通过 | Pass 07 文档、tcgen05 pending marker |
| L2 | 是否把函数 ABI、descriptor value kind 与 operand 展开混为一层？ | 通过 | Pass 04/09/17 分离记录 |
| L3 | 是否按实际源码说明 Pass 10/11/14 的范围？ | 通过 | 三个独立文档均列反例和类型边界 |
| L3 | 新 async Pass 是否看到最终 CFG 且位于 local-slot lowering 前？ | 通过 | tcgen05 第 5 节、建议 Pass 契约 |
| L4 | 是否区分 storage、address width、implicit conversion？ | 通过 | Pass 15/16/17 独立契约 |
| L5 | 是否要求每个新 opcode 明确 direct/intrinsic/helper/reject？ | 通过 | pipeline 第 6 节、Pass 18 文档 |
| E | 是否把 SASS scheduling 留给 backend/ptxas？ | 通过 | tcgen05 第 7/9 节 |

第 2 轮结果：文档结构通过；源码实现风险没有被误标成已解决。

## 第 3 轮：一致性与冗余检查

检查项：

1. 三份总览各自只保留 pipeline、capability、tcgen05 delta，不复制 19 个 Pass 的长篇实现说明。
2. 19 个当前 Pass 均有独立文件，且都有契约、顺序、现代指令接入、反例和测试要求。
3. 建议 Pass 单独标记“尚未实现”。
4. 所有相对 Markdown 链接解析到现存文件。
5. `git diff --check` 无空白错误。
6. 搜索旧名称 `validate_and_annotate_tcgen05_async`、旧结论“只修改 Pass 15”和过时 shfl 失败结论均无残留。

第 3 轮结果：文档一致性通过。

## 审查结论的边界

“文档审查通过”只证明：当前事实、已知反例、建议边界和验证门槛在这些文档中自洽。它不证明以下实现已经完成：

- target suffix 保存与 target validator；
- tcgen05 parser/AST、pending marker 和异步 Pass；
- TMEM value kind/addrspace(6) lowering；
- 19 个 Pass 缺失的专属测试；
- LLVM ordering gate、ptxas 和硬件验证。

这些项目只有代码和测试证据齐全后，才能从“设计通过”升级为“实现通过”。
