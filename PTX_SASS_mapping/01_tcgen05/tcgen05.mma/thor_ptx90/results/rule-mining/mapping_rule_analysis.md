# `tcgen05.mma` 可预测映射与逆向可恢复性规则

> 本页由 `analyze_mapping_rules.py` 从 expanded manifest、O3 核心 SASS attribution 和逐配对 context differences 自动生成。结论只适用于当前 PTX 9.0、`sm_110a`、生成矩阵和工具链。

> 当前输入与工具链已写入生成 JSON：ptxas SHA-256 `a1941a04ca4fd233b2fbe50c625b1e72b3d5f79ebe80209a272c85482dfbb487`，nvdisasm SHA-256 `bc40070d596fa49b81c0905ca1d05e457aaec071280f742997d4a0b511781b25`。

## guard 编译降级的精确分类

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

## lane-0 issuer（发射线程）的核心重编号条件

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

## 扩展 issuer 与 producer 编译降级

新增 issuer/producer profile 已完成 O3 单因素配对，跨四种 branch issuer 的分类不一致数为 0，全部手写公式 mismatch=0。

| profile | design | 核心结果与数量 | 核心 mnemonic 变化 | 完整 kernel 序列变化 | 指令数变化 | 公式 |
|---|---:|---|---:|---:|---:|---|
| `branched_producers` | 1152 | `renumber_only` 1152 | 0 | 1152 | 1152 | all generated designs -> renumber_only |
| `compound_predicated_issuer` | 1152 | `external_control_flow` 656；`first_occurrence_core_predication` 496 | 0 | 1152 | 1056 | step_count == 2 -> first occurrence predicated; otherwise external control flow |
| `derived_producers` | 1152 | `stable_layout` 1152 | 0 | 0 | 0 | identity chain at O3 -> stable_layout |
| `dynamic_lane_issuer` | 1152 | `renumber_only` 168；`stable_layout` 984 | 0 | 1152 | 520 | same renumber_only condition as lane0_issuer |
| `global_load_producers` | 1152 | `renumber_only` 468；`stable_layout` 684 | 0 | 1152 | 1152 | mma.sp: tmem A or block-scale kind; mma.ws.sp: tmem A or zero-column-mask |
| `lane0_issuer` | 1152 | `renumber_only` 168；`stable_layout` 984 | 0 | 1152 | 592 | same renumber_only condition as lane0_issuer |
| `lane31_issuer` | 1152 | `renumber_only` 168；`stable_layout` 984 | 0 | 1152 | 592 | same renumber_only condition as lane0_issuer |
| `nonidentity_producers` | 1152 | `renumber_only` 1152 | 0 | 1152 | 1056 | all generated designs -> renumber_only |
| `thread0_issuer` | 1152 | `renumber_only` 168；`stable_layout` 984 | 0 | 1152 | 824 | same renumber_only condition as lane0_issuer |

四种 branch issuer（lane 0、lane 31、动态 lane、CTA thread 0）对核心映射使用同一条 168/984 重编号分类；差异只落在外围线程标识读取、比较、分支和寄存器布局。compound predicated issuer 的规则更简单：双 occurrence collector 序列只谓词化第一条，单 occurrence 形态使用外围控制流。

identity producer 在 O3 完全消除；非恒等算术和分支选择 producer 保留外围计算并使全部核心发生纯重编号；global-load producer 保持核心助记符和规范操作不变，其中 468 个设计纯重编号、684 个布局稳定。

## PTX 源码别名（source alias）的编码等价性

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

候选配对会因等价 source spelling 和同组重复实例形成笛卡尔积，因此表中把独立 witness 组作为证据规模，把候选配对仅作为一致性重复数；每组的 witness ID、左右 PTX、SASS、encoding、置位 mask 和清位 mask 均保存在生成 JSON。所有行都只有一个稳定 XOR mask，其中 `.4X` 是清位，其余当前字段是置位或表中注明的方向；B buffer 的 `B0/B1/B2/B3` 对应 word 1 的两位字段 `0x0000/0x8000/0x10000/0x18000`。这里描述的是当前 Thor 工具链输出，不把 bit 编号外推到其他架构。`A/B_REUSE` 和 predicate 因伴随调度控制变化而在下一节单独分解。

## opcode、kind 与隐式 scale 的编码

标准非 block-scale kind 在具体操作数完全相同的 O3 pair 上形成 word 1 的两位字段；每一行均只有一个 XOR mask：

| kind 变化 | witness 组 | pair | word 0 XOR | word 1 XOR | 方向 |
|---|---:|---:|---:|---:|---|
| `f16 → tf32` | 272 | 272 | `0x0000000000000000` | `0x0000000000000000` | 编码相同 |
| `f16 → f8f6f4` | 272 | 272 | `0x0000000000000000` | `0x0000000000000300` | 置位 |
| `f16 → i8` | 272 | 272 | `0x0000000000000000` | `0x0000000000000100` | 置位 |
| `f8f6f4 → i8` | 272 | 272 | `0x0000000000000000` | `0x0000000000000200` | 清位 |

因此 `f16` 与 `tf32` 在当前动态 `idesc` 契约下是核心机器编码别名（alias）；`f16/tf32 = 0b00`、`i8 = 0b01`、`f8f6f4 = 0b11` 对应 word 1 的 `0x300` 两位字段。`UTCOMMA` 相对 `UTCQMMA` 还组合使用 word 0 的 opcode 位，不能只看这两位判断全部 block-scale 家族。

在 block-scale 且具体寄存器完全相同的 pair 中，`UTCOMMA → UTCQMMA` 的 composite opcode 变化还取决于 A 来源：

| 家族变化 | A 来源 | witness 组 | pair | word 0 XOR | word 1 XOR |
|---|---|---:|---:|---:|---:|
| `UTCOMMA → UTCQMMA` | `smem_descriptor` | 28 | 168 | `0xc000000000000800` | `0x0000000000000300` |
| `UTCOMMA → UTCQMMA` | `tmem_address` | 28 | 168 | `0xc000000000000600` | `0x0000000000000300` |

word 0 的高两位、低 opcode 子字段和 word 1 的 kind 两位共同决定这一家族转换；SS 与 TS 的低 opcode mask 不同，所以不能把 `UTCOMMA/UTCQMMA` 简化成单一 bit。

全矩阵按 SASS family、A 来源、kind 和 PTX variant 分组后的 opcode composite 值保存在生成 JSON 的 `extended_encoding.opcode_layout.observed_rows`；字段模型固定为 word 0 `[63:56] + [11:0]`、word 1 `[9:8]`，guard 使用 word 0 `[15:12]` 的独立区域。

以下 block-scale 形态在所有严格配对中连具体 SASS 操作和两个 encoding word 都相同，说明 kind/scale 的部分区别没有独立进入核心机器码：

| 隐式 kind/scale alias | 独立 witness 组 | pair | 操作相同 | 编码相同 |
|---|---:|---:|---:|---:|
| `mxf4 block32 ↔ 2X` | 56 | 112 | 112 | 112 |
| `mxf4 ↔ mxf4nvf4 at block32` | 56 | 112 | 112 | 112 |
| `mxf4 block32 ↔ mxf4nvf4 2X` | 56 | 112 | 112 | 112 |
| `mxf4nvf4 block16 ↔ 4X` | 56 | 56 | 56 | 56 |

## `A/B_REUSE` 与 predicate（谓词）编码

`fill → use` 的第二条核心指令同时改变 REUSE payload 和高位调度/控制字段。对全部 pair 求方向交集后，可以把稳定 modifier 位与可变控制位分开：

| 变化 | pair | 稳定置位 word 0 | 稳定置位 word 1 | 稳定清位 word 0 | 可变 word 1 |
|---|---:|---:|---:|---:|---:|
| `.A_REUSE` | 112 | `0x0000000000000000` | `0x0000000000400000` | `0x0000000000000000` | `0x01f2000000000000` |
| `.B_REUSE` | 128 | `0x0000000000000000` | `0x0000000000040000` | `0x0000000000000000` | `0x01f2000000000000` |

`A_REUSE` 的稳定 payload 是 word 1 置位 `0x0000000000400000`，`B_REUSE` 是 word 1 置位 `0x0000000000040000`；两者共同出现的 word 1 高位变化属于调度/控制字段，不能并入 REUSE modifier mask。

| predicate 配对 | pair | 稳定变化 | 其他变化 |
|---|---:|---|---|
| 无核心 predicate → `@UP1` | 232 | word 0 清除 `0x0000000000006000` | word 1 高位随调度布局变化 `0x01ee000000000000` |
| `@UP1 → @!UP1` | 352 | word 0 置位 `0x0000000000008000` | 无 |

定向谓词活跃压力探针进一步冻结完整 selector：核心 guard 的 UP 编号直接写入 word 0 `[14:12]`，`UP0..UP6 → 0..6`，值 7 表示无 guard；word 0 bit 15 是 negate。

guard selector 的定向证据共 7 个 occurrence（`UP0` 1 条、`UP1` 1 条、`UP2` 1 条、`UP3` 1 条、`UP4` 1 条、`UP5` 1 条、`UP6` 1 条）。enable 谓词使用独立字段：word 1 `[25:23]` 直接编码 `UP0..UP6`，值 7 表示 `UPT`，word 1 bit 26 是 enable negate；稀有编号定向证据为 `UP1` 1 条、`UP2` 1 条、`UP3` 1 条、`UP4` 1 条、`UP5` 1 条、`UP6` 1 条，`UP0` 与哨兵值另由常规矩阵提供大量重复。完整逐值计数见生成 JSON。

## 核心寄存器槽位 bitfield（位字段）

把全部 O0/O1/O2/O3 attribution 中反汇编显示的 UR 编号直接回放到 encoding word，得到以下五个 8-bit 槽位，所有检查均为零 mismatch：

| SASS 操作数角色 | encoding 字段 | occurrence | 观测 UR 值 | mismatch |
|---|---|---:|---|---:|
| `source_a` | word 0 `[31:24]` | 99000 | `4,5,6,7,8,9,11,13,15,16,17,22` | 0 |
| `source_b` | word 0 `[39:32]` | 99000 | `4,6,8,10,12,16,18,24` | 0 |
| `destination` | word 1 `[7:0]` | 99000 | `4,6,7,8,10,12,13,14,15,16,17,18` | 0 |
| `auxiliary_mask_or_metadata` | word 0 `[47:40]` | 99000 | `4,6,8,10,12,14,16,18` | 0 |
| `extra_scale_or_zero_mask` | word 0 `[55:48]` | 68814 | `6,8,10,12,14,16,18,20` | 0 |

`idesc[URn]` 在 99000 条 occurrence 中始终满足 `idesc_ur = auxiliary_ur XOR 1`，mismatch=0；当前分配把 auxiliary/idesc 作为偶/奇相邻对，尚未观察到独立 idesc 槽位。extra 槽位另有 240 个只改变该 UR 的上下文 pair 验证，mismatch=0。

常规矩阵中的 enable predicate 主要为 `UP0,UP1,UP2,UP3,UP4,UP5,UP6`，共 89106 条动态谓词 occurrence；v4 定向 sweep 通过同时保持七个统一谓词活跃，独立恢复 word 1 `[25:23]` 字段。

## 可回放的正向与逆向规则

分析器已经生成 [`canonical_mapping_rules.json`](../../results/rule-mining/canonical_mapping_rules.json)：包含 896 条 semantic-form→核心 SASS/semantic-payload 正向规则和 300 条 SASS/semantic-payload→候选 semantic-form 逆向规则；其中 300 条逆向规则必须返回候选集合。正向→逆向逐条回放 mismatch=0。

逆向候选规模分布为 2 个候选的规则 184 条、4 个候选的规则 100 条、8 个候选的规则 16 条；最大候选集合为 8。因此这里的“逆向规则”是可枚举候选关系，不是单值反编译器。

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

| 核心 SASS signature | PTX 目标拼写 | occurrence | 实际歧义字段 |
|---|---:|---:|---|
| `UTCOMMA gdesc[UR{0}], gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}` | 20 | 20 | `collector_spelling`=`"explicit_discard"`,`"implicit_discard"`；`kind`=`"mxf4"`,`"mxf4nvf4"`；`opcode_variant`=`"tcgen05.mma"`,`"tcgen05.mma.sp"`；`scale_vector_semantics`=`"block32"`,`"scale_vec::2X"`；`scale_vector_spelling`=`"block32"`,`"omitted"`,`"scale_vec::2X"`；`sparse`=`false`,`true` |
| `UTCOMMA tmem[UR{0}], gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}` | 20 | 20 | `collector_spelling`=`"explicit_discard"`,`"implicit_discard"`；`kind`=`"mxf4"`,`"mxf4nvf4"`；`opcode_variant`=`"tcgen05.mma"`,`"tcgen05.mma.sp"`；`scale_vector_semantics`=`"block32"`,`"scale_vec::2X"`；`scale_vector_spelling`=`"block32"`,`"omitted"`,`"scale_vec::2X"`；`sparse`=`false`,`true` |
| `UTCOMMA.2CTA gdesc[UR{0}], gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}` | 20 | 20 | `collector_spelling`=`"explicit_discard"`,`"implicit_discard"`；`kind`=`"mxf4"`,`"mxf4nvf4"`；`opcode_variant`=`"tcgen05.mma"`,`"tcgen05.mma.sp"`；`scale_vector_semantics`=`"block32"`,`"scale_vec::2X"`；`scale_vector_spelling`=`"block32"`,`"omitted"`,`"scale_vec::2X"`；`sparse`=`false`,`true` |
| `UTCOMMA.2CTA tmem[UR{0}], gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}` | 20 | 20 | `collector_spelling`=`"explicit_discard"`,`"implicit_discard"`；`kind`=`"mxf4"`,`"mxf4nvf4"`；`opcode_variant`=`"tcgen05.mma"`,`"tcgen05.mma.sp"`；`scale_vector_semantics`=`"block32"`,`"scale_vec::2X"`；`scale_vector_spelling`=`"block32"`,`"omitted"`,`"scale_vec::2X"`；`sparse`=`false`,`true` |
| `UTCOMMA gdesc[UR{0}].A_KEEP, gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}` | 10 | 30 | `collector_spelling`=`"fill"`,`"fill_then_lastuse"`,`"fill_then_use"`；`kind`=`"mxf4"`,`"mxf4nvf4"`；`opcode_variant`=`"tcgen05.mma"`,`"tcgen05.mma.sp"`；`scale_vector_semantics`=`"block32"`,`"scale_vec::2X"`；`scale_vector_spelling`=`"block32"`,`"omitted"`,`"scale_vec::2X"`；`sparse`=`false`,`true` |
| `UTCOMMA tmem[UR{0}].A_KEEP, gdesc[UR{1}], tmem[UR{2}], tmem[UR{3}], idesc[UR{4}], tmem[UR{5}], UP{0}` | 10 | 30 | `collector_spelling`=`"fill"`,`"fill_then_lastuse"`,`"fill_then_use"`；`kind`=`"mxf4"`,`"mxf4nvf4"`；`opcode_variant`=`"tcgen05.mma"`,`"tcgen05.mma.sp"`；`scale_vector_semantics`=`"block32"`,`"scale_vec::2X"`；`scale_vector_spelling`=`"block32"`,`"omitted"`,`"scale_vec::2X"`；`sparse`=`false`,`true` |

表中只列出现次数最高的六组；全部 collision、每组候选 PTX 拼写与字段取值见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。

## 规则使用边界

- guard 与 issuer 的分类规则来自当前有限字段集合；加入 descriptor 常量、真实非恒等 producer 或其他工具链版本后必须重新运行分析器。
- 核心 SASS 的可恢复性不包含外围指令。某些 source/context 信息虽然不在核心中，仍可能从完整 kernel 恢复。
- 逆向 signature 分析会规范化具体寄存器编号，因此不能用该小节预测物理寄存器分配；上一节的机器编码位结论使用的是未规范化且寄存器文本完全相同的严格 witness，不受此限制。
- descriptor 的动态内容尚未枚举，因此 `idesc`、SMEM descriptor 的形状、类型、布局、stride 和 swizzle 位型仍属于未解决层。
- v4 新增的 opcode composite、`A/B_REUSE`、完整 predicate selector、隐式 kind/scale 别名、寄存器槽位和扩展 issuer/producer 机制目前只在一组 Thor 工具链二进制上完成 O0–O3 验证；独立双二进制复现只覆盖 v3 范围，不能把 v3 的复现强度自动外推到 v4 新增结论。

## 证据入口

- 规则挖掘器：[`../../analyze_mapping_rules.py`](../../analyze_mapping_rules.py)
- 完整机器可读结果：[`../../results/rule-mining/mapping_rule_analysis.json`](../../results/rule-mining/mapping_rule_analysis.json)
- 生成 manifest：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)
- 核心 SASS attribution 汇总：[`../../results/expanded/sass/sass_report.json`](../../results/expanded/sass/sass_report.json)；逐记录 `sass_attribution.jsonl` 不随 Git 发布，使用前须核对本页生成 JSON 中记录的输入 SHA-256
- 上下文统计：[`../../Docs/tcgen05_mma_上下文差分报告.md`](../../Docs/tcgen05_mma_上下文差分报告.md)
