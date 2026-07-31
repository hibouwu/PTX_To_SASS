# collector：操作数保留与复用

## 先说结论

collector 不改变 `UTCHMMA`、`UTCQMMA` 等主 opcode，而是改变 A 或 B
操作数后面的 modifier：

```text
fill     → KEEP
use      → REUSE + KEEP
lastuse  → REUSE
discard  → 不带 KEEP/REUSE
```

**collector** 是 Tensor Core 暂存并复用操作数的硬件机制。**KEEP** 表示本次
使用后继续保留，**REUSE** 表示本次使用已经收集的值。

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

`gdesc[UR8]` 表示由 uniform register `UR8` 保存的 shared-memory
descriptor。**uniform register（统一寄存器）**保存整个 warp 共同使用的值。

## B collector

B collector 用在 weight-stationary（WS，权重驻留）形态。状态写在 B
操作数上：

| PTX | SASS B 操作数 |
|---|---|
| `.collector::bN::discard` | 无 `.B_KEEP` 或 `.B_REUSE` |
| `.collector::bN::fill` | `.B_KEEP` |
| `.collector::bN::use` | `.B_REUSE.B_KEEP` |
| `.collector::bN::lastuse` | `.B_REUSE` |

`N` 选择 collector buffer：

| PTX buffer | SASS |
|---|---|
| `b0` | 默认 buffer，不显示编号 |
| `b1` | `.BUFFER1` |
| `b2` | `.BUFFER2` |
| `b3` | `.BUFFER3` |

完整的 B2 状态转换是：

```ptx
tcgen05.mma.ws.cta_group::1.kind::f16.collector::b2::fill
    [%d_tmem], %desc_a, %desc_b, %idesc, %enable;

tcgen05.mma.ws.cta_group::1.kind::f16.collector::b2::use
    [%d_tmem], %desc_a, %desc_b, %idesc, %enable;
```

对应的两条核心 SASS 是：

```sass
UTCHMMA.WS gdesc[UR8],
            gdesc[UR10].B_KEEP.BUFFER2,
            tmem[UR6], tmem[UR4], idesc[UR5], UP0;

UTCHMMA.WS gdesc[UR8],
            gdesc[UR10].B_REUSE.B_KEEP.BUFFER2,
            tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

第一条把 B 装入 B2 并保留；第二条复用 B2 中的值，并继续保留给后续指令。
完整函数级上下文见[综合报告的附录 A.3](../tcgen05_mma_PTX到SASS映射规则报告.md)。

## 适用范围和前置条件

- A collector 属于普通 MMA；B collector 属于 WS MMA。
- `use` 和 `lastuse` 不是孤立动作，前面必须有匹配的 `fill`。
- `discard` 可以显式写出，也可以使用缺省拼写；两者是不同源码写法，但规范化
  后属于同一语义。
- collector modifier 位于操作数上。只比较主助记符会漏掉这类变化。

## 是否改变外围 SASS

collector 的完整选择关系全部位于核心 MMA 操作数上：

```text
a::discard  → A 无 modifier
a::fill     → .A_KEEP
a::use      → .A_REUSE.A_KEEP
a::lastuse  → .A_REUSE

bN::discard → [无 KEEP/REUSE] + [BUFFERn]
bN::fill    → .B_KEEP + [BUFFERn]
bN::use     → .B_REUSE.B_KEEP + [BUFFERn]
bN::lastuse → .B_REUSE + [BUFFERn]
```

其中 `[BUFFERn]` 的选择集合是：

```text
b0 → 无可见 buffer suffix
b1 → .BUFFER1
b2 → .BUFFER2
b3 → .BUFFER3
```

外围指令选择集合是空集：collector 不选择额外的 load、move、predicate、
branch 或 barrier 指令。也就是说，不能寻找某条“collector fill SASS 指令”；
fill/use/lastuse/discard 就编码在 `UTC*MMA` 的 A/B 操作数 modifier 中。

下面的数据只用于确认这种原位映射没有被不同优化级展开成其他序列。

在 PTX 目标指令条数相同的条件下，collector 不改变外围 SASS、核心 MMA 的
寄存器摆放或活跃寄存器数量。四组严格配对结果如下：

| 配对 | SASS 比较数 | 指令数变化 | 外围类型变化 | 核心活跃寄存器变化 |
|---|---:|---:|---:|---:|
| 显式 `discard` 对缺省 `discard` | 4,608 | 0 | 0 | 0 |
| `fill` 对显式 `discard` | 3,584 | 0 | 0 | 0 |
| `fill→use` 对 `fill→lastuse` | 7,680 | 0 | 0 | 0 |
| B1/B2/B3 对 B0 | 12,288 | 0 | 0 | 0 |

显式与缺省 `discard` 的核心指令文本和编码也完全相同，说明两种 PTX 拼写在
当前 lowering 中是严格等价的。

去掉 `KEEP`、`REUSE` 和 `BUFFERn` 文本后，以上配对的核心 SASS 操作数及
寄存器编号也全部相同；除显式/缺省 `discard` 外，其余 collector 状态或
buffer 改变时，核心机器编码全部不同。结论是：

```text
collector 状态
    → 原位修改 MMA 操作数 modifier 和编码
    → 不额外生成准备、控制或完成指令
```

需要区分“modifier 的影响”和“PTX 序列本来就更长”。`fill→use` 有两条 MMA，
当然会比单条 `discard` 产生更多核心指令；这不是 `use` 自动展开了外围 SASS，
而是输入 PTX 本身包含两条目标指令。所以上表只比较目标指令数相同的状态序列。

## 不能从本结果推出什么

这些结果能证明 PTX collector 状态和反汇编文本之间的稳定映射，但没有测量
collector 的容量、驻留时间、冲突代价或性能收益。它们需要实机性能实验。

## 证据

- `syntax` 和 `expanded` 集合覆盖 A collector、B0–B3，以及
  discard、fill、`fill→use`、`fill→lastuse`。
- 四个优化级的目标 occurrence 均按 PTX occurrence 归属到核心 SASS。
- 当前覆盖样本中的 `KEEP`、`REUSE` 和 `BUFFERn` 映射没有发现反例。
