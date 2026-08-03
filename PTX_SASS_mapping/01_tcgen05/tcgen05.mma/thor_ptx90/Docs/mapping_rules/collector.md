# 操作数收集器（collector）：操作数保留与复用如何映射

## 先说结论

collector 不改变 `UTCHMMA`、`UTCQMMA` 等主操作码，而是改变 A 或 B 操作数后面的修饰符：

```text
fill     → KEEP
use      → REUSE + KEEP
lastuse  → REUSE
discard  → 不带 KEEP/REUSE
```

collector 是张量核心（Tensor Core）暂存并复用操作数的硬件机制。`KEEP` 表示本次使用后继续保留。`REUSE` 表示本次使用已经收集的值。

## A collector

A collector 用在普通 `mma` 或 `mma.sp` 形态。它的状态写在 A 操作数上：

| PTX | SASS A 操作数 |
|---|---|
| `.collector::a::discard` | 无 `.A_KEEP` 或 `.A_REUSE` |
| `.collector::a::fill` | `.A_KEEP` |
| `.collector::a::use` | `.A_REUSE.A_KEEP` |
| `.collector::a::lastuse` | `.A_REUSE` |

例如：

```text
PTX:  .collector::a::fill
SASS: gdesc[UR8].A_KEEP

PTX:  .collector::a::use
SASS: gdesc[UR8].A_REUSE.A_KEEP

PTX:  .collector::a::lastuse
SASS: gdesc[UR8].A_REUSE
```

`gdesc[UR8]` 表示由统一寄存器（Uniform Register，UR）`UR8` 保存的共享内存描述符。

## B collector

B collector 用在权重驻留（Weight-Stationary，WS）形态。状态写在 B 操作数上：

| PTX | SASS B 操作数 |
|---|---|
| `.collector::bN::discard` | 无 `.B_KEEP` 或 `.B_REUSE` |
| `.collector::bN::fill` | `.B_KEEP` |
| `.collector::bN::use` | `.B_REUSE.B_KEEP` |
| `.collector::bN::lastuse` | `.B_REUSE` |

`N` 选择 collector 缓冲区：

| PTX buffer | SASS |
|---|---|
| `b0` | 默认缓冲区，不显示编号 |
| `b1` | `.BUFFER1` |
| `b2` | `.BUFFER2` |
| `b3` | `.BUFFER3` |

完整的 B2 状态转换例子：

```ptx
tcgen05.mma.ws.cta_group::1.kind::f16.collector::b2::fill
    [%d_tmem], %desc_a, %desc_b, %idesc, %enable;

tcgen05.mma.ws.cta_group::1.kind::f16.collector::b2::use
    [%d_tmem], %desc_a, %desc_b, %idesc, %enable;
```

同一个 `THOR_MMA_000620` 在 O3 中的核心指令：

```sass
UTCHMMA.WS gdesc[UR8],
            gdesc[UR10].B_KEEP.BUFFER2,
            tmem[UR6], tmem[UR4], idesc[UR5], UP0;

UTCHMMA.WS gdesc[UR8],
            gdesc[UR10].B_REUSE.B_KEEP.BUFFER2,
            tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

第一条把 B 装入 B2 并保留；第二条复用 B2 中的值，并继续保留给后续指令。完整函数级上下文见[综合报告的附录 A.3](../tcgen05_mma_PTX到SASS映射规则报告.md)。

## 适用范围和前置条件

- A collector 属于普通 MMA。B collector 属于 WS MMA。
- `use` 和 `lastuse` 不是孤立动作，前面必须有匹配的 `fill`。
- `discard` 可以显式写出，也可以使用缺省拼写。两者是不同的源码写法，但规范化后属于同一语义。
- collector 修饰符位于操作数上。只比较主助记符会漏掉这类变化。

## collector 是否改变外围 SASS

collector 的完整选择关系全部位于核心 MMA 操作数上：

```text
a::discard  → A 无修饰符
a::fill     → .A_KEEP
a::use      → .A_REUSE.A_KEEP
a::lastuse  → .A_REUSE

bN::discard → [无 KEEP/REUSE] + [BUFFERn]
bN::fill    → .B_KEEP + [BUFFERn]
bN::use     → .B_REUSE.B_KEEP + [BUFFERn]
bN::lastuse → .B_REUSE + [BUFFERn]
```

外围指令选择集合是空集：collector 不选择额外的 load、move、predicate、branch 或 barrier 指令。fill/use/lastuse/discard 就编码在 `UTC*MMA` 的 A/B 操作数修饰符中，不存在某条单独的"collector fill SASS 指令"。

四组严格配对结果如下：

| 配对 | SASS 比较数 | 指令数变化 | 外围类型变化 | 核心活跃寄存器变化 |
|---|---|---|---|---|
| 显式 `discard` 对缺省 `discard` | 4,608 | 0 | 0 | 0 |
| `fill` 对显式 `discard` | 3,584 | 0 | 0 | 0 |
| `fill→use` 对 `fill→lastuse` | 7,680 | 0 | 0 | 0 |
| B1/B2/B3 对 B0 | 12,288 | 0 | 0 | 0 |

显式与缺省 `discard` 的核心指令文本和编码也完全相同，两种 PTX 拼写在当前编译降级中是严格等价的。

去掉 `KEEP`、`REUSE` 和 `BUFFERn` 文本后，以上配对的核心 SASS 操作数及寄存器编号也全部相同。除显式/缺省 `discard` 外，其余 collector 状态或 buffer 改变时，核心机器编码全部不同。结论是：

```text
collector 状态
    → 原位修改 MMA 操作数修饰符和编码
    → 不额外生成准备、控制或完成指令
```

需要区分"修饰符的影响"和"PTX 序列本来就更长"。`fill→use` 有两条 MMA，当然会比单条 `discard` 产生更多核心指令（这不是 `use` 自动展开了外围 SASS，而是输入 PTX 本身包含两条目标指令）。上表只比较目标指令数相同的状态序列。

## collector 的已隔离机器编码字段

O3 `runtime_zero` 中，保留具体寄存器并移除单个被测 modifier 后分组。独立 witness 组是不同控制坐标的证据单元；候选 pair 还包含等价 source spelling 和同组重复实例形成的笛卡尔积：

| collector 变化 | 独立 witness 组 | 候选 pair | word 0 XOR | word 1 XOR |
|---|---:|---:|---:|---:|
| A discard→fill/keep，即增加 `.A_KEEP` | 176 | 1,264 | `0x0000000000000000` | `0x0000000000100000` |
| B discard/lastuse→fill/use，即增加 `.B_KEEP` | 256 | 608 | `0x0000000000000000` | `0x0000000000020000` |
| B0→B1，即增加 `.BUFFER1` | 160 | 288 | `0x0000000000000000` | `0x0000000000008000` |
| B0→B2，即增加 `.BUFFER2` | 160 | 288 | `0x0000000000000000` | `0x0000000000010000` |
| B0→B3，即增加 `.BUFFER3` | 160 | 288 | `0x0000000000000000` | `0x0000000000018000` |

B buffer 因而是 word 1 的两位字段：B0=`0x00000`、B1=`0x08000`、B2=`0x10000`、B3=`0x18000`。`A/B_REUSE` 的配对都包含一个稳定公共候选位，但高位调度控制字段也随序列位置变化；在未进一步冻结调度控制前，本页不把公共位升级为独立确定性字段。完整结果见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)，方法边界见 [`descriptor_and_encoding.md`](descriptor_and_encoding.md)。

## A collector 的跨来源实证

A collector 在 SS 与 TS 两种模式上使用同一状态机，但修饰符附着的操作数类别不同。真实 O3 配对如下：

```sass
// SS，THOR_MMA_000025：fill → use
UTCHMMA gdesc[UR8].A_KEEP, gdesc[UR10], ...;
UTCHMMA gdesc[UR8].A_REUSE.A_KEEP, gdesc[UR10], ...;

// TS，THOR_MMA_000185：fill → use
UTCHMMA tmem[UR7].A_KEEP, gdesc[UR8], ...;
UTCHMMA tmem[UR7].A_REUSE.A_KEEP, gdesc[UR8], ...;
```

collector 状态不等同于 `gdesc` 专用后缀：SS 时附着于 `gdesc[A]`，TS 时附着于 `tmem[A]`。合法的 `.ashift` 最终使用也可以复合：

```sass
// THOR_MMA_000633，group 2 的 fill → ashift + lastuse
UTCHMMA.2CTA        tmem[UR7].A_KEEP,  gdesc[UR8], ...;
UTCHMMA.2CTA.ASHIFT tmem[UR7].A_REUSE, gdesc[UR8], ...;
```

第一条 fill 选择 `A_KEEP`；第二条 lastuse 选择 `A_REUSE`，同时由第二条 PTX 的 `.ashift` 增加 `.ASHIFT`。状态序列、来源类型和主指令修饰符可以分别归因。

## 代表性覆盖口径

| 主要机制 | 覆盖位置 |
|---|---|
| A 的 discard/fill/use/lastuse | A 状态表、严格配对与跨来源实证 |
| B 的 discard/fill/use/lastuse | B 状态表与 B2 完整例子 |
| B0–B3 buffer 编码 | buffer 表与 12,288 次配对 |
| SS 的 `gdesc[A]` 与 TS 的 `tmem[A]` 附着点 | 跨来源实证 |
| 普通、稀疏、分块缩放、WS 变体的合法角色分工 | 适用范围与 expanded 覆盖 |
| 与 `.ashift`、`.2CTA` 的正交组合 | `THOR_MMA_000633` |
| 不产生外围 collector 指令 | 四组严格配对统计 |
| fill→use/lastuse 的状态机前置条件 | 适用范围 |

按当前主要静态机制清单，代表例子和统计已经覆盖状态、缓冲区、来源、变体角色和外围边界。未逐条展开的是不同 kind、优化级和缓冲区的重复 SASS 文本；本文不把重复实例数量换算成总体百分比。

## 不能从本结果推出什么

这些结果能证明 PTX collector 状态和反汇编文本之间的稳定映射，但没有测量 collector 的容量、驻留时间、冲突代价或性能收益。它们需要实机性能实验。

## 证据

- `syntax` 和 `expanded` 集合覆盖 A collector、B0–B3，以及 discard、fill、`fill→use`、`fill→lastuse`。
- 四个优化级的目标出现位置均按 PTX 出现位置归属到核心 SASS。
- 当前覆盖样本中的 `KEEP`、`REUSE` 和 `BUFFERn` 映射没有发现反例。
