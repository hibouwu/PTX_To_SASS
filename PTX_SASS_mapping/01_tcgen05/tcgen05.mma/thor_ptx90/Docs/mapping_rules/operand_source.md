# 操作数来源：TS、SS、TMEM 与 SMEM 描述符如何对应

## TS/SS 表示什么

两个字母依次描述矩阵 A、B 的来源：

- `T`：张量内存（Tensor Memory，TMEM）
- `S`：共享内存描述符（shared-memory descriptor），描述 SMEM 中的数据

当前 `tcgen05.mma` 覆盖两种模式：

| 模式 | A 来源 | B 来源 |
|---|---|---|
| SS | SMEM 描述符 | SMEM 描述符 |
| TS | TMEM 地址 | SMEM 描述符 |

地址是数据所在位置的地址。描述符（descriptor）是描述地址和布局的编码值。

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

`gdesc` 是 SASS 中的通用描述符操作数。`tmem` 是 TMEM 操作数。`UR` 是统一通用寄存器（Uniform General-Purpose Register）。

## 为什么没有 TT 或 ST

在当前 PTX ISA 9.0 `tcgen05.mma` 形态中，B 固定由 `%desc_b` 描述，没有 B 直接使用 TMEM address 的对称形式。TT 和 ST 都不是当前正向文法中的合法来源组合。这是指令操作数角色本身不对称，不是生成器遗漏。

## 覆盖量

| 模式 | semantic form | syntax 实现 | expanded 实现 |
|---|---|---|---|
| SS | 432 | 552 | 4,416 |
| TS | 464 | 600 | 4,800 |

TS 数量更多，因为 `.ashift` 只允许 A 来自 TMEM。

## 对寄存器压力的观察

在 O1/O2/O3 baseline 的核心 MMA 位置：

| 模式 | 平均活跃 UGPR | 最大活跃 UGPR |
|---|---|---|
| SS | 8.21 | 9 |
| TS | 7.12 | 8 |

SS 平均多约一个活跃 UGPR，符合 A 描述符比 A TMEM 地址需要更多统一状态的现象。这是资源观察，不是性能结论。

## 与其他修饰符的关系

- `.ashift` 只适用于 TS。
- SS 和 TS 都覆盖普通、稀疏和分块缩放的合法形态。
- `.ws` 下仍然存在 SS/TS；B 始终是描述符，并可使用 B collector。
- A collector 修饰符会附着在 SS 的 `gdesc[A]` 或 TS 的 `tmem[A]` 上。

## 操作数来源是否改变外围 SASS

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
| SS，直接传入 64 位描述符 | `LDCU.64` 或组成它的统一装载 |
| TS，直接传入 32 位 TMEM 地址 | `LDCU`；不再需要 A 描述符的 64 位装载 |
| SS，derived producer | `LDC.64` + `MOV`/`R2UR` |
| TS，derived producer | `LDC` + `IADD3` |
| 两者的调度差异 | 可能选择或删除 `NOP`、`LOP3.LUT` |

这不是抽象的"寄存器压力发生变化"，而是明确的装载和地址生成选择：

```text
64 位描述符路径
    → LDCU.64 或 LDC.64 + MOV/R2UR

32 位 TMEM 地址路径
    → LDCU 或 LDC + IADD3
```

O3 中，SS 为 A、B 各选择一个 64 位描述符装载：

```sass
LDCU      UR6,  c[0x0][0x380];
LDCU.64   UR8,  c[0x0][0x388];
LDCU.64   UR10, c[0x0][0x390];
UTCHMMA   gdesc[UR8], gdesc[UR10],
           tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

TS 把相邻的 D/A 两个 32 位 TMEM 地址合成一次 `LDCU.64`，只保留 B 描述符：

```sass
LDCU.64   UR6, c[0x0][0x380];
LDCU.64   UR8, c[0x0][0x390];
UTCHMMA   tmem[UR7], gdesc[UR8],
           tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

核心映射始终是 `gdesc → tmem`。

排除只有 TS 才合法的 `.ashift` 后，将 TS 与对应 SS 设计严格配对，得到 4,416 个源码/上下文配对，即 17,664 次 O0–O3 比较：

| 检查项 | 发生变化 |
|---|---|
| 完整函数 SASS 指令数 | 4,016/17,664 |
| 外围指令类型或排列 | 17,664/17,664 |
| 核心 MMA 操作数与寄存器摆放 | 17,664/17,664 |
| 核心位置活跃寄存器 | 17,664/17,664 |
| 核心 MMA 编码 | 17,664/17,664 |

这是本实验中影响最稳定的维度之一。原因：SS 的 A 是 64 位描述符，需要形成 `gdesc[...]`；TS 的 A 是 32 位 TMEM 地址，需要形成 `tmem[...]`。两种输入宽度和寄存器类别不同，因此参数装载、数据搬运和寄存器分配必然不同。

4,016 次指令数变化全部是 TS 比配对 SS 少 8 条。其余比较虽然总数相同，外围指令类型或排列仍然不同。TS/SS 不能只通过观察核心 MMA 的第一个操作数来研究，它会系统性影响整个函数的准备序列。

## 跨变体的来源见证

同一 `gdesc[A] ↔ tmem[A]` 规则也贯穿稀疏、WS 和分块缩放形态（均以 O3 为例）：

| 形态 | SS case 与核心 | TS case 与核心 |
|---|---|---|
| `mma.sp + f16` | `THOR_MMA_000833`：`UTCHMMA gdesc[UR6], gdesc[UR8], ...` | `THOR_MMA_000993`：`UTCHMMA tmem[UR5], gdesc[UR8], ...` |
| `mma.ws + f16` | `THOR_MMA_004865`：`UTCHMMA.WS gdesc[UR8], gdesc[UR10], ...` | `THOR_MMA_005953`：`UTCHMMA.WS tmem[UR7], gdesc[UR8], ...` |
| 分块缩放 `mxf8f6f4` | `THOR_MMA_001665`：`UTCQMMA gdesc[UR8], gdesc[UR10], ...` | `THOR_MMA_002065`：`UTCQMMA tmem[UR7], gdesc[UR8], ...` |

稀疏元数据、`.WS` 和 scale-factor 操作数仍由各自变体决定。来源维度只负责把 A 路径从 64 位描述符换成 32 位 TMEM 地址。B 在所有这些合法形态中仍为 `gdesc[B]`。

## 代表性覆盖口径

| 主要机制 | 覆盖位置 |
|---|---|
| SS 的 `gdesc[A], gdesc[B]` | 基础映射与 O0/O3 |
| TS 的 `tmem[A], gdesc[B]` | 基础映射与 O0/O3 |
| 64 位描述符与 32 位地址的外围指令选择 | `LDCU.64`/`LDC.64` 对 `LDCU`/`LDC+IADD3` |
| 直接参数与 derived producer | O3 与 O0 |
| 普通、稀疏、WS、分块缩放变体 | 跨变体表 |
| A collector 的不同附着点 | 与 collector 的关系 |
| `.ashift` 仅允许 TS | 关系与排除后的严格配对 |
| TT/ST 非法边界 | 文法说明 |

当前生成集合中的主要静态来源机制均有示例或全量统计。描述符内部内容不属于本项目的静态 PTX→SASS 映射对象，不存在于正向文法中的 TT/ST 也没有可配对样本，因此不声明总体百分比。

## 证据

- 对 52,736 条目标出现位置检查 A 的首个 SASS 源操作数，来源反例为 0。
- SS 完整函数见综合报告附录 A.1。
- TS 完整函数见综合报告附录 A.2。
