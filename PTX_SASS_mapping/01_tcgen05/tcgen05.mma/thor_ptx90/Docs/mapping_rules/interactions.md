# 修饰符联合作用：多个维度如何拼成完整编译降级

## 为什么需要这一页

单个规则条目回答“一个维度通常映射到哪里”，但 `tcgen05.mma` 的修饰符不是一组可以任意排列组合的开关。它们限制彼此的适用范围，有些信息还只在操作数或机器编码中体现。

完整分析应先判断组合是否合法，再按层解释编译降级。

## 推荐的阅读顺序

```text
1. kind
   选择 UTCHMMA / UTCQMMA / UTCIMMA / UTCOMMA

2. CTA group
   group 2 增加 .2CTA

3. 变体
   WS 增加 .WS；SP 不产生同名 .SP

4. 分块缩放
   某些规范形态选择不同操作码家族或增加 .4X

5. ashift
   合法 TS 形态增加 .ASHIFT

6. 操作数来源与 collector
   决定 tmem/gdesc 和 KEEP/REUSE/BUFFERn

7. 上下文
   决定谓词、寄存器编号和核心指令前后的外围序列
```

这个顺序是分析方法，不表示 SASS 文本必须严格按同样顺序书写所有字段。

## 组合约束表

| 维度 | 可以和什么组合 | 关键限制 |
|---|---|---|
| `.cta_group::2` | 普通 MMA、合法 TS/SS | WS 固定为 group 1 |
| `.ws` | B collector、合法 kind | 使用 B collector，不使用普通 A collector |
| `.sp` | 普通或 WS 变体 | 没有可见同名 `.SP`；需看 metadata 操作数契约和完整 producer，核心编码可能碰撞 |
| `.ashift` | 普通 TS MMA、CTA group 1/2 | A 必须来自 TMEM；不能分块缩放 |
| A collector | 普通 MMA | 状态序列必须合法 |
| B collector | WS MMA | buffer 为 b0–b3；状态序列必须合法 |
| 分块缩放 | 对应的低精度 kind | scale vector、别名和 `idesc.K` 联合解释 |

## 基础限定符与操作数契约

撤掉单维度条目后，kind、CTA group、`.ashift` 和 TS/SS 的完整入口集中在这里；更长的函数级例子见[综合报告](../tcgen05_mma_PTX到SASS映射规则报告.md)。

| PTX 维度 | 核心 SASS 规则 | 操作数或外围规则 | 已隔离编码 |
|---|---|---|---|
| 标准 kind | `f16/tf32 → UTCHMMA`；`f8f6f4 → UTCQMMA`；`i8 → UTCIMMA` | 不单独选择外围指令；更细类型仍依赖 `idesc` | word 1 `[9:8]`；`f16/tf32 = 00`、`i8 = 01`、`f8f6f4 = 11` |
| `.cta_group::2` | 增加 `.2CTA` | mask 从 4 个变为 8 个；completion 使用 `UTCBAR.2CTA`；WS 只允许 group 1 | word 1 置位 `0x0000000000200000` |
| TS | A 为 `tmem[URn]`，B 为 `gdesc[URn]` | A 使用 32-bit TMEM 地址生产链 | A 槽位仍为 word 0 `[31:24]` |
| SS | A/B 均为 `gdesc[URn]` | A 使用 64-bit SMEM descriptor 生产链 | A/B 槽位分别为 word 0 `[31:24]`/`[39:32]` |
| `.ashift` | 增加 `.ASHIFT` | 不增加独立外围指令；只允许普通 TS MMA | word 1 置位 `0x0000000000000400` |

CTA group 的 mask 与完成协议必须同时解释：带输出禁用 lane mask 的普通非 block-scale、非 WS 形态中，group 1 使用 4 个 mask，group 2 使用 8 个；带 completion 时 `UTCBAR → UTCBAR.2CTA`。阴性探针确认 `.cta_group::0/3/4`、WS + group 2、group 1 错误 mask 数和 group 2 错误 mask 数都会被拒绝。

`.ashift` 的两个核心合法性条件是“普通非 WS 变体”和“A 来自 TMEM”。阴性探针分别确认 block scaling + `.ashift`、SMEM descriptor + `.ashift` 和 WS + `.ashift` 被 `ptxas` 拒绝。合法形态可以与 CTA group 1/2、标准 kind、稀疏变体和 A collector 组合；其 SASS 影响仍是核心 `.ASHIFT` 原位修饰符。

标准 kind 的上述两位字段不构成全部 block-scale opcode：`UTCOMMA/UTCQMMA` 还联合使用 word 0 的 opcode 子字段。完整 composite、方向和见证数见 [`descriptor_and_encoding.md`](descriptor_and_encoding.md)及 [`reverse_mapping_rules.md`](reverse_mapping_rules.md)。

## 三个典型组合

### 1. kind + CTA group + TS + `.ashift`

```text
kind::f16 + cta_group::2 + TS + ashift
→ UTCHMMA.2CTA.ASHIFT tmem[...], gdesc[...], ...
```

四个维度分别决定操作码家族、`.2CTA`、A/B 操作数类型和 `.ASHIFT`。

### 2. WS + B2 collector use

```text
mma.ws + collector::b2::use
→ UTCHMMA.WS ... gdesc[...].B_REUSE.B_KEEP.BUFFER2 ...
```

`.WS` 位于主助记符，collector 状态位于 B 操作数。只比较助记符会遗漏 `use` 和 `fill` 的差别。

### 3. 稀疏 + WS

```text
mma.ws.sp
→ UTC*MMA.WS ...
```

可见 `.WS`，但没有同名 `.SP`。稀疏语义由额外 metadata 及其完整 producer/参数数据流承载，并可能影响操作数位置或机器编码；某些 pair 的规范化核心文本和编码仍完全相同。`.ws.sp` 不能被解释成字符串 `.WS.SP`，也不能只靠核心 SASS 与 `mma.ws` 唯一区分。

## 哪些维度不是独立效应

### `.sp` 是隐藏效应

`.sp` 不改变为同名主操作码修饰符。必须把稀疏 metadata 操作数契约和完整 producer 纳入比较，否则会错误得出“`.sp` 没有作用”的结论。具体核心编码可能因 metadata 槽位和寄存器分配而变化，但 dense/sparse pair 也可能完全碰撞，因此不存在已证明可独立恢复 `.sp` 的核心 opcode bit。

### 分块缩放是 kind、scale vector 和描述符的联合效应

`scale_vec::2X` 与 `block32` 没有同名 SASS 后缀；`scale_vec::4X` 和某些 `block16` 形态可见 `.4X`。这些规则依赖合法 kind 和描述符条件。

### collector 是状态机，不是单条无状态修饰符

`use` 和 `lastuse` 依赖先前的 `fill`。单独摘出第二条指令虽然能读出 `REUSE`/`KEEP`，却不足以证明整段 PTX 合法。

## 上下文与核心规则怎样相遇

外围上下文通常不改操作码家族，但仍能改变机器代码：

| 上下文维度 | 主要影响 |
|---|---|
| `enable-input-d` 常量 | 核心 MMA 的输入 D 谓词可折叠为 `UPT`/`!UPT` |
| PTX guard | 核心谓词或外围控制流；详见 [`context_lowering.md`](context_lowering.md) |
| lane/CTA-thread issuer | 发射控制、活跃寄存器和寄存器编号；详见 [`context_lowering.md`](context_lowering.md) |
| derived producer | 恒等链在 O1–O3 消除；非恒等、分支和 global-load 保留外围数据流；详见 [`context_lowering.md`](context_lowering.md) |
| completion | 核心 MMA 后的提交、屏障和等待序列 |

`UPT` 是统一谓词恒真；`!UPT` 是其取反。64,548 组上下文配对中，没有观察到上下文改变核心 MMA 的操作码家族，但寄存器编号、活跃集合、外围指令、predicate/modifier 和编码仍可能变化。详细统计见 [`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)。

## 哪些修饰符会波及外围 SASS

下面的“外围”指去掉目标 MMA 后的参数装载、谓词、选举、分支和完成协议。“有条件”表示只在部分上下文或优化级发生，不表示结果不稳定。

选择外围指令时，可以先判断 PTX 是否改变了操作数契约：

```text
只改变 MMA 编码模式
    collector / ashift / scale_vec 2X↔4X
    → 不选择新的外围指令

增加或替换 64 位描述符
    SS A / zero-column-mask
    → 直接参数：LDCU.64
    → derived producer：LDC.64 + MOV/R2UR

增加 32 位 TMEM 或 scale address
    TS A / block scaling
    → 直接参数：LDCU，两个相邻地址可合并为 LDCU.64
    → derived producer：LDC + IADD3

增加 输出禁用 lane 掩码
    CTA group 1→2
    → MOV/UMOV + R2UR
    → 需要位逻辑时选择 LOP3.LUT

改变完成协议范围
    CTA group 1→2
    → UTCBAR → UTCBAR.2CTA
```

`NOP` 不在这个语义选择树中，因为它是编译器根据最终调度间隔插入的填充，不是某个 PTX 修饰符的语义实现指令。

总结表：

| 维度 | 核心 MMA | 外围指令数/类型 | 核心寄存器/活跃数 | 最准确的理解模型 |
|---|---|---|---|---|
| 非分块 kind | 操作码或描述符解释变化 | 不变 | 不变 | 原位选择计算家族 |
| CTA group 2 | 增加 `.2CTA` | 有条件变化 | 有条件变化 | 核心模式加 mask/完成协议变化 |
| `.sp` | metadata 操作数，不显示 `.SP`；核心编码可能碰撞 | 总会改变类型，数量有时改变 | 有条件变化 | 稀疏操作数契约 |
| `.ws` | 增加 `.WS` | 有条件变化 | 有条件变化 | collector 和操作数契约共同变化 |
| zero-column-mask 描述符 | 描述符操作数或其值 | 总会改变类型，数量有时改变 | 通常变化 | WS 可选操作数契约 |
| TS/SS | `tmem` 对 `gdesc` | 总会改变类型，数量有时改变 | 总会改变 | A 来源契约变化 |
| collector | `KEEP`/`REUSE`/`BUFFERn` | 不变 | 不变 | 原位操作数修饰符 |
| 启用分块缩放 | 操作码加 scale-factor 操作数 | 总会改变类型，数量有时改变 | 总会改变 | scale-factor 操作数契约 |
| `scale_vec::2X`/`4X` | 可见 `.4X` 或隐式编码 | 不变 | 不变 | 分块家族内的原位模式 |
| `.ashift` | 增加 `.ASHIFT` | 不变 | 不变 | 原位 MMA 修饰符 |

关键分界不是“PTX 上有没有点号修饰符”，而是它是否改变操作数契约：

- 只改变核心编码字段的修饰符，通常不会生成外围指令。
- 新增、删除或改变操作数宽度/类别的修饰符，会改变参数装载和寄存器分配。
- CTA group 还会改变 mask 数量和 completion 指令，因此处在两者之间。

## 真实组合见证

下面列出 expanded 结果中的真实 O3 见证：

| case | 联合维度 | 核心 SASS 结果 |
|---|---|---|
| `THOR_MMA_001641` | sparse + INT8 + TS + group 2 + ashift | `UTCIMMA.2CTA.ASHIFT tmem[...]` |
| `THOR_MMA_000633` | group 2 + TS + A collector lastuse + ashift | `UTCHMMA.2CTA.ASHIFT tmem[...].A_REUSE` |
| `THOR_MMA_007129` | WS + sparse + B2 fill→use | `UTCHMMA.WS ... B_REUSE.B_KEEP.BUFFER2` |
| `THOR_MMA_007265` | WS + sparse + B2 + zero-column-mask | `UTCHMMA.WS ... BUFFER2 ..., UR12, UP0` |
| `THOR_MMA_003145` | block scale + TS + group 2 + 4X | `UTCOMMA.2CTA.4X ... tmem[scale-factor]` |

这些见证覆盖可见修饰符、隐藏稀疏语义、操作数修饰符、可选描述符和新增 scale-factor 操作数五种不同承载位置。非法边界则由文法约束或阴性探针验证（`WS + group 2`、`SS + ashift`、`block scale + ashift`）。

## 代表性覆盖口径

| 主要机制 | 覆盖位置 |
|---|---|
| kind、CTA group、变体、分块缩放、ashift 的组合顺序 | 阅读顺序与真实见证 |
| SS/TS 与 A/B collector 的操作数归属 | 组合表与真实见证 |
| `.sp`、2X、描述符等隐藏效应 | 非独立效应与见证 |
| 原位编码与操作数契约变化 | 外围选择树 |
| guard、issuer、producer、enable、completion 上下文 | 上下文表与 64,548 组比较 |
| 合法与非法组合边界 | 约束表和阴性探针 |
| 核心、外围、寄存器、编码的分层解释 | 总结表 |

当前清单中的跨维度主要静态机制均有规则、真实案例和边界证据。v4 已补 guard/enable 全编号、opcode composite、REUSE、隐式 alias、寄存器槽位、idesc 压力见证以及扩展 producer/issuer；任意 CFG 和任意 producer 仍是开放的编译器输入空间，因此继续按机制清单而不是虚构总体百分比报告覆盖。

## 完整阴性探针目录

下面 30 项逐一对应 Thor v4 `negative_probe_summary.json` 中的 probe ID。它们验证的是 `ptxas` 可静态判定的语法、限定符和操作数契约边界；得到预期拒绝不等于验证了所有运行时 descriptor 值或生命周期错误。

### Qualifier、variant 与 kind/scale 边界

| probe ID | 有意构造的被拒绝或域外形态 | Thor `ptxas` 结论 |
|---|---|---|
| `scale_input_d` | 在 `sm_110a` 使用不受支持的 `scale-inp-d-imm` | feature not supported |
| `block_scale_with_ashift` | block scaling 与 `.ashift` 同时使用 | illegal `.ashift` |
| `smem_descriptor_with_ashift` | A 为 SMEM descriptor 时使用 `.ashift` | illegal `.ashift` |
| `ws_cta_group_2` | WS 与 `.cta_group::2` 组合 | illegal CTA group |
| `mxf4nvf4_omits_scale_vector` | `mxf4nvf4` 省略必需的 scale-vector 限定符 | requires scale vector |
| `mxf8f6f4_scale_vec_2x` | `mxf8f6f4` 与 `scale_vec::2X` 组合 | qualifiers cannot be combined |
| `mxf4_scale_vec_1x` | `mxf4` 与 `scale_vec::1X` 组合 | qualifiers cannot be combined |
| `ws_block_scale` | WS 变体使用 block scaling 操作数契约 | arguments mismatch |
| `cta_group_3` | 使用 `.cta_group::3` | unknown modifier |
| `cta_group_0` | 使用 `.cta_group::0` | unknown modifier |
| `cta_group_4` | 使用 `.cta_group::4` | unknown modifier |
| `unsupported_kind_bf16` | 使用未定义的 `.kind::bf16` | unknown modifier |
| `standard_kind_with_block_scale` | 标准 `f16` kind 与 `.block_scale` 组合 | qualifiers cannot be combined |
| `mxf4nvf4_scale_vec_1x` | `mxf4nvf4` 与 `scale_vec::1X` 组合 | qualifiers cannot be combined |
| `mxf8f6f4_block16` | `mxf8f6f4` 与 `.block16` 组合 | qualifiers cannot be combined |
| `mxf4_scale_vec_8x` | 使用不存在的 `scale_vec::8X` | unknown modifier |
| `ws_with_ashift` | WS 与 `.ashift` 同时使用 | illegal `.ashift` |

### Collector 状态与角色边界

| probe ID | 有意构造的被拒绝或域外形态 | Thor `ptxas` 结论 |
|---|---|---|
| `normal_uses_b_collector` | 普通 `mma` 使用 B collector | illegal B collector |
| `ws_uses_a_collector` | `mma.ws` 使用 A collector | illegal A collector |
| `invalid_collector_operation` | 使用不存在的 `collector::a::reuse` 动作 | unknown modifier |
| `invalid_ws_buffer_b4` | WS 使用不存在的 B4 buffer | unknown modifier |
| `sparse_uses_b_collector` | 非 WS 的 `mma.sp` 使用 B collector | illegal B collector |
| `ws_sparse_uses_a_collector` | `mma.ws.sp` 使用 A collector | illegal A collector |

### 必需、冗余和向量操作数边界

| probe ID | 有意构造的被拒绝或域外形态 | Thor `ptxas` 结论 |
|---|---|---|
| `missing_idesc_standard` | 标准 MMA 缺少 `idesc` | arguments mismatch |
| `missing_enable_standard` | 标准 MMA 缺少 enable 谓词 | arguments mismatch |
| `cta_group_1_wrong_mask_count` | group 1 只提供 3 个输出禁用 lane mask | illegal vector size |
| `cta_group_2_wrong_mask_count` | group 2 提供错误数量的 mask | argument vector size mismatch |
| `unexpected_standard_operand` | 标准 MMA 多出一个操作数 | arguments mismatch |
| `missing_sparse_metadata` | `.sp` 形态缺少 metadata | arguments mismatch |
| `missing_block_scale_operand` | block-scale 形态缺少必需的 scale-factor 操作数 | arguments mismatch |

三张表合计 17+6+7=30 项，报告状态为 30/30 得到预期拒绝。完整 PTX、错误行、原始诊断、工具链摘要和预期正则表达式见 [`negative_probe_summary.json`](../../validation/negative_probe_summary.json)及 [`negative_probe_report.json`](../../results/negative-probes/negative_probe_report.json)。未列入这些表的组合只能称为“未覆盖”，不能由邻近拒绝样本外推出非法。

## 写映射规则时应使用的措辞

- 可以写："在当前覆盖的合法样本中，`.cta_group::2 → .2CTA`，零反例。"
- 应写：“`.sp` 没有可见同名修饰符；metadata 操作数和完整 producer 承载稀疏契约，核心编码可能与 dense 碰撞。”
- 应写："`scale_vec::4X → .4X` 受 kind 和规范形态约束。"
- 不应写：“所有 PTX 修饰符都一对一变成同名 SASS 修饰符。”
- 不应写：“核心助记符相同就说明完整机器代码相同。”

## 最终检查清单

分析一条新的编译降级时，依次确认：

1. PTX 变体和 kind 是否属于已覆盖集合。
2. CTA group 与 WS 是否兼容。
3. A/B 来源是 TS 还是 SS。
4. 分块缩放、`.ashift` 是否满足条件。
5. collector 是否有合法的前序状态。
6. 稀疏 metadata 和 scale-factor 操作数是否完整。
7. 核心 SASS 的操作码、修饰符和操作数是否分别对应。
8. 差异是否其实来自 guard、issuer、producer、enable 或 completion。
9. 若目标是逆映射，核心 SASS 是否存在多对一碰撞，是否需要结合完整 kernel、encoding word 或 descriptor 参数契约；见 [`reverse_mapping_rules.md`](reverse_mapping_rules.md)和 [`descriptor_and_encoding.md`](descriptor_and_encoding.md)。

## 附录：合并前核心维度的完整 PTX/SASS 片段

本附录逐块保留合并前四份基础维度文档中的 fenced 片段。片段正文保持原样；标题只记录原文件、原章节和块编号，方便从新结构回查旧版内容。

原代表 witness 索引：

| case ID | 原文档 | 原章节 |
|---|---|---|
| `THOR_MMA_000001` | `cta_group.md` | 对比 1：`runtime_zero`——纯核心基线 |
| `THOR_MMA_000003` | `cta_group.md` | 对比 2：`enable_true_mask_ones`——4 个 mask 对 8 个 mask |
| `THOR_MMA_000007` | `cta_group.md` | 对比 3：`derived_producers`——生产链能否被消去 |
| `THOR_MMA_000008` | `cta_group.md` | 对比 4：`commit_completion`——完成协议选择 |
| `THOR_MMA_000417` | `cta_group.md` | 对比 1：`runtime_zero`——纯核心基线 |
| `THOR_MMA_000419` | `cta_group.md` | 对比 2：`enable_true_mask_ones`——4 个 mask 对 8 个 mask |
| `THOR_MMA_000423` | `cta_group.md` | 对比 3：`derived_producers`——生产链能否被消去 |
| `THOR_MMA_000424` | `cta_group.md` | 对比 4：`commit_completion`——完成协议选择 |
| `THOR_MMA_000953` | `cta_group.md` | 对比 5：稀疏 INT8——跨变体、操作码与活跃寄存器 |
| `THOR_MMA_001369` | `cta_group.md` | 对比 5：稀疏 INT8——跨变体、操作码与活跃寄存器 |
| `THOR_MMA_002345` | `cta_group.md` | 对比 6：分块缩放 4X——无 mask 的正交修饰符组合 |
| `THOR_MMA_003145` | `cta_group.md` | 对比 6：分块缩放 4X——无 mask 的正交修饰符组合 |
| `THOR_MMA_000078` | `ashift.md` | 直接映射 |
| `THOR_MMA_000161` | `ashift.md` | `.ASHIFT` 的已隔离机器编码位 |
| `THOR_MMA_000201` | `ashift.md` | `.ASHIFT` 的已隔离机器编码位 |
| `THOR_MMA_000329` | `ashift.md` | 跨形态代表例子 |
| `THOR_MMA_000393` | `ashift.md` | 跨形态代表例子 |
| `THOR_MMA_000633` | `ashift.md` | 跨形态代表例子 |
| `THOR_MMA_001225` | `ashift.md` | 跨形态代表例子 |
| `THOR_MMA_001641` | `ashift.md` | 跨形态代表例子 |
| `THOR_MMA_000833` | `operand_source.md` | 跨变体的来源见证 |
| `THOR_MMA_000993` | `operand_source.md` | 跨变体的来源见证 |
| `THOR_MMA_001665` | `operand_source.md` | 跨变体的来源见证 |
| `THOR_MMA_002065` | `operand_source.md` | 跨变体的来源见证 |
| `THOR_MMA_004865` | `operand_source.md` | 跨变体的来源见证 |
| `THOR_MMA_005953` | `operand_source.md` | 跨变体的来源见证 |

### `kind_and_opcode.md`

#### 原章节“PTX 语法位置”· 片段 1

```ptx
tcgen05.mma.cta_group::1.kind::f16 ...
tcgen05.mma.cta_group::1.kind::tf32 ...
tcgen05.mma.cta_group::1.kind::i8 ...
```

#### 原章节“最小例子”· 片段 2

```ptx
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

#### 原章节“最小例子”· 片段 3

```sass
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0 ;
```

#### 原章节“与其他维度组合”· 片段 4

```text
cta_group::2 → .2CTA
ws           → .WS
ashift       → .ASHIFT
4X 形态      → .4X（仅适用的 UTCOMMA 形态）
```

#### 原章节“与其他维度组合”· 片段 5

```text
kind::f16 + cta_group::2 + ashift
→ UTCHMMA.2CTA.ASHIFT
```

#### 原章节“kind 是否改变外围 SASS”· 片段 6

```text
f16 / tf32
    → UTCHMMA

f8f6f4 / mxf8f6f4
    → UTCQMMA

i8
    → UTCIMMA

mxf4 / mxf4nvf4
    → UTCOMMA
```

#### 原章节“kind 是否改变外围 SASS”· 片段 7

```ptx
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

tcgen05.mma.cta_group::1.kind::tf32
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

tcgen05.mma.cta_group::1.kind::f8f6f4
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

tcgen05.mma.cta_group::1.kind::i8
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.scale_vec::4X
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;
```

#### 原章节“kind 是否改变外围 SASS”· 片段 8

```sass
// kind::f16 或 kind::tf32
UTCHMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// kind::f8f6f4
UTCQMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// kind::i8
UTCIMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// kind::mxf4nvf4 + scale_vec::4X
UTCOMMA.4X  gdesc[UR8], gdesc[UR10],
             tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR12], UP0;
```

#### 原章节“kind 是否改变外围 SASS”· 片段 9

```ptx
tcgen05.mma.cta_group::1.kind::f8f6f4
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

tcgen05.mma.cta_group::1.kind::i8
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

#### 原章节“kind 是否改变外围 SASS”· 片段 10

```sass
// kind::f8f6f4，O0
UTCQMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;

// kind::f8f6f4，O3
UTCQMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// kind::i8，O0
UTCIMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;

// kind::i8，O3
UTCIMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

### `cta_group.md`

#### 原章节“映射规则”· 片段 1

```text
UTCHMMA       ← cta_group::1
UTCHMMA.2CTA  ← cta_group::2

UTCQMMA       ← cta_group::1
UTCQMMA.2CTA  ← cta_group::2
```

#### 原章节“PTX 与 SASS 对照”· 片段 2

```ptx
tcgen05.mma.cta_group::2.kind::f16.ashift
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
```

#### 原章节“PTX 与 SASS 对照”· 片段 3

```sass
UTCHMMA.2CTA.ASHIFT
    tmem[UR7], gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], UP0 ;
```

#### 原章节“CTA group 是否改变外围 SASS”· 片段 4

```text
tcgen05.mma.cta_group::1
    → UTC*MMA

tcgen05.mma.cta_group::2
    → UTC*MMA.2CTA

保留下来的 completion for CTA group 1
    → UTCBAR

保留下来的 completion for CTA group 2
    → UTCBAR.2CTA
```

#### 原章节“CTA group 是否改变外围 SASS”· 片段 5

```text
.cta_group::2
    → 核心 MMA 增加 .2CTA
    → completion 的 UTCBAR 选择 .2CTA 版本
    → 如果额外 4 个 mask 未被常量折叠，则选择更多 MOV/R2UR/UMOV
```

#### 原章节“对比 1：`runtime_zero`——纯核心基线”· 片段 6

```ptx
// THOR_MMA_000001，group 1
mov.b32 %mask0, 0;
mov.b32 %mask1, 0;
mov.b32 %mask2, 0;
mov.b32 %mask3, 0;
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

// THOR_MMA_000417，group 2
mov.b32 %mask0, 0;
mov.b32 %mask1, 0;
mov.b32 %mask2, 0;
mov.b32 %mask3, 0;
mov.b32 %mask4, 0;
mov.b32 %mask5, 0;
mov.b32 %mask6, 0;
mov.b32 %mask7, 0;
tcgen05.mma.cta_group::2.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
```

#### 原章节“对比 1：`runtime_zero`——纯核心基线”· 片段 7

```sass
// group 1
UTCHMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;

// group 2
UTCHMMA.2CTA gdesc[UR4], gdesc[UR6],
              tmem[UR18], tmem[UR16], idesc[UR17], UR8, UP0;
```

#### 原章节“对比 1：`runtime_zero`——纯核心基线”· 片段 8

```sass
// group 1
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// group 2
UTCHMMA.2CTA gdesc[UR8], gdesc[UR10],
              tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

#### 原章节“对比 2：`enable_true_mask_ones`——4 个 mask 对 8 个 mask”· 片段 9

```ptx
// group 1：THOR_MMA_000003
setp.eq.u32 %enable, 0, 0;
mov.b32 %mask0, 0xffffffff;
mov.b32 %mask1, 0xffffffff;
mov.b32 %mask2, 0xffffffff;
mov.b32 %mask3, 0xffffffff;
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

// group 2：THOR_MMA_000419
setp.eq.u32 %enable, 0, 0;
mov.b32 %mask0, 0xffffffff;
mov.b32 %mask1, 0xffffffff;
mov.b32 %mask2, 0xffffffff;
mov.b32 %mask3, 0xffffffff;
mov.b32 %mask4, 0xffffffff;
mov.b32 %mask5, 0xffffffff;
mov.b32 %mask6, 0xffffffff;
mov.b32 %mask7, 0xffffffff;
tcgen05.mma.cta_group::2.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
```

#### 原章节“对比 2：`enable_true_mask_ones`——4 个 mask 对 8 个 mask”· 片段 10

```sass
// group 1
MOV  R3, 0xffffffff;
MOV  R6, 0xffffffff;
MOV  R7, 0xffffffff;
MOV  R8, 0xffffffff;
R2UR UR12, R10;
R2UR UR13, R11;
R2UR UR14, R12;
R2UR UR15, R8;
UTCHMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;

// group 2
MOV  R4,  0xffffffff;
MOV  R5,  0xffffffff;
MOV  R6,  0xffffffff;
MOV  R7,  0xffffffff;
MOV  R8,  0xffffffff;
MOV  R9,  0xffffffff;
MOV  R10, 0xffffffff;
MOV  R11, 0xffffffff;
R2UR UR8,  R13;
R2UR UR9,  R14;
R2UR UR10, R15;
R2UR UR11, R16;
R2UR UR12, R8;
R2UR UR13, R9;
R2UR UR14, R10;
R2UR UR15, R11;
UTCHMMA.2CTA gdesc[UR4], gdesc[UR6],
              tmem[UR18], tmem[UR16], idesc[UR17], UR8, UP0;
```

#### 原章节“对比 2：`enable_true_mask_ones`——4 个 mask 对 8 个 mask”· 片段 11

```sass
// group 1
UMOV UR12, 0xffffffff;
UMOV UR13, 0xffffffff;
UMOV UR14, 0xffffffff;
UMOV UR15, 0xffffffff;
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UR12, UPT;

// group 2
UMOV UR8,  0xffffffff;
UMOV UR9,  0xffffffff;
UMOV UR10, 0xffffffff;
UMOV UR11, 0xffffffff;
UMOV UR12, 0xffffffff;
UMOV UR13, 0xffffffff;
UMOV UR14, 0xffffffff;
UMOV UR15, 0xffffffff;
UTCHMMA.2CTA gdesc[UR16], gdesc[UR18],
              tmem[UR6], tmem[UR4], idesc[UR5], UR8, UPT;
```

#### 原章节“对比 3：`derived_producers`——生产链能否被消去”· 片段 12

```ptx
// 两个 group 共用的 identity producer
add.u32 %d_tmem, %d_tmem, 0;
add.u32 %a_tmem, %a_tmem, 0;
xor.b64 %desc_a, %desc_a, 0;
or.b64  %desc_b, %desc_b, 0;
xor.b32 %idesc, %idesc, 0;

// group 1：THOR_MMA_000007
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

// group 2：THOR_MMA_000423
tcgen05.mma.cta_group::2.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
```

#### 原章节“对比 3：`derived_producers`——生产链能否被消去”· 片段 13

```sass
// group 1：identity producer 已消去
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// group 2：identity producer 已消去
UTCHMMA.2CTA gdesc[UR8], gdesc[UR10],
              tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

#### 原章节“对比 4：`commit_completion`——完成协议选择”· 片段 14

```ptx
// group 1：THOR_MMA_000008
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%mbar];

// group 2：THOR_MMA_000424
tcgen05.mma.cta_group::2.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
tcgen05.commit.cta_group::2.mbarrier::arrive::one.b64 [%mbar];
```

#### 原章节“对比 4：`commit_completion`——完成协议选择”· 片段 15

```sass
// group 1
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;
LDCU.64 UR4, c[0x0][0x3b8];
UMOV     UR4, UR4;
UTCBAR  [UR4], URZ;

// group 2
UTCHMMA.2CTA gdesc[UR8], gdesc[UR10],
              tmem[UR6], tmem[UR4], idesc[UR5], UP0;
LDCU.64     UR4, c[0x0][0x3b8];
UMOV         UR4, UR4;
UTCBAR.2CTA [UR4], URZ;
```

#### 原章节“对比 5：稀疏 INT8——跨变体、操作码与活跃寄存器”· 片段 16

```ptx
// group 1：THOR_MMA_000953
tcgen05.mma.sp.cta_group::1.kind::i8
    [%d_tmem], %desc_a, %desc_b, [%meta_tmem], %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

// group 2：THOR_MMA_001369
tcgen05.mma.sp.cta_group::2.kind::i8
    [%d_tmem], %desc_a, %desc_b, [%meta_tmem], %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
```

#### 原章节“对比 5：稀疏 INT8——跨变体、操作码与活跃寄存器”· 片段 17

```sass
// group 1；核心处 live：GPR 1、UGPR 11、P 1、UP 1
UTCIMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;

// group 2；核心处 live：GPR 1、UGPR 15、P 1、UP 1
UTCIMMA.2CTA gdesc[UR4], gdesc[UR6],
              tmem[UR18], tmem[UR16], idesc[UR17], UR8, UP0;
```

#### 原章节“对比 5：稀疏 INT8——跨变体、操作码与活跃寄存器”· 片段 18

```sass
// group 1；核心处 live：GPR 1、UGPR 7、P 2、UP 1
UTCIMMA gdesc[UR6], gdesc[UR8],
         tmem[UR4], tmem[UR10], idesc[UR11], UP0;

// group 2；核心处 live：GPR 1、UGPR 7、P 2、UP 1
UTCIMMA.2CTA gdesc[UR6], gdesc[UR8],
              tmem[UR4], tmem[UR10], idesc[UR11], UP0;
```

#### 原章节“对比 6：分块缩放 4X——无 mask 的正交修饰符组合”· 片段 19

```ptx
// group 1：THOR_MMA_002345
tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.scale_vec::4X
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;

// group 2：THOR_MMA_003145
tcgen05.mma.cta_group::2.kind::mxf4nvf4.block_scale.scale_vec::4X
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;
```

#### 原章节“对比 6：分块缩放 4X——无 mask 的正交修饰符组合”· 片段 20

```sass
// group 1
UTCOMMA.4X tmem[UR7], gdesc[UR8],
            tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR10], UP0;

// group 2
UTCOMMA.2CTA.4X tmem[UR7], gdesc[UR8],
                 tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR10], UP0;
```

#### 原章节“`.2CTA` 的已隔离机器编码位”· 片段 21

```text
word 0 XOR = 0x0000000000000000
word 1 XOR = 0x0000000000200000
```

### `ashift.md`

#### 原章节“先说结论”· 片段 1

```text
PTX:  tcgen05.mma...ashift
SASS: UTC*MMA...ASHIFT
```

#### 原章节“直接映射”· 片段 3

```sass
// THOR_MMA_000078，O0
UTCHMMA.2CTA.ASHIFT
    tmem[UR17], gdesc[UR4],
    tmem[UR16], tmem[UR6], idesc[UR7], UR8, UP0;

// THOR_MMA_000078，O3
UTCHMMA.2CTA.ASHIFT
    tmem[UR7], gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

#### 原章节“`.ashift` 是否改变外围 SASS”· 片段 4

```text
UTC*MMA
    → UTC*MMA.ASHIFT

外围 load/move/shift/control 指令
    → 不新增
```

#### 原章节“`.ashift` 是否改变外围 SASS”· 片段 5

```ptx
tcgen05.mma.cta_group::2.kind::f16
    ...

tcgen05.mma.cta_group::2.kind::f16.ashift
    ...
```

#### 原章节“`.ashift` 是否改变外围 SASS”· 片段 6

```sass
UTCHMMA.2CTA ...
→ UTCHMMA.2CTA.ASHIFT ...
```

#### 原章节“`.ASHIFT` 的已隔离机器编码位”· 片段 7

```text
word 0 XOR = 0x0000000000000000
word 1 XOR = 0x0000000000000400
```

#### 原章节“跨形态代表例子”· 片段 8

```sass
UTCHMMA.2CTA.ASHIFT
    tmem[UR7].A_REUSE, gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

### `operand_source.md`

#### 原章节“PTX 写法”· 片段 1

```ptx
tcgen05.mma... [%d_tmem], %desc_a, %desc_b, ...
```

#### 原章节“PTX 写法”· 片段 2

```ptx
tcgen05.mma... [%d_tmem], [%a_tmem], %desc_b, ...
```

#### 原章节“SASS 映射”· 片段 3

```sass
// SS
UTCHMMA gdesc[UR8], gdesc[UR10], ...

// TS
UTCHMMA tmem[UR7], gdesc[UR8], ...
```

#### 原章节“操作数来源是否改变外围 SASS”· 片段 4

```text
SS
    PTX: %desc_a
    SASS: gdesc[URa]

TS
    PTX: [%a_tmem]
    SASS: tmem[URa]
```

#### 原章节“操作数来源是否改变外围 SASS”· 片段 5

```text
64 位描述符路径
    → LDCU.64 或 LDC.64 + MOV/R2UR

32 位 TMEM 地址路径
    → LDCU 或 LDC + IADD3
```

#### 原章节“操作数来源是否改变外围 SASS”· 片段 6

```sass
LDCU      UR6,  c[0x0][0x380];
LDCU.64   UR8,  c[0x0][0x388];
LDCU.64   UR10, c[0x0][0x390];
UTCHMMA   gdesc[UR8], gdesc[UR10],
           tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

#### 原章节“操作数来源是否改变外围 SASS”· 片段 7

```sass
LDCU.64   UR6, c[0x0][0x380];
LDCU.64   UR8, c[0x0][0x390];
UTCHMMA   tmem[UR7], gdesc[UR8],
           tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```
