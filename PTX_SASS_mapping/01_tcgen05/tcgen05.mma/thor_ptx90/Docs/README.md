# tcgen05.mma 最终报告

本目录只保存适合直接阅读和纳入版本控制的最终报告。

文档入口：

- [`mapping_rules/README.md`](mapping_rules/README.md)：规则总索引。基础维度跳转到综合报告，复杂状态机、联合作用、上下文、编码、逆向、内存一致性和复现边界各保留一份专题。
- [`mapping_rules/context_lowering.md`](mapping_rules/context_lowering.md)：统一整理 guard、lane/CTA-thread issuer 和直接/恒等/非恒等/分支/global-load producer 的外围编译降级。
- [`mapping_rules/memory_consistency.md`](mapping_rules/memory_consistency.md)：系统整理 commit、mbarrier、tcgen05 fence、LD/ST wait、scope 和资源生命周期。
- [`mapping_rules/reverse_mapping_rules.md`](mapping_rules/reverse_mapping_rules.md)：自动挖掘 guard/issuer 的精确决策条件，并量化从规范化核心 SASS 反推各 PTX 字段时的一对一与多对一边界。
- [`mapping_rules/descriptor_and_encoding.md`](mapping_rules/descriptor_and_encoding.md)：把 descriptor 视为不透明寄存器操作数，列出已隔离的编码位、机器码级 alias 和静态 mapping 完成标准。
- [`../results/rule-mining/canonical_mapping_rules.json`](../results/rule-mining/canonical_mapping_rules.json)：由分析器生成的 semantic form→SASS/encoding payload 正向规则，以及 SASS/encoding payload→PTX 候选集合逆向规则。
- [`mapping_rules/reproducibility.md`](mapping_rules/reproducibility.md)：记录 Thor 主机重跑、跨 CUDA 13.0 二进制的逐记录稳定性，以及 O0 无语义差异的处理边界。
- [`tcgen05_mma_PTX到SASS映射规则报告.md`](tcgen05_mma_PTX到SASS映射规则报告.md)：指令族综合报告，讲清修饰符联合作用、完整编译降级、函数级 PTX/SASS 例子、寄存器和上下文。
- [`tcgen05_mma_上下文差分报告.md`](tcgen05_mma_上下文差分报告.md)：供进一步核对的逐上下文统计报告。

运行 `../check_all.sh` 后，完整 cubin、SASS、逐配对 JSONL 和中间日志写入 `../results/`。最终中文上下文差分报告会同步生成到 `tcgen05_mma_上下文差分报告.md`。

`results/` 中的 `.cubin` 和体积较大的逐记录 `.jsonl` 文件会被 Git 忽略；原始与活跃寄存器 SASS 当前作为可审计证据保留。其余紧凑报告和元数据仍可按需纳入版本控制。
