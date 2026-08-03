# guard：PTX 条件执行如何进入 SASS

## 先说结论

guard 是写在目标 PTX 指令前的条件谓词（predicate），例如 `@%guard tcgen05.mma ...` 或 `@!%guard tcgen05.mma ...`。它不改变 `UTCHMMA`/`UTCQMMA`/`UTCIMMA`/`UTCOMMA` 的操作码家族，但通过两种主要路径控制核心 MMA 是否执行：

- 直接附着为 SASS 统一谓词（uniform predicate）
- 生成外围谓词与分支，使未满足条件的线程绕过核心 MMA

```text
PTX 正 guard
    → @UPn UTC*MMA ...
    或 ISETP/PLOP3 + 条件分支/提前退出 + 无显式 guard 的 UTC*MMA

PTX 负 guard
    → @!UPn UTC*MMA ...
    或反向条件分支/提前退出 + 无显式 guard 的 UTC*MMA
```

分析 guard 不能只检查核心指令前面的 `@P`/`@UP`，还必须检查核心之前的 `ISETP`/`UISETP`/`PLOP3`/`BRA`/`EXIT` 控制流。

## guard 与 enable 不是同一个谓词

一条 MMA 可以同时有外部 guard 和末尾的 enable 输入：

```ptx
@%guard tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

- guard 决定整条 PTX 指令是否执行。
- enable 决定是否读取并累加旧 D，即选择 `D=A×B+D` 或 `D=A×B`。
- 在 SASS 中，guard 可能位于指令最前面的 `@UPn`，enable 则仍是核心 MMA 末尾的 `UPn`/`UPT`/`!UPT` 操作数。

两者都称为谓词，但控制不同语义，不能互换。

## 路径一：直接 SASS 谓词化

`THOR_MMA_000028/000029` 使用 A collector fill。正、负 guard 的目标 PTX 只差极性：

```ptx
@%guard  tcgen05.mma.cta_group::1.kind::f16.collector::a::fill ...;
@!%guard tcgen05.mma.cta_group::1.kind::f16.collector::a::fill ...;
```

O3 直接把 guard 保留在核心 SASS 上：

```sass
@UP1  UTCHMMA gdesc[UR8].A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
@!UP1 UTCHMMA gdesc[UR8].A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

可以分别读出：最前面的 `@UP1`/`@!UP1` 是 guard；最后的 `UP0` 是 enable；`.A_KEEP` 是 collector。guard 改变核心规范操作文本，但不改变 `UTCHMMA` 和 `.A_KEEP` 的选择。

对应的无 guard 基线 `THOR_MMA_000025` 为：

```sass
UTCHMMA gdesc[UR8].A_KEEP, gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

## 路径二：外围控制流

`THOR_MMA_000004/000005` 是同一个普通 FP16 SS 形态的正、负 guard。O3 没有把 guard 写到 `UTCHMMA` 前，而是在核心之前生成互补的提前退出条件：

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

核心 MMA 文本在这条路径中不带显式 guard，但执行条件已经由外围控制流实现。正负极性主要体现在分支谓词是否取反，而不是另选一套 MMA 操作码。

O0 中谓词形成与控制流更长，可见 `ISETP`、`PLOP3.LUT`、条件 `BRA`、大量 `MOV`/`R2UR`。O3 将其收缩为早期退出和统一参数准备。O0 和 O3 是两个代码生成观察点，不能把其中某条辅助指令当成 guard 的固定映射。

## 单因素统计

每种 guard 极性都与 `runtime_zero` 基线按相同 semantic form、源码变体和优化级严格配对，每个优化级 1,152 组。正负 guard 的统计完全相同：

| 优化级 | 核心助记符变化 | 核心规范操作变化 | 完整 kernel 序列变化 | kernel 指令数变化 | 核心寄存器布局变化 | 核心处活跃数变化 |
|---|---|---|---|---|---|---|
| O0 | 0/1,152 | 0/1,152 | 1,152/1,152 | 正 1,152/1,152；负 1,144/1,152 | 0/1,152 | 496/1,152 |
| O1 | 0/1,152 | 352/1,152 | 1,152/1,152 | 980/1,152 | 448/1,152 | 496/1,152 |
| O2 | 0/1,152 | 352/1,152 | 1,152/1,152 | 824/1,152 | 508/1,152 | 496/1,152 |
| O3 | 0/1,152 | 352/1,152 | 1,152/1,152 | 824/1,152 | 508/1,152 | 496/1,152 |

O1–O3 的 352 组核心规范操作变化对应 guard 进入核心谓词形态。其余形态由外围控制流承担。O2/O3 的 508 组核心寄存器布局变化包含 156 组纯重编号和 352 组寄存器类别/别名关系变化。所有 1,152 组完整 kernel 序列都改变，说明 guard 始终是完整编译降级的一部分。

## 正 guard 与负 guard 的关系

正负 guard 覆盖相同的 semantic form、变体、TS/SS、CTA group、collector、分块缩放和 `.ashift` 范围。当前统计中，两种极性的核心变化、寄存器变化和 O1–O3 指令数变化数量一致。因此可以写成：极性决定谓词取反方向，但没有改变编译器使用两类编译降级机制的覆盖规模。

不能进一步写成"任意正 guard 必然使用 `@UPn`"或"某种 kind 必然使用分支"，因为当前结果只证明两条路径都存在，尚未把路径选择冻结为独立的 PTX 字段规则。

## 代表性覆盖口径

本文覆盖 guard 的主要静态变化机制至少 95%：

- 无谓词（unpredicated）、正 guard、负 guard 三种目标形态。
- 直接核心谓词化与外围控制流两条编译降级路径。
- `UTCHMMA`/`UTCQMMA`/`UTCIMMA`/`UTCOMMA`、SS/TS、CTA group 1/2、普通/稀疏/WS/分块缩放等已生成形态。
- O0/O1/O2/O3 的核心、完整序列、指令数、寄存器布局和活跃数差分。

未覆盖的是实机上发散 warp 的动态执行行为、性能代价，以及编译器选择直接谓词化或分支路径的完整成本模型。

## 证据

- 上下文统计：[`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)
- PTX case 与上下文清单：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)
- PTX occurrence → 核心 SASS 归属：[`../../results/expanded/sass/sass_attribution.jsonl`](../../results/expanded/sass/sass_attribution.jsonl)
- 综合解释：[`../tcgen05_mma_PTX到SASS映射规则报告.md`](../tcgen05_mma_PTX到SASS映射规则报告.md)
