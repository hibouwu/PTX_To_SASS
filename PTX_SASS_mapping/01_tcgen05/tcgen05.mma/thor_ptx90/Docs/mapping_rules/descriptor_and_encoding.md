# descriptor 与机器编码：完整逆向映射还缺哪一层

## 先说结论

当前文档已经能从 PTX 的操作码变体、限定符、操作数来源和上下文预测核心 SASS 文本及主要外围序列，但还不能仅凭静态编译结果解释 `idesc`、SMEM descriptor、zero-column-mask descriptor 内部每一个位域的语义。原因不是这些字段不重要，而是当前 case 把 descriptor 作为运行时参数装入 UR；核心机器指令编码记录的是“读取哪个 UR”，descriptor 的运行时数值并没有内嵌到这条 MMA 的 128-bit encoding 中。

因此完整映射必须分成两个彼此独立的层：

```text
PTX opcode/qualifier/operand contract
    → SASS opcode、modifier、操作数槽位、核心机器编码

descriptor runtime value
    → shape/type/layout/stride/swizzle/稀疏或缩放解释
    → 由 UR 中的数据驱动，不等于 MMA encoding word 的静态位域
```

把这两层混在一起会产生两种错误：一是把 descriptor 位误称为 MMA opcode 位；二是看到 dense 与 sparse 的规范化核心文本相同，就误判稀疏语义消失。

## 当前已经冻结的编码规则

下表来自 O3 `runtime_zero` 的同寄存器文本配对。分析器只接受具体寄存器文本完全相同、移除被测 modifier 后整条 SASS 操作也完全相同的候选 pair，因此 XOR 不混入寄存器重分配；等价源码拼写和重复实例会在同一独立 witness 组内形成多个候选 pair，不能把候选数误当独立证据数。

| PTX 变化 | SASS 变化 | 独立 witness 组 | 候选 pair | word 0 XOR | word 1 XOR | 位方向 |
|---|---|---:|---:|---:|---:|---|
| `.cta_group::1 → .cta_group::2` | 增加 `.2CTA` | 424 | 424 | `0x0000000000000000` | `0x0000000000200000` | 置位 |
| 无 `.ashift → .ashift` | 增加 `.ASHIFT` | 32 | 80 | `0x0000000000000000` | `0x0000000000000400` | 置位 |
| A discard→fill/keep | 增加 `.A_KEEP` | 176 | 1,264 | `0x0000000000000000` | `0x0000000000100000` | 置位 |
| B discard/lastuse→fill/use | 增加 `.B_KEEP` | 256 | 608 | `0x0000000000000000` | `0x0000000000020000` | 置位 |
| B0→B1/B2/B3 | 增加 `.BUFFER1/2/3` | 各 160 | 各 288 | `0x0000000000000000` | `0x0000000000008000/00010000/00018000` | 置位字段 |
| 非 4X→4X | 增加 `.4X` | 40 | 352 | `0x4000000000000000` | `0x0000000000000000` | 清位 |
| 非 WS→WS | 增加 `.WS` | 16 | 64 | `0x0000000000000000` | `0x0000000000080000` | 置位 |

`word 0/1` 按 `nvdisasm` 在 attribution 中输出的两个 64-bit word 顺序编号，不在这里换算成其他厂商文档或小端字节流的全局 bit 编号。`.4X` 的 PTX/SASS 变化在当前方向上清除 word 0 的该位，其余表中 modifier 置位；只报 XOR 会丢失这一方向信息。`A/B_REUSE` pair 除公共候选位外还会改变高位调度控制字段，尚不能按同一证据等级归纳为独立固定 XOR mask。完整 witness ID、左右 PTX/SASS/encoding 和 set/clear mask 见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)的 `encoding_bits` 字段。

## 已证明是机器编码级 alias 的 PTX 拼写

同一 semantic form 内共有 384 个 O3 source-spelling pair，384/384 的具体核心 SASS 文本和两个 encoding word 都完全相同：

| 仅改变的源码拼写 | pair | 编码相同 |
|---|---:|---:|
| 显式 collector discard 与缺省 discard | 160 | 160 |
| 等价 scale-vector 拼写 | 160 | 160 |
| 两类拼写同时改变 | 64 | 64 |

这说明逆向映射不能把“恢复 semantic form”和“恢复原始 PTX 文本”视为同一个目标。即使取得完整核心机器码，也无法区分这些等价 source spelling；逆向器应输出规范 PTX 或 alias 集合，而不应伪造唯一原始拼写。

## descriptor/地址操作数分层表

| 输入 | PTX 表现 | 核心 SASS 表现 | 值是否进入 MMA encoding | 当前可恢复内容 | 尚未恢复内容 |
|---|---|---|---|---|---|
| instruction descriptor | `%idesc` | `idesc[URn]` | 否，只编码 UR 槽位 | 存在性和寄存器类别 | shape、类型组合、转置/布局等内部位域 |
| A/B SMEM descriptor | `%desc_a/%desc_b` | `gdesc[URn]` | 否，只编码 UR 槽位 | A/B 来源类别和槽位 | base、leading dimension、stride、swizzle、布局位域 |
| zero-column-mask descriptor | `%zero_mask_desc` | WS 核心中的额外 `URn` | 否，只编码额外操作数槽位 | descriptor 是否存在 | mask 格式、地址和作用范围位域 |
| D/A/metadata TMEM address | `[%d_tmem]/[%a_tmem]/[%meta_tmem]` | `tmem[URn]` | 地址值不进入，只编码槽位 | TMEM 来源与某些角色关系 | 地址位宽、对齐、跨 CTA 分布和 metadata 解释 |
| scale-factor TMEM address | `[%scale_a_tmem]/[%scale_b_tmem]` | 额外 `tmem[URn]` | 地址值不进入，只编码槽位 | 是否启用 block scale | scale block 的运行时布局与地址解释 |

## 为什么核心文本不能唯一恢复所有 PTX 字段

O3 `runtime_zero` 的 1,648 个 occurrence 归一化为 300 种核心 SASS signature。`.ws`、CTA group、TS/SS、zero-column-mask 是否存在、collector 状态和 `.ashift` 在当前样本中都可以由 signature 唯一恢复；`.sp` 在 0/300 个 signature 上可唯一恢复，`kind` 只有 200/300 个 signature 可唯一恢复。详细矩阵和碰撞实例见 [`reverse_mapping_rules.md`](reverse_mapping_rules.md)。

最关键的多对一关系是：

```text
mma 与 mma.sp
    → 可产生同一规范化核心 SASS signature

f16 与 tf32
    → 可共享 UTCHMMA 文本家族，精细解释依赖 idesc

mxf4 与 mxf4nvf4、block32 与 scale_vec::2X
    → 部分形态汇合为同一 UTCOMMA signature

显式/缺省 alias
    → 核心文本和机器编码都相同
```

这意味着一个实用逆向器应返回候选约束集合，例如“`sparse ∈ {false,true}`”，而不是在证据不足时任选一个 PTX 形态。

## descriptor 位域的实验矩阵

静态编译矩阵不足以回答 descriptor 值语义，下一阶段需要在 Thor 实机上执行单因素 runtime probe。每一类 descriptor 都应固定已知可工作的基线，只改变一个合法字段或一个候选 bit，并同时记录编译、反汇编、执行结果和错误状态。

| probe 族 | 固定项 | 单因素扫描 | 主要观测 | 成功判据 |
|---|---|---|---|---|
| `idesc` | opcode/qualifier、A/B 数据、地址、collector、CTA group | 已知合法 shape/type/layout 字段；必要时对候选位做 walking-bit | D 的数值和写入范围、异常/非法指令 | 字段变化与数值/覆盖区域存在可重复的一一对应 |
| SMEM descriptor | kind、idesc、矩阵数据、shared-memory allocation | base、leading dimension、stride、swizzle、layout | 读取元素位置和输出数值 | 每个字段可由地址置换或结果置换唯一辨识 |
| sparse metadata | dense 数值、idesc、A/B descriptor | metadata TMEM 内容和地址字段 | 稀疏选择模式与 D 数值 | metadata 模式变化只影响预测的非零位置 |
| zero-column-mask | WS 形态、B collector、数据和 idesc | descriptor 字段与 mask payload | 被抑制列和输出范围 | mask 位与输出列形成稳定映射 |
| block scale | kind、idesc、A/B 原始值 | scale address、block size、scale-vector 模式 | 分块后的数值倍率 | 每个 block 的倍率和寻址符合唯一规则 |

walking-bit 不能直接从全零开始，因为任意位组合可能非法。更安全的方法是从一个已验证的合法 descriptor 基线出发，对已知字段采用合法枚举，对未知字段先做单比特翻转并把“正常执行、结果改变、结果不变、trap/launch failure”分别记录。

## 每条新规则必须保存的证据

| 字段 | 含义 |
|---|---|
| `toolchain` | `ptxas`、driver、`nvdisasm` 版本和 `sm_110a` 目标 |
| `ptx_form` | 完整 opcode、qualifier、操作数契约和上下文 |
| `descriptor_role` | `idesc/desc_a/desc_b/meta/zero_mask/scale` |
| `baseline_value` / `treatment_value` | 两个完整 32/64-bit 值 |
| `changed_mask` | 两值 XOR，避免只写十进制差值 |
| `core_sass` / `encoding_words` | 核心文本和两个原始 word |
| `runtime_status` | success、compile reject、launch failure、trap、timeout |
| `output_digest` | 完整输出或稳定 hash，并保存差异位置 |
| `replicates` | 重复次数和是否稳定 |
| `inferred_rule` | 可预测规则、适用条件和反例数 |

只有同时具备单因素 pair、重复执行和零反例适用域，结论才升级为“确定性 descriptor 规则”；仅凭某一条正常执行样本只能标为观察结果。

## 完整映射的完成标准

| 层 | 当前状态 | 完成条件 |
|---|---|---|
| PTX grammar 与合法组合 | 已覆盖主要形态 | 阴性探针覆盖所有组合边界 |
| 核心 SASS 文本选择 | 已形成主要零反例规则 | 新增形态进入自动回归，不靠人工例子 |
| 外围 lowering | guard/issuer/identity producer/completion 已系统化 | 扩展非恒等 producer 和更多 issuer 模式 |
| 核心机器编码 | 已隔离 `.2CTA`、`.ASHIFT`、`.A/B_KEEP`、B buffer、`.4X`、`.WS`，alias 已验证 | 继续分离 opcode、`A/B_REUSE`、predicate、kind/scale 隐式模式和寄存器槽位 bitfield |
| descriptor runtime semantics | 尚未开始实机位域扫描 | 完成 `idesc`、SMEM descriptor、metadata、zero mask、block scale 的合法字段矩阵 |
| 逆映射 | 已量化核心文本的可恢复率 | 合并核心编码、外围序列和 descriptor 值，输出唯一值或候选集合 |

因此，当前资料已经是一套较完整的“静态指令选择与外围 lowering 规则”，但还不是完整 Thor ISA 编码手册。真正剩余的核心工作是机器编码 bitfield 和 descriptor 运行时语义，而不是继续堆更多相似反汇编例子。
