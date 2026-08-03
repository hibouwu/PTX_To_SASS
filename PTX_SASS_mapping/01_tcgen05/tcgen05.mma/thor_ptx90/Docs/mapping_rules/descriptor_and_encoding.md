# descriptor 与机器编码：静态逆向的分层边界

## 先说结论

当前文档已经能从 PTX 的操作码变体、限定符、操作数来源和上下文预测核心 SASS 文本及主要外围序列。`idesc`、SMEM descriptor 和 zero-column-mask descriptor 在这里统一视为寄存器操作数；核心机器指令编码记录的是“读取哪个 UR”，不解释 UR 所承载值的内部格式。

当前 PTX → SASS mapping 只研究下面这一层：

```text
PTX opcode/qualifier/operand contract
    → SASS opcode、modifier、操作数槽位、核心机器编码
```

因此不能把 descriptor 值中的位误称为 MMA opcode 位，也不能因为 dense 与 sparse 的规范化核心文本相同就误判 PTX 操作数契约相同。

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

`word 0/1` 按 `nvdisasm` 在 attribution 中输出的两个 64-bit word 顺序编号，不在这里换算成小端字节流的全局 bit 编号。`.4X` 的 PTX/SASS 变化在当前方向上清除 word 0 的该位，其余表中 modifier 置位；只报 XOR 会丢失方向信息。完整 witness ID、左右 PTX/SASS/encoding 和 set/clear mask 见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。

## opcode、kind、REUSE 与 predicate

| 静态变化 | 严格 pair | 稳定编码结果 | 同时变化但不属于 payload 的字段 |
|---|---:|---|---|
| `f16 → tf32` | 272 | 两个 word 完全相同 | 无 |
| `f16 → i8` | 272 | word 1 置位 `0x0000000000000100` | 无 |
| `f16 → f8f6f4` | 272 | word 1 置位 `0x0000000000000300` | 无 |
| `f8f6f4 → i8` | 272 | word 1 清除 `0x0000000000000200` | 无 |
| `UTCOMMA → UTCQMMA`，SS | 168 | word 0 XOR=`0xc000000000000800`，word 1 XOR=`0x0000000000000300` | 无 |
| `UTCOMMA → UTCQMMA`，TS | 168 | word 0 XOR=`0xc000000000000600`，word 1 XOR=`0x0000000000000300` | 无 |
| `A fill → use` | 112 | word 1 稳定置位 `0x0000000000400000`，即 `.A_REUSE` payload | word 1 高位调度/控制 mask `0x01f2000000000000` 可变 |
| `B fill → use` | 128 | word 1 稳定置位 `0x0000000000040000`，即 `.B_REUSE` payload | word 1 高位调度/控制 mask `0x01f2000000000000` 可变 |
| 无核心 predicate → `@UP1` | 232 | word 0 稳定清除 `0x0000000000006000` | word 1 高位随调度布局变化 |
| `@UP1 → @!UP1` | 352 | word 0 稳定置位 `0x0000000000008000` | 无 |

标准 kind 的 word 1 `0x300` 字段可读成 `f16/tf32=0b00`、`i8=0b01`、`f8f6f4=0b11`。`UTCOMMA/UTCQMMA` 还组合使用 word 0 `[63:56]`、与 A 来源相关的 word 0 `[11:0]` 和 word 1 `[9:8]`，因此不是单一 bit；生成 JSON 的 `opcode_layout.observed_rows` 给出全部 family/A-form/kind/variant 组合值。REUSE 使用稳定 payload 位，但 `fill → use` 还会改变调度控制编码；分析器通过所有 pair 的 set/clear 方向交集将二者分开。

v4 定向 microprobe 同时保持多个统一谓词活跃，已恢复两套完整 predicate 字段：核心 guard 使用 word 0 `[14:12]`，`UP0..UP6` 直接编码为 0..6，值 7 表示无 guard，word 0 bit 15 是 negate；enable 操作数使用 word 1 `[25:23]`，`UP0..UP6` 同样直接编码为 0..6，值 7 表示 `UPT`，word 1 bit 26 是 enable negate。每个编号都有独立核心指令见证，分析器逐值断言，不能再把无 guard→`@UP1` 的 `0x6000` 差异误写成单独的 presence bit。

以下隐式 kind/scale 形态是机器编码级 alias：`mxf4 block32 ↔ mxf4 2X` 为 112/112，`mxf4 block32 ↔ mxf4nvf4 block32` 为 112/112，`mxf4 block32 ↔ mxf4nvf4 2X` 为 112/112，`mxf4nvf4 block16 ↔ mxf4nvf4 4X` 为 56/56；每个 pair 的具体 SASS 操作与两个 encoding word 都完全相同。

## 寄存器槽位 bitfield

| SASS 操作数角色 | encoding 字段 | 检查 occurrence | 观测 UR 值 | mismatch |
|---|---|---:|---|---:|
| source A | word 0 `[31:24]` | 52,736 | `4,5,6,7,8,11,13,16,17` | 0 |
| source B | word 0 `[39:32]` | 52,736 | `4,6,8,10,12,16,18` | 0 |
| destination D | word 1 `[7:0]` | 52,736 | `4,6,10,12,16,18` | 0 |
| mask 或 sparse metadata auxiliary | word 0 `[47:40]` | 52,736 | `4,6,8,10,14,16,18` | 0 |
| block-scale 或 zero-mask extra | word 0 `[55:48]` | 37,088 | `6,8,10,12` | 0 |

`idesc[URn]` 在 52,736 条既有 occurrence 中始终满足 `idesc_ur = auxiliary_ur XOR 1`。v4 还加入八个同时跨越目标存活的 64-bit uniform 值，A/B 分配被推高到 `UR22/UR24` 时 auxiliary/idesc 仍为 `UR4/UR5`；因此当前证据支持“编码只携带 auxiliary 偶寄存器，idesc 隐式取相邻奇寄存器”，而不是存在尚未找到的独立 idesc 字段。extra 槽位另有 240 个只改变该 UR 的上下文 pair 验证。

word 1 `[63:27]` 被显式划为编译器 scheduling/control 区域，不参与 semantic opcode 预测。分析器记录各优化级的完整控制值 codebook 和观察到的 variable mask；`.A/B_REUSE` 配对中的 `0x01f2000000000000` 属于该区域。除非进一步逆向 Thor 调度器，正向规则应把这些位作为编译器选择量，而不是 PTX qualifier payload。

## 已证明是机器编码级 alias 的 PTX 拼写

同一 semantic form 内共有 384 个 O3 source-spelling pair，384/384 的具体核心 SASS 文本和两个 encoding word 都完全相同：

| 仅改变的源码拼写 | pair | 编码相同 |
|---|---:|---:|
| 显式 collector discard 与缺省 discard | 160 | 160 |
| 等价 scale-vector 拼写 | 160 | 160 |
| 两类拼写同时改变 | 64 | 64 |

这说明逆向映射不能把“恢复 semantic form”和“恢复原始 PTX 文本”视为同一个目标。即使取得完整核心机器码，也无法区分这些等价 source spelling；逆向器应输出规范 PTX 或 alias 集合，而不应伪造唯一原始拼写。

## descriptor/地址操作数分层表

| 输入 | PTX 表现 | 核心 SASS 表现 | 值是否进入 MMA encoding | 当前静态 mapping 可恢复内容 |
|---|---|---|---|---|
| instruction descriptor | `%idesc` | `idesc[URn]` | 否，只编码 UR 槽位 | 存在性、寄存器类别和槽位 bitfield |
| A/B SMEM descriptor | `%desc_a/%desc_b` | `gdesc[URn]` | 否，只编码 UR 槽位 | A/B 来源类别和槽位 bitfield |
| zero-column-mask descriptor | `%zero_mask_desc` | WS 核心中的额外 `URn` | 否，只编码额外操作数槽位 | descriptor 是否存在及其槽位 bitfield |
| D/A/metadata TMEM address | `[%d_tmem]/[%a_tmem]/[%meta_tmem]` | `tmem[URn]` | 地址值不进入，只编码槽位 | TMEM 来源、角色关系和槽位 bitfield |
| scale-factor TMEM address | `[%scale_a_tmem]/[%scale_b_tmem]` | 额外 `tmem[URn]` | 地址值不进入，只编码槽位 | block scale 是否启用及其槽位 bitfield |

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

## 静态 mapping 的完成标准

| 层 | 当前状态 | 完成条件 |
|---|---|---|
| PTX grammar 与合法组合 | 已覆盖主要形态 | 每类已建模 qualifier 与操作数约束都有最小阴性见证 |
| 核心 SASS 文本选择 | 已形成主要零反例规则 | 新增形态进入自动回归，不靠人工例子 |
| 外围 lowering | guard、lane issuer、identity producer、completion 已系统化；生成器已加入更多 issuer 与非恒等 producer | 在 Thor 完整重跑后冻结新增 profile 的四优化级规则 |
| 核心机器编码 | 已隔离主要 modifier、标准 kind、block opcode composite、REUSE、guard/enable predicate 全编号字段和五个 UR 槽位 | Thor 四优化级重跑验证 v4 定向探针；高位 scheduling/control 保持为独立编译器 codebook |
| descriptor 操作数 | 已区分角色并恢复 A/B/D/aux/extra 槽位，idesc 相邻关系有压力探针 | 把 descriptor 内部内容保持为显式排除范围 |
| 静态逆映射 | 已量化核心文本的可恢复率 | v4 生成正向规则和逆向候选集合并逐条回放 |

因此，当前主要静态 opcode/modifier/predicate/UR 槽位已经从“观察变化”推进为可回放的编码断言。word 1 高位调度控制作为独立编译器字段记录 codebook，不伪装成 PTX 语义字段；新增 producer/issuer 和 v4 定向探针只需 Thor 四优化级完整重跑后冻结最终计数。
