# tcgen05.mma 最终报告

本目录只保存适合直接阅读和纳入版本控制的最终报告。

文档入口：

- [`mapping_rules/README.md`](mapping_rules/README.md)：按 kind、CTA group、变体、操作数来源、collector、分块缩放、`.ashift` 和内存一致性拆分的可检索规则索引。查单个语义维度时从这里开始。
- [`mapping_rules/memory_consistency.md`](mapping_rules/memory_consistency.md)：系统整理 commit、mbarrier、tcgen05 fence、LD/ST wait、scope 和资源生命周期。
- [`tcgen05_mma_PTX到SASS映射规则报告.md`](tcgen05_mma_PTX到SASS映射规则报告.md)：指令族综合报告，讲清修饰符联合作用、完整编译降级、函数级 PTX/SASS 例子、寄存器和上下文。
- [`tcgen05_mma_上下文差分报告.md`](tcgen05_mma_上下文差分报告.md)：供进一步核对的逐上下文统计报告。

运行 `../check_all.sh` 后，完整 cubin、SASS、逐配对 JSONL 和中间日志写入 `../results/`。最终中文上下文差分报告会同步生成到 `tcgen05_mma_上下文差分报告.md`。

`results/` 中的 `.cubin`、`.sass` 和体积较大的逐记录 `.jsonl` 文件会被 Git 忽略。其余紧凑报告和元数据仍可按需纳入版本控制。
