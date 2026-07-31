# 操作数来源：TS、SS、TMEM 与 SMEM descriptor

## TS/SS 表示什么

两个字母依次描述矩阵 A、B 的来源：

- `T`：Tensor Memory，简称 TMEM；
- `S`：shared-memory descriptor，描述 SMEM 中的数据。

当前 `tcgen05.mma` 覆盖：

| 模式 | A 来源 | B 来源 |
|---|---|---|
| SS | SMEM descriptor | SMEM descriptor |
| TS | TMEM address | SMEM descriptor |

**address** 是数据所在位置的地址；**descriptor** 是描述地址和布局的编码值。

## PTX 写法

SS：

```ptx
tcgen05.mma... [%d_tmem], %desc_a, %desc_b, ...
```

TS：

```ptx
tcgen05.mma... [%d_tmem], [%a_tmem], %desc_b, ...
```

方括号 `[...]` 表示把其中的值解释为 TMEM 地址。

## SASS 映射

| 模式 | 核心 SASS 前两个源操作数 |
|---|---|
| SS | `gdesc[A]`, `gdesc[B]` |
| TS | `tmem[A]`, `gdesc[B]` |

实际例子：

```sass
// SS
UTCHMMA gdesc[UR8], gdesc[UR10], ...

// TS
UTCHMMA tmem[UR7], gdesc[UR8], ...
```

`gdesc` 是 SASS 中的通用 descriptor 操作数；`tmem` 是 TMEM 操作数； `UR` 是 uniform general-purpose register，即 uniform 通用寄存器。

## 为什么没有 TT 或 ST

在当前 PTX 9.0 `tcgen05.mma` 形态中，B 固定由 `%desc_b` 描述，没有 B 直接使用 TMEM address 的对称形式。因此：

- TT 不是当前正向文法中的合法来源组合；
- ST 也不是当前正向文法中的合法来源组合。

这不是生成器遗漏，而是指令操作数角色本身不对称。

## 覆盖量

| 模式 | semantic form | syntax 实现 | expanded 实现 |
|---|---:|---:|---:|
| SS | 432 | 552 | 4,416 |
| TS | 464 | 600 | 4,800 |

TS 数量更多，因为 `.ashift` 只允许 A 来自 TMEM。

## 对寄存器压力的观察

在 O1/O2/O3 baseline 的核心 MMA 位置：

| 模式 | 平均活跃 UGPR | 最大活跃 UGPR |
|---|---:|---:|
| SS | 8.21 | 9 |
| TS | 7.12 | 8 |

**活跃寄存器** 指当前保存有效值、之后还可能被使用的寄存器。SS 平均多约一个活跃 UGPR，符合 A descriptor 比 A TMEM address 需要更多 uniform 状态的现象。这是资源观察，不是性能结论。

## 与其他 modifier 的关系

- `.ashift` 只适用于 TS。
- SS 和 TS 都覆盖普通、稀疏和 block-scaled 的合法形态。
- `.ws` 下仍然存在 SS/TS；B 始终是 descriptor，并可使用 B collector。
- A collector modifier 会附着在 SS 的 `gdesc[A]` 或 TS 的 `tmem[A]` 上。

## 是否改变外围 SASS

TS/SS 首先选择不同的核心操作数类别：

```text
SS
    PTX: %desc_a
    SASS: gdesc[URa]

TS
    PTX: [%a_tmem]
    SASS: tmem[URa]
```

这进一步决定 A 的准备指令集合：

| A 的来源和产生方式 | SASS 指令选择 |
|---|---|
| SS，直接传入 64 位 descriptor | `LDCU.64` 或组成它的 uniform load |
| TS，直接传入 32 位 TMEM address | `LDCU`；不再需要 A descriptor 的 64 位装载 |
| SS，derived producer | `LDC.64` + `MOV/R2UR` |
| TS，derived producer | `LDC` + `IADD3` |
| 两者的调度差异 | 可能选择或删除 `NOP`、`LOP3.LUT` |

因此它不是抽象的“寄存器压力发生变化”，而是明确的 load/address-generation 选择：

```text
64 位 descriptor 路径
    → LDCU.64 或 LDC.64 + MOV/R2UR

32 位 TMEM address 路径
    → LDCU 或 LDC + IADD3
```

O0 能看到两种来源的原始地址形成过程。SS case `THOR_MMA_000001` 将两个 64 位 descriptor 分别搬到 uniform register。以下是选指相关片段，省略部分同值 `MOV` 和无关 mask 准备。先看两个 case 的目标 PTX：

```ptx
// SS：A 是 64 位 shared-memory descriptor
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

// TS：A 是 32 位 TMEM address
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

```sass
MOV      R2, 0x8;
LDC.64   R2, c[0x0][R2+0x380];
MOV      R15, R2;
MOV      R16, R3;
MOV      R2, 0x10;
LDC.64   R2, c[0x0][R2+0x380];
MOV      R13, R2;
MOV      R14, R3;
R2UR     UR4, R2;
R2UR     UR5, R3;
R2UR     UR6, R6;
R2UR     UR7, R7;
UTCHMMA  gdesc[UR4], gdesc[UR6],
          tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;
```

TS case `THOR_MMA_000161` 只保留 B 的 64 位 descriptor；A 作为 32 位 TMEM address 经过 `IADD3` 和 `R2UR`：

```sass
MOV      R2, 0x4;
LDC      R2, c[0x0][R2+0x380];
MOV      R4, R2;
MOV      R2, 0x10;
LDC.64   R2, c[0x0][R2+0x380];
MOV      R12, R2;
MOV      R13, R3;
IADD3    R11, PT, PT, R4, RZ, RZ;
R2UR     UR4, R4;
R2UR     UR5, R5;
R2UR     UR13, R11;
UTCHMMA  tmem[UR13], gdesc[UR4],
          tmem[UR12], tmem[UR6], idesc[UR7], UR8, UP0;
```

到 O3，装载和搬运被合并。SS 为 A、B 各选择一个 64 位 descriptor load：

```sass
LDCU      UR6,  c[0x0][0x380];
LDCU.64   UR8,  c[0x0][0x388];
LDCU.64   UR10, c[0x0][0x390];
UTCHMMA   gdesc[UR8], gdesc[UR10],
           tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

TS 把相邻的 D/A 两个 32 位 TMEM address 合成一次 `LDCU.64`，只保留 B descriptor：

```sass
LDCU.64   UR6, c[0x0][0x380];
LDCU.64   UR8, c[0x0][0x390];
UTCHMMA   tmem[UR7], gdesc[UR8],
           tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

O0 说明来源差异如何通过 `LDC/LDC.64 + IADD3/MOV/R2UR` 形成；O3 展示最终的 `LDCU.64` 合并结果。核心映射始终是 `gdesc → tmem`。

以下统计用于说明这条选择关系在所有合法 variant 和上下文中都存在。

会。排除只有 TS 才合法的 `.ashift` 后，将 TS 与对应 SS 设计严格配对，得到 4,416 个源码/上下文配对，即 17,664 次 O0–O3 比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 4,016/17,664 |
| 外围指令类型或排列 | 17,664/17,664 |
| 核心 MMA 操作数与寄存器摆放 | 17,664/17,664 |
| 核心位置活跃寄存器 | 17,664/17,664 |
| 核心 MMA 编码 | 17,664/17,664 |

这是本实验中影响最稳定的维度之一。原因是：

- SS 的 A 是 64 位 descriptor，需要形成 `gdesc[...]`；
- TS 的 A 是 32 位 TMEM address，需要形成 `tmem[...]`；
- 两种输入宽度和寄存器类别不同，因此参数装载、数据搬运和寄存器分配必然不同。

4,016 次指令数变化全部是 TS 比配对 SS 少 8 条；其余比较虽然总数相同，外围指令类型或排列仍然不同。也就是说，TS/SS 不能只通过观察核心 MMA 的第一个操作数来研究，它会系统性影响整个函数的准备序列。

## 跨 variant 的来源见证

普通 f16 的 O0/O3 对比已经展示装载路径。下面用真实 O3 核心指令确认同一 `gdesc[A] ↔ tmem[A]` 规则也贯穿 sparse、WS 和 block-scaled 形态：

| 形态 | SS case 与核心 | TS case 与核心 |
|---|---|---|
| `mma.sp + f16` | `THOR_MMA_000833`：`UTCHMMA gdesc[UR6], gdesc[UR8], ...` | `THOR_MMA_000993`：`UTCHMMA tmem[UR5], gdesc[UR8], ...` |
| `mma.ws + f16` | `THOR_MMA_004865`：`UTCHMMA.WS gdesc[UR8], gdesc[UR10], ...` | `THOR_MMA_005953`：`UTCHMMA.WS tmem[UR7], gdesc[UR8], ...` |
| block-scaled `mxf8f6f4` | `THOR_MMA_001665`：`UTCQMMA gdesc[UR8], gdesc[UR10], ...` | `THOR_MMA_002065`：`UTCQMMA tmem[UR7], gdesc[UR8], ...` |

其中 sparse metadata、`.WS` 和 scale-factor 操作数仍由各自 variant 决定；来源维度只负责把 A 路径从 64 位 descriptor 换成 32 位 TMEM address。B 在所有这些合法形态中仍为 `gdesc[B]`。

## 代表性覆盖口径

| 主要机制 | 覆盖位置 |
|---|---|
| SS 的 `gdesc[A], gdesc[B]` | 基础映射与 O0/O3 |
| TS 的 `tmem[A], gdesc[B]` | 基础映射与 O0/O3 |
| 64 位 descriptor 与 32 位 address 的外围选指 | `LDCU.64/LDC.64` 对 `LDCU/LDC+IADD3` |
| 直接参数与 derived producer | O3 与 O0 |
| 普通、sparse、WS、block-scaled variant | 跨 variant 表 |
| A collector 的不同附着点 | 与 collector 的关系 |
| `.ashift` 仅允许 TS | 关系与排除后的严格配对 |
| TT/ST 非法边界 | 文法说明 |

这些主要静态来源机制均有示例或全量统计，保守记为 **至少 95% 的主要变化机制**。未覆盖的部分是运行时 descriptor 内容和不存在于正向文法中的 TT/ST 执行语义。

## 证据

- 对 52,736 条目标 occurrence 检查 A 的首个 SASS 源操作数，来源反例为 0。
- SS 完整函数见综合报告附录 A.1。
- TS 完整函数见综合报告附录 A.2。
