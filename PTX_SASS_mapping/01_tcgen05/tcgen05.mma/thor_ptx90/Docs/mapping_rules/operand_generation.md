# 操作数生成方式：直接参数与 derived producer 如何编译

## 先说结论

操作数来源回答 A/B 是 TMEM 地址还是 SMEM 描述符。操作数生成方式回答这些地址、描述符、指令描述符（instruction descriptor，`idesc`）和谓词在到达 MMA 之前是直接从参数使用，还是经过前序算术/逻辑链派生。

当前 `derived_producers` 配置使用保持值不变的 `add 0`、`xor 0`、`or 0` 链：O0 保留额外 `IADD3`/`LOP3` 等外围指令，O1/O2/O3 将它们全部消除，最终完整规范化 kernel 与直接参数基线相同。

```text
direct_parameters
    → 参数装载 → 搬运到 R/UR → UTC*MMA

identity_arithmetic_chain
    → 参数装载 → add 0 / xor 0 / or 0 → 搬运到 R/UR → UTC*MMA   （O0）
    → 与 direct_parameters 完全相同                              （O1–O3）
```

编译器能消除当前测试的恒等 producer，不表示任意真实地址计算或描述符变换都会消失。

## 与操作数来源的区别

| 问题 | 维度 | 例子 | 主要影响 |
|---|---|---|---|
| 数据从哪类存储对象取得 | 操作数来源 | SS 的 `%desc_a`；TS 的 `[%a_tmem]` | 核心选择 `gdesc[A]` 或 `tmem[A]` |
| 传给目标的值怎样产生 | 操作数生成方式 | 直接参数；`add 0`/`xor 0`/`or 0` 派生 | 外围装载、算术、搬运和寄存器分配 |

两者是正交的分析问题。SS/TS 的详细规则见 [`operand_source.md`](operand_source.md)。本文只研究 producer chain。

## PTX 对照

`runtime_zero` 基线从参数直接形成目标操作数：

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

`derived_producers` case `THOR_MMA_000007` 在相同参数与目标之间增加恒等运算：

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

这些运算不改变位值，专门用于观察 producer 是否保留、如何选择 SASS，以及从哪个优化级开始消除。

## O0：producer 变成外围地址与逻辑运算

普通 FP16 SS case 的 O0 派生路径可见：

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

`IADD3` 承担 32 位 add-zero 路径。`LOP3.LUT` 承担 32/64 位 xor-zero 或 or-zero 逻辑路径。随后通过 `MOV`/`R2UR` 进入核心所需的统一寄存器（Uniform Register，UR）。不同来源和变体会改变具体寄存器及指令数量，应识别"算术/逻辑生产链"而不是记住这组固定编号。

虽然 O0 的完整序列变化，核心 MMA 的助记符、规范操作、寄存器布局和核心位置活跃数仍与直接参数基线相同。producer 是外围编译降级，不是核心指令选择维度。

## O1–O3：恒等 producer 完全消除

O3 的 `THOR_MMA_000007` 与直接参数基线 `THOR_MMA_000001` 得到相同关键序列：

```sass
LDCU UR5, c[0x0][0x39c];
LDCU UR6, c[0x0][0x380];
LDCU.64 UR8, c[0x0][0x388];
LDCU.64 UR10, c[0x0][0x390];
UMOV UR4, URZ;
UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

不仅核心 MMA 相同，O1/O2/O3 的完整规范化 kernel 序列、指令数、核心寄存器布局、核心与峰值活跃数、kernel 寄存器引用集合也全部相同。这是比"核心操作码没变"更强的优化结果。

## 单因素统计

`derived_producers` 与 `runtime_zero` 按相同 semantic form、源码变体和优化级配对，每个优化级 1,152 组：

| 优化级 | 核心助记符变化 | 核心规范操作变化 | 完整 kernel 序列变化 | kernel 指令数变化 | 核心寄存器布局变化 | 核心处活跃数变化 | kernel 峰值活跃数变化 | kernel 引用集合变化 |
|---|---|---|---|---|---|---|---|---|
| O0 | 0/1,152 | 0/1,152 | 1,152/1,152 | 852/1,152 | 0/1,152 | 0/1,152 | 108/1,152 | 556/1,152 |
| O1 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 |
| O2 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 |
| O3 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 | 0/1,152 |

O0 的 1,152/1,152 完整序列变化说明 producer 确实进入了未优化编译降级。只有 852 组改变指令总数，说明其余 300 组虽然总数相同，指令类型、顺序或操作数仍然变化。O1 起所有指标归零，说明当前恒等链已经完全规范化为基线。

## 哪些 producer 不能套用这条消除规则

当前确定性结论只适用于生成器明确记录的 `identity_arithmetic_chain`：

- `add_zero`：加零
- `xor_zero`：与零异或
- `or_zero`：与零或

下列情形没有被本实验证明会消除：

- 非零地址偏移、动态 stride、swizzle 或描述符位域拼装。
- 从共享/全局内存实际加载后再形成描述符。
- 可能溢出、改变高位或改变对齐的算术。
- 依赖 lane、CTA、运行时分支或原子操作的 producer。
- 具有副作用、volatile、内存顺序或别名约束的生产链。

文档中的规则必须写成"当前恒等 producer 在 O1 以上被消除"，不能缩写成"producer 不影响 SASS"。

## 代表性覆盖口径

本文覆盖当前生成集合中的直接参数与恒等派生链，并对 32 位地址/`idesc`、64 位描述符、谓词输入和 completion 地址执行恒等 producer 变换，同时覆盖全部已生成核心形态以及 O0–O3 的消除边界。非恒等地址运算、descriptor 构造、跨基本块数据流和内存加载 producer 尚未形成封闭集合，因此不声明总体百分比。

这个覆盖清单不包含任意真实地址生成算法。若要研究非恒等 producer，需要新增单因素矩阵，分别冻结 offset、stride、descriptor pack、lane dependence 和 memory load。

## 证据

- 上下文统计：[`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)
- PTX case 与 `identity_arithmetic_chain` 清单：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)
- 核心 SASS 与寄存器归属：[`../../results/expanded/sass/sass_attribution.jsonl`](../../results/expanded/sass/sass_attribution.jsonl)
- 操作数来源规则：[`operand_source.md`](operand_source.md)
- 综合解释：[`../tcgen05_mma_PTX到SASS映射规则报告.md`](../tcgen05_mma_PTX到SASS映射规则报告.md)
