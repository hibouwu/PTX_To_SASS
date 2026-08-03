# 外围上下文编译降级：guard、issuer 与 producer

## 先说结论

guard、发射线程（issuer）和操作数生产方式（producer）都不选择 `UTCHMMA`、`UTCQMMA`、`UTCIMMA` 或 `UTCOMMA` 家族，但会改变核心谓词、外围控制流、参数准备、寄存器分配和活跃区间。三者必须与核心指令选择分层分析：

| 上下文 | 回答的问题 | 核心 MMA 影响 | 主要外围影响 |
|---|---|---|---|
| guard | 这条 PTX 指令是否执行？ | 双 occurrence 的部分形态只在首条增加 `@UPn/@!UPn`；其余形态核心无 guard | 谓词形成、分支或提前退出 |
| issuer | 哪个 lane/CTA thread 到达并发射？ | 助记符和规范操作不变；部分形态纯寄存器重编号 | lane/thread ID、比较、分支、活跃区间 |
| producer | 地址、描述符和谓词怎样产生？ | 助记符和规范操作不变；非恒等形态可引起重编号 | load、算术、逻辑、搬运和基本块合流 |

```text
核心指令选择
    kind + variant + CTA group + TS/SS + collector + block scaling + ashift

外围上下文编译降级
    guard + issuer + producer + enable + completion
```

本页合并此前分散的 guard、issuer 和 producer 三组条目。逐 profile 的四优化级统计见[上下文差分报告](../tcgen05_mma_上下文差分报告.md)，自动断言和精确候选规则见[逆向规则报告](reverse_mapping_rules.md)。

## 三个维度不能混为一谈

- guard 是目标 PTX 指令自身的条件前缀，例如 `@%guard tcgen05.mma ...`。
- issuer 是围绕目标建立的线程选择，例如只允许 lane 0、lane 31、参数指定 lane 或 `%tid.x == 0` 到达目标。
- producer 是生成 D/A、descriptor、metadata、scale、enable、guard 或 mbarrier 输入的前序数据流。
- enable 是核心 MMA 的末尾谓词操作数，决定是否读取并累加旧 D；它不是外部 guard。
- completion 位于核心之后，决定已经发出的异步工作如何提交、等待和同步；它不决定谁发射，也不决定操作数怎样产生。

同一 kernel 可以同时具有这五类上下文。看到 SASS 谓词或分支时，必须沿 PTX 数据流和控制流判断来源，不能仅凭助记符猜测。

## guard：核心首条谓词化或外围控制流

guard 有两条主要编译降级路径：

```text
PTX 正 guard
    → @UPn UTC*MMA ... ; UTC*MMA ...
    或 ISETP/PLOP3 + 条件分支/提前退出 + 无显式 guard 的 UTC*MMA

PTX 负 guard
    → @!UPn UTC*MMA ... ; UTC*MMA ...
    或反向条件分支/提前退出 + 无显式 guard 的 UTC*MMA
```

### guard 与 enable 的位置

```sass
@UP1 UTCHMMA gdesc[UR8].A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
      UTCHMMA gdesc[UR8].A_REUSE.A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

指令最前面的 `@UP1` 是 guard，末尾的 `UP0` 是 enable。两条 collector occurrence 只在第一条携带 guard，表示编译器把整个序列作为同一条件控制单元；第二条没有再次谓词化不代表 guard 丢失。

外围控制流路径则可能表现为：

```sass
ISETP.NE.U32.AND P0, PT, RZ, UR5, PT;
@!P0 EXIT;
...
UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

这里核心 MMA 没有显式 guard，但执行条件已经由提前退出实现。正负极性改变 `@UPn/@!UPn` 或分支取反方向，不改变路径分类条件。

### guard 的精确路径规则

对当前 1,152 个设计，O1–O3 的路径可由 `variant + kind + zero_column_mask + step_count` 零反例预测：

```text
first_occurrence_core_predication =
    step_count == 2
    and (
        variant in {mma.sp, mma.ws.sp}
        or (kind in {f16, tf32, f8f6f4, i8} and zero_column_mask == false)
    )

其余合法形态 = external_control_flow
```

| 路径 | 设计数 | occurrence guard 形状 |
|---|---:|---|
| collector 序列首条核心谓词化 | 352 | 全部为 `(true, false)` |
| 外围控制流 | 800 | 656 个 `(false)`；144 个 `(false, false)` |

正、负 guard 在 O1–O3 得到相同的 352/800 分类，全部 1,152 个完整 kernel 序列都会变化；核心操作码家族变化为 0。

### guard 的机器编码边界

核心 guard selector 使用 word 0 `[14:12]`：`UP0..UP6 → 0..6`，值 7 表示无 guard，bit 15 表示 negate。enable 使用独立的 word 1 `[25:23]` 和 negate bit 26。完整逐值见证和单探针证据规模见 [`descriptor_and_encoding.md`](descriptor_and_encoding.md)及 [`reverse_mapping_rules.md`](reverse_mapping_rules.md)。

## issuer：线程选择、控制流和寄存器重编号

当前矩阵覆盖以下 issuer：

- 当前到达目标位置的线程直接发射。
- lane 0、lane 31 或参数指定 lane 通过外围分支发射。
- `%tid.x == 0` 的 CTA thread 通过外围分支发射。
- lane-0 条件与参数 guard 合取后直接谓词化或走外围控制流。

lane-0 的典型 O3 形态是：

```sass
S2R R0, SR_LANEID;
ISETP.NE.U32.AND P0, PT, R0, RZ, PT;
@P0 EXIT;
...
UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

`UTCHMMA` 不增加 `.LANE0` 一类修饰符。issuer 信息存在于外围线程标识读取、比较和控制流中，并通过控制流边界影响参数准备位置和寄存器活跃区间。

### lane/CTA-thread branch issuer 的精确规则

lane 0、lane 31、参数 lane 和 CTA thread 0 四种 branch issuer 在 O1–O3 都使用相同的 168/984 分类，跨 profile mismatch=0：

```text
renumber_only =
    a_form == tmem_address
    and (
        (variant == mma.sp and kind in {mxf4, mxf4nvf4, mxf8f6f4})
        or (variant == mma.ws.sp and zero_column_mask == true)
    )

其余合法形态 = stable_layout
```

| 子集 | 数量 | 条件 |
|---|---:|---|
| 稀疏分块缩放 TS | 100 | `mma.sp`，A=`tmem`，kind 为 `mxf4/mxf4nvf4/mxf8f6f4` |
| 稀疏 WS + zero-column-mask TS | 68 | `mma.ws.sp`，A=`tmem`，zero-column-mask=true |
| 其余合法设计 | 984 | 核心寄存器布局稳定 |

这里的“稳定”只指核心寄存器布局是否相对基线变化。四种 branch issuer 的完整 kernel 序列、kernel 峰值活跃数和寄存器引用集合仍全部变化；lane 0、lane 31 和动态 lane 的核心位置活跃数也全部变化，而 CTA thread 0 的该指标为 0/1,152。公式不预测具体物理编号，编号仍受活跃区间和工具链版本影响。

compound predicated issuer 的规则更直接：双 occurrence collector 序列只谓词化第一条，单 occurrence 形态使用外围控制流。它验证了 lane 条件与参数 guard 合取后的编译降级，但不代表任意嵌套 CFG 已封闭枚举。

## producer：直接参数、恒等链和真实数据流

操作数来源回答 A/B 是 TMEM 地址还是 SMEM 描述符；producer 回答这些值怎样到达目标。两者正交：TS/SS 决定核心使用 `tmem` 或 `gdesc`，producer 决定外围是否出现 load、算术、逻辑和搬运。

### 恒等 producer

`derived_producers` 使用保持位值不变的 `add 0`、`xor 0` 和 `or 0`：

```text
direct_parameters
    → 参数装载 → R/UR → UTC*MMA

identity_arithmetic_chain
    → 参数装载 → add 0 / xor 0 / or 0 → R/UR → UTC*MMA  （O0）
    → 与 direct_parameters 完全相同                         （O1–O3）
```

O0 的 1,152/1,152 个完整序列发生变化，1,068 个改变指令数；核心助记符、规范操作、寄存器布局和核心位置活跃数不变。O1–O3 的完整规范化 kernel 序列、指令数、核心布局、活跃数和寄存器引用集合全部与直接参数基线相同。

这条结论只适用于生成器记录的恒等链，不能缩写成“producer 不影响 SASS”。非零偏移、动态 stride、swizzle、描述符位域拼装、memory load、分支、原子、volatile 和具有内存顺序的 producer 都不属于恒等消除规则。

### 扩展 producer

| profile | producer 结构 | Thor O1–O3 结果 |
|---|---|---|
| `nonidentity_producers` | 地址/`idesc` 加或异或参数 delta，64-bit descriptor/mbarrier 使用扩展 delta | 1,152/1,152 纯重编号；完整序列全部变化 |
| `branched_producers` | 直接值与 delta 派生值由参数 predicate 在独立基本块中选择 | 1,152/1,152 纯重编号；完整序列和指令数全部变化 |
| `global_load_producers` | 从 global base 的固定 role offset 装入全部目标输入 | 468/1,152 纯重编号、684/1,152 稳定；完整序列和指令数全部变化 |

三类 producer 的核心助记符和规范操作变化均为 0，手写公式 mismatch=0。global-load 的 468/684 分类为：

```text
renumber_only =
    (variant == mma.sp
     and (a_form == tmem_address or kind in {mxf4, mxf4nvf4, mxf8f6f4}))
    or
    (variant == mma.ws.sp
     and (a_form == tmem_address or zero_column_mask == true))

其余合法形态 = stable_layout
```

## 联合分析边界

| 容易混淆的组合 | 正确区分 |
|---|---|
| guard + issuer | issuer 决定谁到达目标，guard 决定到达后的目标是否执行；二者都可能生成分支 |
| guard + enable | guard 控制整条 PTX，enable 控制是否累加旧 D；机器编码字段独立 |
| issuer + CTA group | issuer 选择发射线程，CTA group 选择一次操作涉及一个还是两个 CTA 的 TMEM |
| producer + TS/SS | producer 决定值怎样产生，TS/SS 决定 A 的存储来源和核心操作数类别 |
| producer + completion | producer 位于核心前准备输入，completion 位于核心后提交或等待工作 |

64,548 个上下文配对没有一次改变核心 MMA 操作码家族，但上下文仍可改变谓词、modifier、寄存器编号、活跃集合、外围序列和完整 encoding。结论必须写成“上下文不改变当前样本中的核心家族选择”，不能写成“上下文不影响 SASS”。

## 覆盖与证据

当前静态机制覆盖正/负 guard、两种 guard 路径、全部 `UP0..UP6` selector、四种 branch issuer、compound issuer、直接参数、恒等算术、参数 delta、分支合流和 global-load producer，并跨 O0/O1/O2/O3 回归。未封闭枚举的仍包括任意嵌套 CFG、动态 leader election、多候选 issuer、循环携带值、复杂 descriptor pack、shared-memory producer、原子结果和跨函数 producer，因此不声明开放编译器输入空间的总体百分比。

- 上下文逐 profile 统计：[`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)
- 自动决策公式与反例计数：[`reverse_mapping_rules.md`](reverse_mapping_rules.md)
- 综合 PTX/SASS 解释：[`../tcgen05_mma_PTX到SASS映射规则报告.md`](../tcgen05_mma_PTX到SASS映射规则报告.md)
- expanded manifest：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)
- SASS attribution 汇总：[`../../results/expanded/sass/sass_report.json`](../../results/expanded/sass/sass_report.json)

## 附录：合并前上下文文档的完整 PTX/SASS 片段

本附录逐块保留合并前 guard、issuer 和 producer 文档中的 fenced 片段。片段正文保持原样；标题只记录原文件、原章节和块编号。已在正文中原样出现的块不重复列出。

原代表 witness 索引：

| case ID | 原文档 | 原章节 |
|---|---|---|
| `THOR_MMA_000004` | `guard.md` | 路径二：外围控制流 |
| `THOR_MMA_000025` | `guard.md` | 路径一：collector 序列首条 SASS 谓词化 |
| `THOR_MMA_000028` | `guard.md` | 路径一：collector 序列首条 SASS 谓词化 |
| `THOR_MMA_000006` | `issuer.md` | PTX 形态 |
| `THOR_MMA_000001` | `operand_generation.md` | O1–O3：恒等 producer 完全消除 |
| `THOR_MMA_000007` | `operand_generation.md` | PTX 对照 |

### `guard.md`

#### 原章节“guard 与 enable 不是同一个谓词”· 片段 2

```ptx
@%guard tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

#### 原章节“路径一：collector 序列首条 SASS 谓词化”· 片段 3

```ptx
@%guard  tcgen05.mma.cta_group::1.kind::f16.collector::a::fill ...;
@!%guard tcgen05.mma.cta_group::1.kind::f16.collector::a::fill ...;
```

#### 原章节“路径一：collector 序列首条 SASS 谓词化”· 片段 4

```sass
@UP1  UTCHMMA gdesc[UR8].A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
      UTCHMMA gdesc[UR8].A_REUSE.A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
@!UP1 UTCHMMA gdesc[UR8].A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
      UTCHMMA gdesc[UR8].A_REUSE.A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

#### 原章节“路径一：collector 序列首条 SASS 谓词化”· 片段 5

```sass
UTCHMMA gdesc[UR8].A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

#### 原章节“路径二：外围控制流”· 片段 6

```sass
// 正 guard：guard 为假时退出
ISETP.NE.U32.AND P0, PT, RZ, UR5, PT;
@!P0 EXIT;
...
UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// 负 guard：guard 为真时退出
ISETP.NE.U32.AND P0, PT, RZ, UR5, PT;
@P0 EXIT;
...
UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

### `issuer.md`

#### 原章节“先说结论”· 片段 1

```text
current_thread
    → 线程直接到达 UTC*MMA

lane0_issuer
    → 读取 SR_LANEID
    → 判断 lane != 0
    → 非 lane 0 绕过或退出
    → lane 0 执行同一 UTC*MMA
```

#### 原章节“PTX 形态”· 片段 2

```ptx
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

#### 原章节“PTX 形态”· 片段 3

```ptx
mov.u32 %lane, %laneid;
setp.eq.u32 %issuer, %lane, 0;
@!%issuer bra CASE_END_000006;
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
CASE_END_000006:
```

#### 原章节“O0：完整显示 lane 选择”· 片段 4

```sass
S2R R2, SR_LANEID;
MOV R2, R2;
ISETP.EQ.U32.AND P1, PT, R2, RZ, PT;
PLOP3.LUT P1, PT, P1, PT, PT, 0x8, 0x80;
...
@P1 BRA ...;
...
UTCHMMA gdesc[UR4], gdesc[UR6], tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;
```

#### 原章节“O3：收缩为早期退出”· 片段 5

```sass
S2R R0, SR_LANEID;
ISETP.NE.U32.AND P0, PT, R0, RZ, PT;
@P0 EXIT;
LDCU UR6, c[0x0][0x380];
LDCU.64 UR8, c[0x0][0x388];
LDCU.64 UR10, c[0x0][0x390];
...
UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

### `operand_generation.md`

#### 原章节“先说结论”· 片段 1

```text
direct_parameters
    → 参数装载 → 搬运到 R/UR → UTC*MMA

identity_arithmetic_chain
    → 参数装载 → add 0 / xor 0 / or 0 → 搬运到 R/UR → UTC*MMA   （O0）
    → 与 direct_parameters 完全相同                              （O1–O3）
```

#### 原章节“PTX 对照”· 片段 2

```ptx
ld.param.b32 %d_tmem, [p_d_tmem];
ld.param.b64 %desc_a, [p_desc_a];
ld.param.b64 %desc_b, [p_desc_b];
ld.param.b32 %idesc, [p_idesc];
...
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

#### 原章节“PTX 对照”· 片段 3

```ptx
add.u32 %d_tmem, %d_tmem, 0;
add.u32 %a_tmem, %a_tmem, 0;
xor.b64 %desc_a, %desc_a, 0;
or.b64 %desc_b, %desc_b, 0;
add.u32 %meta_tmem, %meta_tmem, 0;
xor.b32 %idesc, %idesc, 0;
add.u32 %scale_a_tmem, %scale_a_tmem, 0;
add.u32 %scale_b_tmem, %scale_b_tmem, 0;
xor.b64 %zero_mask_desc, %zero_mask_desc, 0;
or.b32 %enable_u32, %enable_u32, 0;
xor.b32 %guard_u32, %guard_u32, 0;
add.u64 %mbar, %mbar, 0;
...
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

#### 原章节“O0：producer 变成外围地址与逻辑运算”· 片段 4

```sass
IADD3 R0, PT, PT, R0, RZ, RZ;
LOP3.LUT R15, R15, RZ, RZ, 0x3c, !PT;
LOP3.LUT R16, R16, RZ, RZ, 0x3c, !PT;
LOP3.LUT R13, R13, RZ, RZ, 0xfc, !PT;
LOP3.LUT R14, R14, RZ, RZ, 0xfc, !PT;
LOP3.LUT R2, R2, RZ, RZ, 0x3c, !PT;
...
R2UR UR4, R4;
R2UR UR5, R5;
R2UR UR6, R6;
R2UR UR7, R7;
...
UTCHMMA gdesc[UR4], gdesc[UR6], tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;
```

#### 原章节“O1–O3：恒等 producer 完全消除”· 片段 5

```sass
LDCU UR5, c[0x0][0x39c];
LDCU UR6, c[0x0][0x380];
LDCU.64 UR8, c[0x0][0x388];
LDCU.64 UR10, c[0x0][0x390];
UMOV UR4, URZ;
UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```
