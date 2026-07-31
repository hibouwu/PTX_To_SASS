# CTA group：`.cta_group::1/2`

## 这个维度回答什么

CTA group 指一次 `tcgen05.mma` 由一个还是两个 CTA 参与。CTA 是 Cooperative Thread Array，即 CUDA thread block。

## 映射规则

| PTX | SASS |
|---|---|
| `.cta_group::1` | 主助记符不增加 CTA 数量 modifier |
| `.cta_group::2` | 主助记符增加 `.2CTA` |

例子：

```text
UTCHMMA       ← cta_group::1
UTCHMMA.2CTA  ← cta_group::2

UTCQMMA       ← cta_group::1
UTCQMMA.2CTA  ← cta_group::2
```

`.2CTA` 是直接可见的 SASS 主指令 modifier。

## PTX 与 SASS 对照

PTX：

```ptx
tcgen05.mma.cta_group::2.kind::f16.ashift
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
```

核心 SASS：

```sass
UTCHMMA.2CTA.ASHIFT
    tmem[UR7], gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], UP0 ;
```

完整函数见[综合报告的附录 A.2](../tcgen05_mma_PTX到SASS映射规则报告.md)。

## CTA group 还改变哪些 PTX 操作数

普通 MMA 的 disable-output-lane mask 数量随 CTA group 改变：

| CTA group | mask 数量 |
|---|---:|
| 1 | 4 个 32 位 mask |
| 2 | 8 个 32 位 mask |

**disable-output-lane mask** 是指定哪些输出 lane 不写结果的位掩码。 **位掩码** 是用每个二进制位表示开/关状态的整数。

mask 数量变化属于 PTX 操作数形状的一部分，不能只靠 `.2CTA` 文本替代。

## 适用限制

- 普通 `mma` 和 `mma.sp` 覆盖 CTA group 1/2。
- block-scaled 普通 MMA 覆盖 CTA group 1/2。
- `mma.ws` 和 `mma.ws.sp` 只允许 CTA group 1。

因此，不存在合法的：

```ptx
tcgen05.mma.ws.cta_group::2 ...
```

这不是“缺少测试”，而是 variant 与 CTA group 的适用性约束。

## 静态验证与运行时验证要分开

当前结果证明 `.cta_group::2` 能通过 `ptxas` 并稳定生成 `.2CTA`。它没有证明两个 CTA 已在 Thor 上通过真实 cluster launch 正确协作。

**cluster launch** 是把多个 CTA 作为一个协作 cluster 启动的运行方式。真实验证还需要 peer CTA、合法 TMEM 生命周期和同步协议。

## 是否改变外围 SASS

CTA group 的核心和完成协议存在两条直接映射：

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

其中 `UTC*MMA` 代表 `UTCHMMA/UTCQMMA/UTCIMMA/UTCOMMA` 中由 kind 选中的家族。

group 2 还把 disable-output-lane mask 从 4 个扩展到 8 个。根据 mask 如何产生，外围 SASS 从以下集合中选择：

| PTX/上下文作用 | 可能选择的 SASS | 作用 |
|---|---|---|
| 常量或普通寄存器 mask | `MOV`、`UMOV` | 形成每个 mask word |
| GPR mask 送入 uniform operand | `R2UR` | GPR 到 uniform register 搬运 |
| mask 逻辑合成 | `LOP3.LUT` | 组合位掩码 |
| completion | `UTCBAR` 或 `UTCBAR.2CTA` | 选择单 CTA/双 CTA 完成协议 |
| 调度填充 | `NOP` | 解决调度间隔，不承载新的 PTX 语义 |

所以真正的 lowering 关系是：

```text
.cta_group::2
    → 核心 MMA 增加 .2CTA
    → completion 的 UTCBAR 选择 .2CTA 版本
    → 如果额外 4 个 mask 未被常量折叠，则选择更多 MOV/R2UR/UMOV
```

下面选六组最有代表性的 group 1/group 2 配对。每组都先给目标 PTX，再给同一 case 的 O0 和 O3。SASS 只保留与本组结论有关的片段。

### 对比 1：`runtime_zero`——纯核心基线

对应 PTX：

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

O0：

```sass
// group 1
UTCHMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;

// group 2
UTCHMMA.2CTA gdesc[UR4], gdesc[UR6],
              tmem[UR18], tmem[UR16], idesc[UR17], UR8, UP0;
```

O3：

```sass
// group 1
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// group 2
UTCHMMA.2CTA gdesc[UR8], gdesc[UR10],
              tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

基线说明 `.2CTA` 在 O0/O3 都稳定存在；零 mask 到 O3 已完全折叠。

### 对比 2：`enable_true_mask_ones`——4 个 mask 对 8 个 mask

对应 PTX：

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

O0：

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

O3：

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

这组最清楚地展示了 mask 的选择过程：O0 是 `MOV→R2UR`，O3 合并为 4 条或 8 条 `UMOV`。

### 对比 3：`derived_producers`——生产链能否被消去

对应 PTX：

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

O0：

```sass
// group 1
IADD3 R0, PT, PT, R0, RZ, RZ;
LOP3.LUT R15, R15, RZ, RZ, 0x3c, !PT;
LOP3.LUT R16, R16, RZ, RZ, 0x3c, !PT;
LOP3.LUT R13, R13, RZ, RZ, 0xfc, !PT;
LOP3.LUT R14, R14, RZ, RZ, 0xfc, !PT;
LOP3.LUT R2,  R2,  RZ, RZ, 0x3c, !PT;
R2UR  UR4, R4;
R2UR  UR6, R6;
R2UR  UR10, R0;
UTCHMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;

// group 2
IADD3 R0, PT, PT, R0, RZ, RZ;
LOP3.LUT R19, R19, RZ, RZ, 0x3c, !PT;
LOP3.LUT R20, R20, RZ, RZ, 0x3c, !PT;
LOP3.LUT R17, R17, RZ, RZ, 0xfc, !PT;
LOP3.LUT R18, R18, RZ, RZ, 0xfc, !PT;
LOP3.LUT R2,  R2,  RZ, RZ, 0x3c, !PT;
R2UR  UR4,  R4;
R2UR  UR6,  R6;
R2UR  UR18, R0;
UTCHMMA.2CTA gdesc[UR4], gdesc[UR6],
              tmem[UR18], tmem[UR16], idesc[UR17], UR8, UP0;
```

O3：

```sass
// group 1：identity producer 已消去
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// group 2：identity producer 已消去
UTCHMMA.2CTA gdesc[UR8], gdesc[UR10],
              tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

这组说明 O0 中能看到 `IADD3/LOP3.LUT/R2UR` 生产链，O3 会把恒等运算全部消去；CTA group 最终只保留 `.2CTA` 差异。

### 对比 4：`commit_completion`——完成协议选择

对应 PTX：

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

O0：

```sass
// group 1
UTCHMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;
R2UR   UR4, R0;
UTCBAR [UR4], URZ;

// group 2
UTCHMMA.2CTA gdesc[UR4], gdesc[UR6],
              tmem[UR18], tmem[UR16], idesc[UR17], UR8, UP0;
R2UR   UR4, R0;
UTCBAR.2CTA [UR4], URZ;
```

O3：

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

这组把核心与完成协议对应起来：`.cta_group::2` 同时选择 `UTCHMMA.2CTA` 和 `UTCBAR.2CTA`。

### 对比 5：sparse INT8——跨 variant、opcode 与活跃寄存器

对应 PTX：

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

O0：

```sass
// group 1；核心处 live：GPR 1、UGPR 11、P 1、UP 1
UTCIMMA gdesc[UR4], gdesc[UR6],
         tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;

// group 2；核心处 live：GPR 1、UGPR 15、P 1、UP 1
UTCIMMA.2CTA gdesc[UR4], gdesc[UR6],
              tmem[UR18], tmem[UR16], idesc[UR17], UR8, UP0;
```

O3：

```sass
// group 1；核心处 live：GPR 1、UGPR 7、P 2、UP 1
UTCIMMA gdesc[UR6], gdesc[UR8],
         tmem[UR4], tmem[UR10], idesc[UR11], UP0;

// group 2；核心处 live：GPR 1、UGPR 7、P 2、UP 1
UTCIMMA.2CTA gdesc[UR6], gdesc[UR8],
              tmem[UR4], tmem[UR10], idesc[UR11], UP0;
```

这组补上普通 `mma.sp` 和 `UTCIMMA` 家族。它还直接展示：额外 4 个 mask 可使 O0 核心位置的活跃 UGPR 从 11 增至 15，但在 O3 中准备序列被优化后，两组的活跃寄存器数量重新相同；稳定保留的差异仍是 `.2CTA`。`.sp` 自身没有同名 `.SP` 后缀，稀疏语义由 metadata 操作数和编码承载。

### 对比 6：block-scaled 4X——无 mask 的正交 modifier 组合

对应 PTX：

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

O0：

```sass
// group 1
UTCOMMA.4X tmem[UR11], gdesc[UR4],
            tmem[UR10], tmem[UR6], idesc[UR7], tmem[UR8], UP0;

// group 2
UTCOMMA.2CTA.4X tmem[UR11], gdesc[UR4],
                 tmem[UR10], tmem[UR6], idesc[UR7], tmem[UR8], UP0;
```

O3：

```sass
// group 1
UTCOMMA.4X tmem[UR7], gdesc[UR8],
            tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR10], UP0;

// group 2
UTCOMMA.2CTA.4X tmem[UR7], gdesc[UR8],
                 tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR10], UP0;
```

block-scaled 形态没有 disable-output-lane mask，因此 group 1→2 不会产生 4→8 个 mask 的准备序列。这一配对中 O0/O3 的核心操作数和活跃寄存器都相同，只有 `.2CTA` 及其机器编码位发生变化。同时它证明 `.2CTA` 可以和 `.4X` 正交组合，且规则同样适用于 `UTCOMMA` 家族。

## 代表性覆盖口径

这里的“覆盖率”按主要静态 lowering 机制计算，不按 192 种精确 semantic form 逐条计数。六组配对覆盖：

| 主要机制 | 代表例子 |
|---|---|
| 核心 `.2CTA` 与编码位稳定变化 | 对比 1、5、6 |
| 有 mask 形态的 4→8 操作数契约 | 对比 2、5 |
| 无 mask 的 block-scaled 形态 | 对比 6 |
| `MOV/R2UR/UMOV/LOP3.LUT` 及优化消除 | 对比 2、3 |
| completion 的 `UTCBAR→UTCBAR.2CTA` | 对比 4 |
| opcode/variant/modifier 组合与活跃寄存器变化 | 对比 5、6 |

按这六类主要静态机制计为 6/6；考虑没有逐条展示所有 kind、collector 和调度填充实例，保守记为 **至少 95% 的主要变化机制**，而不是“95% 的精确指令形态”。真实双 CTA cluster 协作仍属于运行时验证，不计入这个静态覆盖率。

下面的统计说明这些候选指令在哪些优化级被实际保留下来。

会，但不是每个上下文都会改变。把 group 2 与同一合法设计的 group 1 配对后，得到 2,432 个源码/上下文配对，即 O0–O3 共 9,728 次比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 1,048/9,728 |
| 外围指令类型或排列 | 2,256/9,728 |
| 核心位置活跃寄存器 | 1,144/9,728 |
| 核心 MMA 编码 | 9,728/9,728 |

所以 `.cta_group::2` 不只是给核心 MMA 增加 `.2CTA`：

- 普通 MMA 的 mask 从 4 个增加到 8 个，某些上下文因此增加 `MOV`、`R2UR` 或 `UMOV` 等准备指令；
- completion 上下文中的 `UTCBAR` 会相应变为 `UTCBAR.2CTA`；
- O0 最容易保留额外准备序列：2,432 次 O0 比较中有 832 次指令数变化；
- O1、O2、O3 各只有 72/2,432 次指令数变化，说明多数常量 mask 准备会被优化。

变化不是固定增加一条指令。观察到的 group 2 指令数增量为 8、16、24、32 或 40 条，取决于 mask、producer 和 completion 上下文。没有观察到 group 2 比配对的 group 1 指令更少。

## 证据

- 52,736 条目标 occurrence 中，`.2CTA` 是否出现与 CTA group 完全一致。
- 当前样本反例为 0。
- 完整 TS + 2CTA + ASHIFT 例子位于综合报告附录 A.2。
