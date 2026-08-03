# `kind` 如何决定核心 SASS 操作码

## 这个维度回答什么

`kind` 指定 `tcgen05.mma` 属于哪一类数据格式和计算路径。编译器根据 `kind` 选择核心 SASS 使用 `UTCHMMA`、`UTCQMMA`、`UTCIMMA` 还是 `UTCOMMA`。

数据格式指矩阵元素如何用二进制表示。核心 SASS 指真正触发张量核心（Tensor Core）数值运算的那条机器指令，不包括参数装载和线程选举。

## PTX 语法位置

```ptx
tcgen05.mma.cta_group::1.kind::f16 ...
tcgen05.mma.cta_group::1.kind::tf32 ...
tcgen05.mma.cta_group::1.kind::i8 ...
```

`kind` 是操作码限定符（qualifier），即附加在 PTX 指令名后的语义限定。

## 映射规则

| PTX `kind` | SASS 主助记符 | 含义 |
|---|---|---|
| `f16` | `UTCHMMA` | 16 位浮点家族 |
| `tf32` | `UTCHMMA` | TensorFloat-32 家族 |
| `f8f6f4` | `UTCQMMA` | FP8/FP6/FP4 混合低精度家族 |
| `mxf8f6f4` | `UTCQMMA` | 带分块缩放的 FP8/FP6/FP4 家族 |
| `i8` | `UTCIMMA` | 8 位整数家族 |
| `mxf4` | `UTCOMMA` | 显微缩放（microscaling）FP4 家族 |
| `mxf4nvf4` | `UTCOMMA` | MXF4/NVF4 家族 |

术语说明：

- FP（Floating Point）是浮点数。
- INT8 是 8 位整数。
- TF32 是张量核心使用的 TensorFloat-32 格式。
- 显微缩放指多组低精度数据共享局部缩放因子。
- 助记符（mnemonic）是反汇编器显示的操作码人类可读名称。

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

如果只把 `kind::f16` 换成 `kind::i8`，主助记符进入 `UTCIMMA` 家族。其他修饰符仍由 CTA group、来源模式和 collector 等维度决定。

## 为什么多个 kind 共享同一个主助记符

`f16` 和 `tf32` 都映射到 `UTCHMMA`，不代表二者机器语义相同。精确的 A/B/D 类型、矩阵 M/N/K 形状和主方向（row-major 或 column-major）还可能由指令描述符（instruction descriptor，`idesc`）提供。

A、B 是输入矩阵，D 是输出/累加矩阵。M、N、K 是矩阵乘法的三个尺寸：`M×K` 乘以 `K×N`。主方向指数据以行还是以列为连续方向。

本条目能给出主操作码家族规则，不能仅凭可见助记符恢复所有描述符字段。

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

## kind 是否改变外围 SASS

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

四个核心家族对应的 PTX。为突出 `kind`，都使用 CTA group 1 和直接参数上下文：

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

它们的 O3 代表性 SASS：

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

前三条说明：在操作数契约相同时，kind 直接选择 `UTCHMMA`、`UTCQMMA` 或 `UTCIMMA` 之一，外围和核心寄存器布局可以保持不变。最后一条多出的 `tmem[UR12]` 来自分块缩放，不应误归因给 `UTCOMMA` 这个操作码名称。

下面专门比较 `f8f6f4` 与 `i8` 在 O0 和 O3 两级的稳定性。对应 PTX 是：

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

O0 用来观察描述符、mask 和 `enable` 如何进入操作数；O3 用来读取最终寄存器布局。`UTCQMMA` 和 `UTCIMMA` 的选择在两优化级中保持不变。

对于不带分块缩放的 `f16`、`tf32`、`f8f6f4`、`i8`，外围指令选择集合不随 kind 变化：参数仍由同一组 `LDC`/`LDCU` 装载，谓词和控制仍使用同一组 `UISETP`/`PLOP3`/`ELECT`/`BRA` 指令。变化被限制在核心 MMA 家族内。

`f16` 和 `tf32` 都选择 `UTCHMMA`。在当前 `idesc` 运行时传入的实验中，二者连核心编码也相同；类型区别不由另一个 SASS 操作码表达，而由 `idesc` 的运行时内容表达。

以下计数用于确认上述选择关系在全部上下文和优化级中是否稳定。

这里把 `f16` 作为基线，在 kind 之外的 semantic form、源码写法、上下文和优化级完全相同的条件下，分别与 `tf32`、`f8f6f4`、`i8` 配对。每组有 1,504 个源码/上下文配对，乘以 O0–O3 后是 6,016 次 SASS 比较。

| kind 对比 | 完整函数指令数变化 | 外围指令类型变化 | 核心活跃寄存器变化 | 核心编码 |
|---|---|---|---|---|
| `tf32` 对 `f16` | 0/6,016 | 0/6,016 | 0/6,016 | 6,016/6,016 相同 |
| `f8f6f4` 对 `f16` | 0/6,016 | 0/6,016 | 0/6,016 | 6,016/6,016 不同 |
| `i8` 对 `f16` | 0/6,016 | 0/6,016 | 0/6,016 | 6,016/6,016 不同 |

外围指令指去掉目标 MMA 后函数中剩余的参数装载、谓词、选举、分支和完成协议指令。核心活跃寄存器指执行目标 MMA 时仍保存有效值的寄存器数量。

结论：

- 非分块缩放 kind 不会增加或删除外围 SASS，也不改变外围指令类型。
- `f8f6f4` 和 `i8` 改变核心操作码与编码。
- 当前运行时 `idesc` 写法下，`f16` 与 `tf32` 生成了完全相同的核心指令文本和编码，二者的具体类型区别由运行时描述符承载。
- 分块缩放 kind 还会增加 scale-factor 操作数，不能套用本节结论。见 [`block_scaling.md`](block_scaling.md)。

## 代表性覆盖口径

本页的七个已覆盖 kind 已经全部进入映射表，四个 SASS 操作码家族也都有真实 PTX 与 SASS 见证：

| 主要机制 | 代表内容 |
|---|---|
| `f16`/`tf32 → UTCHMMA` | 最小例子与同编码说明 |
| `f8f6f4`/`mxf8f6f4 → UTCQMMA` | O0/O3 对比与分块缩放交叉引用 |
| `i8 → UTCIMMA` | O0/O3 对比 |
| `mxf4`/`mxf4nvf4 → UTCOMMA` | `.4X` 代表例子 |
| 同操作码不等于同数据类型 | `f16`/`tf32` 与运行时 `idesc` 边界 |
| 非分块 kind 不改变外围序列 | 三组各 6,016 次严格配对 |
| kind 与 `.2CTA`/`.WS`/`.ASHIFT`/`.4X` 的组合 | 修饰符组合段 |

当前生成矩阵中的主要静态操作码选择机制均已覆盖。`idesc` 位型尚未逐字段冻结，因此不把这项结果外推为数据类型、形状或机器编码位的百分比覆盖。

## 证据与边界

- 对 expanded 归属配对的 52,736 条目标出现位置检查，kind → 主助记符规则反例为 0。
- `ptxas` 和 `nvdisasm` 均来自 CUDA 13.0。
- 结论适用于 PTX ISA 9.0、编译目标 `sm_110a`。
- 尚未逐字段冻结 `idesc`，所以不能据此给出精确数据类型/形状编码位。
