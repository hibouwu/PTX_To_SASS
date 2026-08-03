# `tcgen05.mma` 可预测映射与逆向可恢复性规则

> 本页由 `analyze_mapping_rules.py` 从 expanded manifest、O3 核心 SASS attribution 和逐配对 context differences 自动生成。结论只适用于当前 PTX 9.0、`sm_110a`、生成矩阵和工具链。

> 当前输入与工具链已写入生成 JSON：ptxas SHA-256 `daba837a68265cae38c832d13399b61dab811891de9b8914defddef143b849f2`，nvdisasm SHA-256 `3c27bded09bd877807207b62db8186a0a9a359d10311ab6e2c885f9b418c9f41`。

## guard lowering 的精确分类

正 guard 的 1,152 个单因素设计分为：`external_control_flow` 800, `first_occurrence_core_predication` 352。正负极性分类不一致的设计数为 0。

在当前字段集中，能无误差预测两种路径的最小特征组合大小为 4，第一组最小预测器是 `variant + kind + zero_column_mask + step_count`。精确规则可以写成：

```text
first_occurrence_core_predication =
    step_count == 2
    and (
        variant in {mma.sp, mma.ws.sp}
        or (kind in {f16, tf32, f8f6f4, i8} and zero_column_mask == false)
    )

其余合法形态 = external_control_flow
```

分析器已把这条手写公式逐项回放到 1152 个设计，mismatch=0；出现任何 mismatch 会使规则挖掘失败。

352 个 `first_occurrence_core_predication` 样本的 occurrence 谓词形状全部是 `(true, false)`：只有 collector 序列第一条核心 MMA 带 `@UPn/@!UPn`，第二条不重复携带 guard。其余 800 个设计的所有核心 occurrence 都不带 guard，由外围控制流实现条件执行。正负 guard 只改变谓词极性，不改变上述路径分类。完整预测分组保存在[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)中。

## lane-0 issuer 的核心重编号条件

lane-0 issuer 的 1,152 个单因素设计分为：`renumber_only` 168, `stable_layout` 984。

在当前字段集中，能无误差预测 `renumber_only` 与 `stable_layout` 的最小特征组合大小为 4，第一组最小预测器是 `variant + kind + a_form + zero_column_mask`。精确规则可以写成：

```text
renumber_only =
    a_form == tmem_address
    and (
        (variant == mma.sp and kind in {mxf4, mxf4nvf4, mxf8f6f4})
        or (variant == mma.ws.sp and zero_column_mask == true)
    )

其余合法形态 = stable_layout
```

分析器已把这条手写公式逐项回放到 1152 个设计，mismatch=0；出现任何 mismatch 会使规则挖掘失败。

前一分支有 100 个设计，后一分支有 68 个设计，合计 168 个；它们在 O1–O3 仅改变具体寄存器编号，不改变寄存器类别、别名关系、核心助记符或规范操作。完整预测分组保存在[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)中。


这里的预测目标只是在 O3 核心 MMA 上是否发生纯物理寄存器重编号；lane-0 issuer 对所有设计的完整控制流和活跃寄存器仍有影响。

## PTX source alias 的编码等价性

在同一 semantic form 内比较 O3 `runtime_zero` 的 source spelling，共有 384 对。384/384 对生成完全相同的具体核心 SASS 操作文本，384/384 对连两个 64-bit encoding word 也完全相同。

| 仅改变的 source spelling | 配对数 | 核心操作文本相同 | 核心编码相同 |
|---|---:|---:|---:|
| `collector_spelling` | 160 | 160 | 160 |
| `collector_spelling+scale_vector_spelling` | 64 | 64 | 64 |
| `scale_vector_spelling` | 160 | 160 | 160 |

因此，显式 `.collector::*::discard` 与缺省 discard、缺省 scale-vector 与其等价显式拼写，在当前语义条件相同的配对中都是机器编码级 alias。仅凭核心 SASS 或核心机器码不能恢复用户采用了哪一种等价 PTX 拼写。

## 已隔离的核心机器编码位

下表只保留具体寄存器文本完全相同、移除被测 SASS modifier 后整条操作文本也完全相同的 O3 单因素配对，因此 XOR mask 不混入寄存器编号变化。`word 0/1` 按 `nvdisasm` 在 attribution 中输出的两个 64-bit encoding word 顺序编号。

| PTX/SASS 变化 | 独立 witness 组 | 候选配对 | word 0 XOR | word 1 XOR | 位方向 |
|---|---:|---:|---:|---:|---|
| `.cta_group::1 → .cta_group::2` / `.2CTA` | 424 | 424 | `0x0000000000000000` | `0x0000000000200000` | 置位 |
| `无 .ashift → .ashift` / `.ASHIFT` | 32 | 80 | `0x0000000000000000` | `0x0000000000000400` | 置位 |
| `A discard → fill/keep` / `.A_KEEP` | 176 | 1264 | `0x0000000000000000` | `0x0000000000100000` | 置位 |
| `B discard/lastuse → fill/use` / `.B_KEEP` | 256 | 608 | `0x0000000000000000` | `0x0000000000020000` | 置位 |
| `B0 → B1` / `.BUFFER1` | 160 | 288 | `0x0000000000000000` | `0x0000000000008000` | 置位 |
| `B0 → B2` / `.BUFFER2` | 160 | 288 | `0x0000000000000000` | `0x0000000000010000` | 置位 |
| `B0 → B3` / `.BUFFER3` | 160 | 288 | `0x0000000000000000` | `0x0000000000018000` | 置位 |
| `非 4X → 4X` / `.4X` | 40 | 352 | `0x4000000000000000` | `0x0000000000000000` | 清位 |
| `非 WS → WS` / `.WS` | 16 | 64 | `0x0000000000000000` | `0x0000000000080000` | 置位 |

候选配对会因等价 source spelling 和同组重复实例形成笛卡尔积，因此表中把独立 witness 组作为证据规模，把候选配对仅作为一致性重复数；每组的 witness ID、左右 PTX、SASS、encoding、置位 mask 和清位 mask 均保存在生成 JSON。所有行都只有一个稳定 XOR mask，其中 `.4X` 是清位，其余当前字段是置位或表中注明的方向；B buffer 的 `B0/B1/B2/B3` 对应 word 1 的两位字段 `0x0000/0x8000/0x10000/0x18000`。这里描述的是当前 Thor 工具链输出，不把 bit 编号外推到其他架构；`A/B_REUSE` 配对还会改变高位调度控制字段，尚未列入已隔离规则。

## 从核心 SASS 反推 PTX 字段

分析集合为 O3 `runtime_zero` 的 1648 个目标 occurrence，共有 1152 种 PTX 目标指令文本和 300 种去除具体寄存器编号后的核心 SASS signature。出现多 PTX 拼写或字段歧义的 signature 有 300 个，其中存在语义字段歧义的有 300 个。

| PTX 字段 | 可唯一恢复的 SASS signature | 加权 occurrence | 当前结论 |
|---|---:|---:|---|
| `opcode_variant` | 0/300 (0.0%) | 0/1648 (0.0%) | 核心 SASS signature 无法唯一恢复 |
| `weight_stationary` | 300/300 (100.0%) | 1648/1648 (100.0%) | 样本内可由核心 SASS 唯一恢复 |
| `sparse` | 0/300 (0.0%) | 0/1648 (0.0%) | 核心 SASS signature 无法唯一恢复 |
| `cta_group` | 300/300 (100.0%) | 1648/1648 (100.0%) | 样本内可由核心 SASS 唯一恢复 |
| `kind` | 200/300 (66.7%) | 824/1648 (50.0%) | 条件可恢复，存在多对一组 |
| `a_form` | 300/300 (100.0%) | 1648/1648 (100.0%) | 样本内可由核心 SASS 唯一恢复 |
| `scale_vector_semantics` | 268/300 (89.3%) | 1256/1648 (76.2%) | 条件可恢复，存在多对一组 |
| `scale_vector_spelling` | 252/300 (84.0%) | 1088/1648 (66.0%) | 条件可恢复，存在多对一组 |
| `zero_column_mask` | 300/300 (100.0%) | 1648/1648 (100.0%) | 样本内可由核心 SASS 唯一恢复 |
| `collector_op` | 300/300 (100.0%) | 1648/1648 (100.0%) | 样本内可由核心 SASS 唯一恢复 |
| `collector_buffer` | 300/300 (100.0%) | 1648/1648 (100.0%) | 样本内可由核心 SASS 唯一恢复 |
| `ashift` | 300/300 (100.0%) | 1648/1648 (100.0%) | 样本内可由核心 SASS 唯一恢复 |
| `collector_spelling` | 186/300 (62.0%) | 592/1648 (35.9%) | 条件可恢复，存在多对一组 |

“样本内可恢复”只表示当前生成集合中没有碰撞；它不是 ISA 对未来形态的一一对应保证。source spelling 字段尤其容易在规范化或优化后丢失。

## 主要多对一实例

### 1. `UTCOMMA gdesc[UR{0}], gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}`

该 signature 汇合 20 种 PTX 目标拼写、20 个 occurrence；歧义字段：`opcode_variant`="tcgen05.mma","tcgen05.mma.sp"；`sparse`=false,true；`kind`="mxf4","mxf4nvf4"；`scale_vector_semantics`="block32","scale_vec::2X"；`scale_vector_spelling`="block32","omitted","scale_vec::2X"；`collector_spelling`="explicit_discard","implicit_discard"。

- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.block32 [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.block32.collector::a::discard [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.collector::a::discard [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- 其余 16 种拼写省略；完整集合见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。

### 2. `UTCOMMA tmem[UR{0}], gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}`

该 signature 汇合 20 种 PTX 目标拼写、20 个 occurrence；歧义字段：`opcode_variant`="tcgen05.mma","tcgen05.mma.sp"；`sparse`=false,true；`kind`="mxf4","mxf4nvf4"；`scale_vector_semantics`="block32","scale_vec::2X"；`scale_vector_spelling`="block32","omitted","scale_vec::2X"；`collector_spelling`="explicit_discard","implicit_discard"。

- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.block32 [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.block32.collector::a::discard [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.collector::a::discard [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- 其余 16 种拼写省略；完整集合见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。

### 3. `UTCOMMA.2CTA gdesc[UR{0}], gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}`

该 signature 汇合 20 种 PTX 目标拼写、20 个 occurrence；歧义字段：`opcode_variant`="tcgen05.mma","tcgen05.mma.sp"；`sparse`=false,true；`kind`="mxf4","mxf4nvf4"；`scale_vector_semantics`="block32","scale_vec::2X"；`scale_vector_spelling`="block32","omitted","scale_vec::2X"；`collector_spelling`="explicit_discard","implicit_discard"。

- `tcgen05.mma.cta_group::2.kind::mxf4.block_scale [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::2.kind::mxf4.block_scale.block32 [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::2.kind::mxf4.block_scale.block32.collector::a::discard [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::2.kind::mxf4.block_scale.collector::a::discard [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- 其余 16 种拼写省略；完整集合见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。

### 4. `UTCOMMA.2CTA tmem[UR{0}], gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}`

该 signature 汇合 20 种 PTX 目标拼写、20 个 occurrence；歧义字段：`opcode_variant`="tcgen05.mma","tcgen05.mma.sp"；`sparse`=false,true；`kind`="mxf4","mxf4nvf4"；`scale_vector_semantics`="block32","scale_vec::2X"；`scale_vector_spelling`="block32","omitted","scale_vec::2X"；`collector_spelling`="explicit_discard","implicit_discard"。

- `tcgen05.mma.cta_group::2.kind::mxf4.block_scale [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::2.kind::mxf4.block_scale.block32 [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::2.kind::mxf4.block_scale.block32.collector::a::discard [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::2.kind::mxf4.block_scale.collector::a::discard [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- 其余 16 种拼写省略；完整集合见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。

### 5. `UTCOMMA gdesc[UR{0}].A_KEEP, gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}`

该 signature 汇合 10 种 PTX 目标拼写、30 个 occurrence；歧义字段：`opcode_variant`="tcgen05.mma","tcgen05.mma.sp"；`sparse`=false,true；`kind`="mxf4","mxf4nvf4"；`scale_vector_semantics`="block32","scale_vec::2X"；`scale_vector_spelling`="block32","omitted","scale_vec::2X"；`collector_spelling`="fill","fill_then_lastuse","fill_then_use"。

- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.block32.collector::a::fill [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.collector::a::fill [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.scale_vec::2X.collector::a::fill [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.block32.collector::a::fill [%d_tmem], %desc_a, %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- 其余 6 种拼写省略；完整集合见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。

### 6. `UTCOMMA tmem[UR{0}].A_KEEP, gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}`

该 signature 汇合 10 种 PTX 目标拼写、30 个 occurrence；歧义字段：`opcode_variant`="tcgen05.mma","tcgen05.mma.sp"；`sparse`=false,true；`kind`="mxf4","mxf4nvf4"；`scale_vector_semantics`="block32","scale_vec::2X"；`scale_vector_spelling`="block32","omitted","scale_vec::2X"；`collector_spelling`="fill","fill_then_lastuse","fill_then_use"。

- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.block32.collector::a::fill [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.collector::a::fill [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4.block_scale.scale_vec::2X.collector::a::fill [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- `tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.block32.collector::a::fill [%d_tmem], [%a_tmem], %desc_b, %idesc, [%scale_a_tmem], [%scale_b_tmem], %enable;`
- 其余 6 种拼写省略；完整集合见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。

## 规则使用边界

- guard 与 issuer 的分类规则来自当前有限字段集合；加入 descriptor 常量、真实非恒等 producer 或其他工具链版本后必须重新运行分析器。
- 核心 SASS 的可恢复性不包含外围指令。某些 source/context 信息虽然不在核心中，仍可能从完整 kernel 恢复。
- 逆向 signature 分析会规范化具体寄存器编号，因此不能用该小节预测物理寄存器分配；上一节的机器编码位结论使用的是未规范化且寄存器文本完全相同的严格 witness，不受此限制。
- descriptor 的动态内容尚未枚举，因此 `idesc`、SMEM descriptor 的形状、类型、布局、stride 和 swizzle 位型仍属于未解决层。

## 证据入口

- 规则挖掘器：[`../../analyze_mapping_rules.py`](../../analyze_mapping_rules.py)
- 完整机器可读结果：[`../../results/rule-mining/mapping_rule_analysis.json`](../../results/rule-mining/mapping_rule_analysis.json)
- 生成 manifest：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)
- 核心 SASS attribution：[`../../results/expanded/sass/sass_attribution.jsonl`](../../results/expanded/sass/sass_attribution.jsonl)
- 上下文统计：[`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)
