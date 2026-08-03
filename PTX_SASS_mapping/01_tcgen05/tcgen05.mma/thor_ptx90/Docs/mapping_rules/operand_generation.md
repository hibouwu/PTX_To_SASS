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

## 扩展 producer 矩阵

生成器现在为全部 1,152 个设计增加三种不能按恒等链消除的 producer：

| profile | producer 结构 | 本地 CUDA 13 O3 预验证 |
|---|---|---|
| `nonidentity_producers` | 对 32-bit 地址/`idesc` 加或异或参数 delta，对 64-bit descriptor/mbarrier 使用扩展后的 delta | 核心助记符与规范操作 0 变化；1,152/1,152 纯寄存器重编号；完整 kernel 序列 1,152/1,152 变化 |
| `branched_producers` | 计算直接值和 delta 派生值，由参数 predicate 在独立基本块中选择 | 核心助记符与规范操作 0 变化；1,152/1,152 纯寄存器重编号；完整 kernel 序列和指令数 1,152/1,152 变化 |
| `global_load_producers` | 从同一 global base 的固定 role offset 装入 D/A、descriptor、metadata、scale、predicate 与 mbarrier 输入 | 核心助记符与规范操作 0 变化；468/1,152 纯重编号、684/1,152 稳定；完整 kernel 序列和指令数 1,152/1,152 变化 |

global-load producer 的 468/684 分类由下面的零反例条件预测：

```text
renumber_only =
    (variant == mma.sp
     and (a_form == tmem_address or kind in {mxf4, mxf4nvf4, mxf8f6f4}))
    or
    (variant == mma.ws.sp
     and (a_form == tmem_address or zero_column_mask == true))

其余合法形态 = stable_layout
```

三种 profile 已通过全部 270 个 expanded shard 的 O3 编译、归属和 3×1,152 配对检查，手写公式 mismatch=0。Thor 四优化级完整回归后，O0/O1/O2 的保留、融合和重编号边界会由自动报告补齐。

## producer 规则的适用边界

当前确定性结论只适用于生成器明确记录的 `identity_arithmetic_chain`：

- `add_zero`：加零
- `xor_zero`：与零异或
- `or_zero`：与零或

下列形态不应套用恒等链消除规则：

- 非零地址偏移、动态 stride、swizzle 或描述符位域拼装。
- 从 shared/global memory load 后再形成目标操作数。
- 可能溢出、改变高位或改变对齐的算术。
- 依赖 lane、CTA、条件分支或原子操作的 producer。
- 具有副作用、volatile、内存顺序或别名约束的生产链。

文档中的规则必须写成"当前恒等 producer 在 O1 以上被消除"，不能缩写成"producer 不影响 SASS"。

## 代表性覆盖口径

当前生成集合覆盖直接参数、恒等算术、参数 delta 非恒等算术、条件基本块选择和 global-load producer，并横跨全部 1,152 个核心设计。尚未枚举的是 shared-memory producer、循环携带值、多个合流基本块、原子结果、复杂 descriptor pack 和跨函数 producer，因此不声明总体百分比。

## 证据

- 上下文统计：[`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)
- PTX case 与全部 producer 清单：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)
- 核心 SASS 与寄存器归属：[`../../results/expanded/sass/sass_attribution.jsonl`](../../results/expanded/sass/sass_attribution.jsonl)
- 操作数来源规则：[`operand_source.md`](operand_source.md)
- 综合解释：[`../tcgen05_mma_PTX到SASS映射规则报告.md`](../tcgen05_mma_PTX到SASS映射规则报告.md)
