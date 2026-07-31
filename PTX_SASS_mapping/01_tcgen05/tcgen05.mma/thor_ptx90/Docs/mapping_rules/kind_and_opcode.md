# `kind` 与核心 SASS opcode

## 这个维度回答什么

`kind` 表示 `tcgen05.mma` 属于哪一类数据格式和计算路径。它首先决定核心
SASS 使用 `UTCHMMA`、`UTCQMMA`、`UTCIMMA` 还是 `UTCOMMA`。

**数据格式** 指矩阵元素如何用二进制表示；**核心 SASS** 指真正触发 Tensor
Core 数值运算的那条机器指令，不包括参数装载和线程选举。

## PTX 语法位置

```ptx
tcgen05.mma.cta_group::1.kind::f16 ...
tcgen05.mma.cta_group::1.kind::tf32 ...
tcgen05.mma.cta_group::1.kind::i8 ...
```

`kind` 是 opcode qualifier。**qualifier** 是附加在 PTX 指令名后的语义限定。

## 映射规则

| PTX `kind` | SASS 主助记符 | 白话解释 |
|---|---|---|
| `f16` | `UTCHMMA` | 16 位浮点家族 |
| `tf32` | `UTCHMMA` | TensorFloat-32 家族 |
| `f8f6f4` | `UTCQMMA` | FP8/FP6/FP4 混合低精度家族 |
| `mxf8f6f4` | `UTCQMMA` | 带分块缩放的 FP8/FP6/FP4 家族 |
| `i8` | `UTCIMMA` | 8 位整数家族 |
| `mxf4` | `UTCOMMA` | microscaling FP4 家族 |
| `mxf4nvf4` | `UTCOMMA` | MXF4/NVF4 家族 |

这里：

- **FP** 是 floating point，即浮点数；
- **INT8** 是 8 位整数；
- **TF32** 是 Tensor Core 使用的 TensorFloat-32 格式；
- **microscaling** 指多组低精度数据共享局部缩放因子；
- **助记符** 是反汇编器显示的 opcode 人类可读名称。

## 最小例子

```ptx
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

核心 SASS：

```sass
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0 ;
```

如果只把 `kind::f16` 换成 `kind::i8`，主助记符进入 `UTCIMMA` 家族；其他
modifier 仍由 CTA group、来源模式和 collector 等维度决定。

## 为什么多个 kind 会共享同一个主助记符

`f16` 和 `tf32` 都映射到 `UTCHMMA`，不代表二者机器语义相同。精确 A/B/D
类型、矩阵 M/N/K 形状和 major 方向还可能由 `idesc` 提供。

- **A/B/D**：两个输入矩阵 A、B 和输出/累加矩阵 D。
- **M/N/K**：`M×K` 矩阵乘以 `K×N` 矩阵的三个尺寸。
- **major**：数据以行或列为主要连续方向。
- **idesc**：instruction descriptor，描述 MMA 类型和形状等信息。

因此，本条目能给出“主 opcode 家族规则”，不能仅凭可见助记符恢复所有
descriptor 字段。

## 与其他维度组合

主助记符确定后，还会叠加：

```text
cta_group::2 → .2CTA
ws           → .WS
ashift       → .ASHIFT
4X 形态      → .4X（仅适用的 UTCOMMA 形态）
```

例如：

```text
kind::f16 + cta_group::2 + ashift
→ UTCHMMA.2CTA.ASHIFT
```

组合限制见 [`interactions.md`](interactions.md)。

## 是否改变外围 SASS

kind 的指令选择关系是：

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

四个核心家族使用的对应 PTX 如下。为突出 `kind`，都使用 CTA group 1 和直接
参数上下文：

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

它们的 O3 代表性 SASS 如下：

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

前三条说明：在操作数契约相同时，kind 直接选择 `UTCHMMA/UTCQMMA/UTCIMMA`
之一，外围和核心寄存器布局可以保持不变。最后一条多出的 `tmem[UR12]` 来自
block scaling，不应误归因给 `UTCOMMA` 这个 opcode 名称。

下面专门比较 `f8f6f4` 与 `i8` 在 O0/O3 的稳定性。对应 PTX 是：

```ptx
tcgen05.mma.cta_group::1.kind::f8f6f4
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

tcgen05.mma.cta_group::1.kind::i8
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

O0 与 O3 会重新安排操作数，但不会重新选择 kind 对应的核心家族：

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

O0 用来观察 descriptor、mask 和 `enable` 如何进入操作数；O3 用来读取最终
寄存器布局。`UTCQMMA/UTCIMMA` 的选择在两级中保持不变。

对于不带 block scaling 的 `f16/tf32/f8f6f4/i8`，外围指令选择集合不随 kind
变化：参数仍由同一组 `LDC/LDCU` 装载，谓词和控制仍使用同一组
`UISETP/PLOP3/ELECT/BRA` 指令。变化被限制在核心 MMA 家族内。

特别地，`f16` 和 `tf32` 都选择 `UTCHMMA`。在当前 `idesc` 运行时传入的
实验中，二者连核心编码也相同；类型区别不由另一个 SASS opcode 表达，而由
`idesc` 的运行时内容表达。

下面的计数用于确认上述选择关系在全部上下文和优化级中是否稳定。

这里把 `f16` 作为基线，在 kind 之外的 semantic form、源码写法、上下文和
优化级完全相同的条件下，分别与 `tf32`、`f8f6f4`、`i8` 配对。每组有
1,504 个源码/上下文配对，乘以 O0–O3 后是 6,016 次 SASS 比较。

| kind 对比 | 完整函数指令数变化 | 外围指令类型变化 | 核心活跃寄存器变化 | 核心编码 |
|---|---:|---:|---:|---|
| `tf32` 对 `f16` | 0/6,016 | 0/6,016 | 0/6,016 | 6,016/6,016 相同 |
| `f8f6f4` 对 `f16` | 0/6,016 | 0/6,016 | 0/6,016 | 6,016/6,016 不同 |
| `i8` 对 `f16` | 0/6,016 | 0/6,016 | 0/6,016 | 6,016/6,016 不同 |

**外围指令**指去掉目标 MMA 后，函数中剩余的参数装载、谓词、选举、分支和完成
协议指令。**核心活跃寄存器**指执行目标 MMA 时仍保存有效值的寄存器数量。

结论很直接：

- 非 block-scaled kind 不会增加或删除外围 SASS，也不改变外围指令类型；
- `f8f6f4` 和 `i8` 改变核心 opcode 与编码；
- 当前运行时 `idesc` 写法下，`f16` 与 `tf32` 生成了完全相同的核心指令文本
  和编码，二者的具体类型区别由运行时 descriptor 承载；
- block-scaled kind 还会增加 scale-factor 操作数，不能套用本节结论，见
  [`block_scaling.md`](block_scaling.md)。

## 证据与边界

- 对 expanded attribution 的 52,736 条目标 occurrence 检查，kind → 主助记符
  规则反例为 0。
- `ptxas` 和 `nvdisasm` 均来自 CUDA 13.0。
- 结论适用于 PTX 9.0、`sm_110a`。
- 尚未逐字段冻结 `idesc`，所以不能据此给出精确 dtype/shape 编码位。

**dtype** 是 data type，即数据类型；**编码位** 是机器指令二进制中的具体 bit。
