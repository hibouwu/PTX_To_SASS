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

`gdesc` 是 SASS 中的通用 descriptor 操作数；`tmem` 是 TMEM 操作数；
`UR` 是 uniform general-purpose register，即 uniform 通用寄存器。

## 为什么没有 TT 或 ST

在当前 PTX 9.0 `tcgen05.mma` 形态中，B 固定由 `%desc_b` 描述，没有 B 直接使用
TMEM address 的对称形式。因此：

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

**活跃寄存器** 指当前保存有效值、之后还可能被使用的寄存器。SS 平均多约一个
活跃 UGPR，符合 A descriptor 比 A TMEM address 需要更多 uniform 状态的现象。
这是资源观察，不是性能结论。

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

因此它不是抽象的“寄存器压力发生变化”，而是明确的 load/address-generation
选择：

```text
64 位 descriptor 路径
    → LDCU.64 或 LDC.64 + MOV/R2UR

32 位 TMEM address 路径
    → LDCU 或 LDC + IADD3
```

以下统计用于说明这条选择关系在所有合法 variant 和上下文中都存在。

会。排除只有 TS 才合法的 `.ashift` 后，将 TS 与对应 SS 设计严格配对，得到
4,416 个源码/上下文配对，即 17,664 次 O0–O3 比较：

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

4,016 次指令数变化全部是 TS 比配对 SS 少 8 条；其余比较虽然总数相同，
外围指令类型或排列仍然不同。也就是说，TS/SS 不能只通过观察核心 MMA 的第一个
操作数来研究，它会系统性影响整个函数的准备序列。

## 证据

- 对 52,736 条目标 occurrence 检查 A 的首个 SASS 源操作数，来源反例为 0。
- SS 完整函数见综合报告附录 A.1。
- TS 完整函数见综合报告附录 A.2。
