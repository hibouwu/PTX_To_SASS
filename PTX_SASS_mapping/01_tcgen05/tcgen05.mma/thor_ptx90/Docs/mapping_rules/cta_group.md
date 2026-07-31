# CTA group：`.cta_group::1/2`

## 这个维度回答什么

CTA group 指一次 `tcgen05.mma` 由一个还是两个 CTA 参与。CTA 是
Cooperative Thread Array，即 CUDA thread block。

## 映射规则

| PTX | SASS |
|---|---|
| `.cta_group::1` | 主助记符不增加 CTA 数量 modifier |
| `.cta_group::2` | 主助记符增加 `.2CTA` |

例子：

```text
UTCHMMA       ← cta_group::1
UTCHMMA.2CTA  ← cta_group::2

UTCQMMA       ← cta_group::1
UTCQMMA.2CTA  ← cta_group::2
```

`.2CTA` 是直接可见的 SASS 主指令 modifier。

## PTX 与 SASS 对照

PTX：

```ptx
tcgen05.mma.cta_group::2.kind::f16.ashift
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
```

核心 SASS：

```sass
UTCHMMA.2CTA.ASHIFT
    tmem[UR7], gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], UP0 ;
```

完整函数见[综合报告的附录 A.2](../tcgen05_mma_PTX到SASS映射规则报告.md)。

## CTA group 还改变哪些 PTX 操作数

普通 MMA 的 disable-output-lane mask 数量随 CTA group 改变：

| CTA group | mask 数量 |
|---|---:|
| 1 | 4 个 32 位 mask |
| 2 | 8 个 32 位 mask |

**disable-output-lane mask** 是指定哪些输出 lane 不写结果的位掩码。
**位掩码** 是用每个二进制位表示开/关状态的整数。

mask 数量变化属于 PTX 操作数形状的一部分，不能只靠 `.2CTA` 文本替代。

## 适用限制

- 普通 `mma` 和 `mma.sp` 覆盖 CTA group 1/2。
- block-scaled 普通 MMA 覆盖 CTA group 1/2。
- `mma.ws` 和 `mma.ws.sp` 只允许 CTA group 1。

因此，不存在合法的：

```ptx
tcgen05.mma.ws.cta_group::2 ...
```

这不是“缺少测试”，而是 variant 与 CTA group 的适用性约束。

## 静态验证与运行时验证要分开

当前结果证明 `.cta_group::2` 能通过 `ptxas` 并稳定生成 `.2CTA`。它没有证明
两个 CTA 已在 Thor 上通过真实 cluster launch 正确协作。

**cluster launch** 是把多个 CTA 作为一个协作 cluster 启动的运行方式。
真实验证还需要 peer CTA、合法 TMEM 生命周期和同步协议。

## 是否改变外围 SASS

CTA group 的核心和完成协议存在两条直接映射：

```text
tcgen05.mma.cta_group::1
    → UTC*MMA

tcgen05.mma.cta_group::2
    → UTC*MMA.2CTA

保留下来的 completion for CTA group 1
    → UTCBAR

保留下来的 completion for CTA group 2
    → UTCBAR.2CTA
```

其中 `UTC*MMA` 代表 `UTCHMMA/UTCQMMA/UTCIMMA/UTCOMMA` 中由 kind 选中的
家族。

group 2 还把 disable-output-lane mask 从 4 个扩展到 8 个。根据 mask 如何
产生，外围 SASS 从以下集合中选择：

| PTX/上下文作用 | 可能选择的 SASS | 作用 |
|---|---|---|
| 常量或普通寄存器 mask | `MOV`、`UMOV` | 形成每个 mask word |
| GPR mask 送入 uniform operand | `R2UR` | GPR 到 uniform register 搬运 |
| mask 逻辑合成 | `LOP3.LUT` | 组合位掩码 |
| completion | `UTCBAR` 或 `UTCBAR.2CTA` | 选择单 CTA/双 CTA 完成协议 |
| 调度填充 | `NOP` | 解决调度间隔，不承载新的 PTX 语义 |

所以真正的 lowering 关系是：

```text
.cta_group::2
    → 核心 MMA 增加 .2CTA
    → completion 的 UTCBAR 选择 .2CTA 版本
    → 如果额外 4 个 mask 未被常量折叠，则选择更多 MOV/R2UR/UMOV
```

下面的统计说明这些候选指令在哪些优化级被实际保留下来。

会，但不是每个上下文都会改变。把 group 2 与同一合法设计的 group 1 配对后，
得到 2,432 个源码/上下文配对，即 O0–O3 共 9,728 次比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 1,048/9,728 |
| 外围指令类型或排列 | 2,256/9,728 |
| 核心位置活跃寄存器 | 1,144/9,728 |
| 核心 MMA 编码 | 9,728/9,728 |

所以 `.cta_group::2` 不只是给核心 MMA 增加 `.2CTA`：

- 普通 MMA 的 mask 从 4 个增加到 8 个，某些上下文因此增加 `MOV`、`R2UR`
  或 `UMOV` 等准备指令；
- completion 上下文中的 `UTCBAR` 会相应变为 `UTCBAR.2CTA`；
- O0 最容易保留额外准备序列：2,432 次 O0 比较中有 832 次指令数变化；
- O1、O2、O3 各只有 72/2,432 次指令数变化，说明多数常量 mask 准备会被优化。

变化不是固定增加一条指令。观察到的 group 2 指令数增量为 8、16、24、32 或
40 条，取决于 mask、producer 和 completion 上下文。没有观察到 group 2
比配对的 group 1 指令更少。

## 证据

- 52,736 条目标 occurrence 中，`.2CTA` 是否出现与 CTA group 完全一致。
- 当前样本反例为 0。
- 完整 TS + 2CTA + ASHIFT 例子位于综合报告附录 A.2。
