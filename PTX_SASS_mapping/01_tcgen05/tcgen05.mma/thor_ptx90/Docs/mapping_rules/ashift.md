# `.ashift`：A 操作数行移位

## 先说结论

合法的 PTX `.ashift` 会直接变成 SASS `.ASHIFT`：

```text
PTX:  tcgen05.mma...ashift
SASS: UTC*MMA...ASHIFT
```

但这不是一个可随意附加的通用 modifier。当前 Thor/PTX 9.0 组合中，它要求 A 来自 TMEM，并且不能与 block scaling 组合。

## `.ashift` 是什么

`.ashift` 表示对 A 操作数的行位置采用硬件支持的移位解释。这里的 A 是矩阵乘加 `D = A × B + D` 中的左输入矩阵；**TMEM（Tensor Memory）**是 Tensor Core 使用的专用存储空间。

`.ashift` 改变的是 MMA 如何解释 A 的位置，不是额外插入一条通用整数移位指令。因此在 SASS 中表现为核心 MMA 的 `.ASHIFT` modifier。

## 直接映射

一个 CTA group 2 的例子：

```ptx
tcgen05.mma.cta_group::2.kind::f16.ashift
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7},
    %enable;
```

核心 SASS：

```sass
// THOR_MMA_000078，O0
UTCHMMA.2CTA.ASHIFT
    tmem[UR17], gdesc[UR4],
    tmem[UR16], tmem[UR6], idesc[UR7], UR8, UP0;

// THOR_MMA_000078，O3
UTCHMMA.2CTA.ASHIFT
    tmem[UR7], gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

O0 保留了尚未折叠的 mask/辅助操作数 `UR8`，O3 将其折叠并重新编号；两级都直接选择 `.ASHIFT`，没有额外 shift 指令。

这里可以分别读出：

- `UTCHMMA`：由 `kind::f16` 决定的 opcode 家族；
- `.2CTA`：由 `.cta_group::2` 决定；
- `.ASHIFT`：由 PTX `.ashift` 决定；
- 第一个输入为 `tmem[...]`：A 来自 TMEM。

完整函数级 PTX 和 SASS 见[综合报告的附录 A.2](../tcgen05_mma_PTX到SASS映射规则报告.md)。

## 适用条件

在当前正向矩阵中，合法 `.ashift` 形态满足：

- 使用普通 `mma` 或 `mma.sp`，不是 WS variant；
- A 使用 TMEM address，即 TS 来源模式；
- 不是 block-scaled MMA；
- 使用该形态允许的矩阵尺寸和 descriptor。

其中“TS”表示 A 来自 TMEM、B 来自 SMEM descriptor。来源模式详见 [`operand_source.md`](operand_source.md)。

## 两个已验证的非法组合

| 非法构造 | 结果 | 说明 |
|---|---|---|
| SMEM descriptor A + `.ashift` | `ptxas` 拒绝 | `.ashift` 要求 TMEM A |
| block scaling + `.ashift` | `ptxas` 拒绝 | 两者不能自由叠加 |

这些是**阴性探针**：实验者故意构造非法 PTX，以确认工具链真的拒绝越界组合。阴性探针的价值是确认边界，不是证明硬件运行语义。

## 与 collector 的关系

`.ashift` 与 collector 状态也不能只靠字符串机械拼接。生成矩阵只保留合法的状态序列，例如先 `fill`，再在匹配的最终使用中组合相应状态。判断某条写法是否合法时，应同时查看 variant、A 来源和 collector 前序状态。

## 是否改变外围 SASS

`.ashift` 的选择集合只有一个元素：

```text
UTC*MMA
    → UTC*MMA.ASHIFT

外围 load/move/shift/control 指令
    → 不新增
```

尤其不会选择 `SHF`、`SHR`、`SHL` 或其他独立整数移位指令。A 的行移位模式直接编码在 MMA 中，而不是先用一条 SASS 指令改写 A 地址。

下面的数据用于确认 `.ASHIFT` 在不同上下文和优化级都没有被展开。

不会。将全部 384 个 `.ashift` 源码/上下文用例与对应的非 `.ashift` 用例配对，并比较 O0–O3，共得到 1,536 次 SASS 比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 0/1,536 |
| 外围指令类型或排列 | 0/1,536 |
| 去掉 `.ASHIFT` 后的核心操作数和寄存器编号 | 0/1,536 |
| 核心位置活跃寄存器 | 0/1,536 |
| 核心 MMA 编码 | 1,536/1,536 |

所以 `.ashift` 是一个原位编码到 MMA 的 modifier：

```ptx
tcgen05.mma.cta_group::2.kind::f16
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;

tcgen05.mma.cta_group::2.kind::f16.ashift
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7}, %enable;
```

```sass
UTCHMMA.2CTA ...
→ UTCHMMA.2CTA.ASHIFT ...
```

它不会额外生成移位指令，也不会改变 `LDCU`、`ELECT`、`PLOP3`、`BRA` 等外围序列。当前样本中连核心寄存器编号都保持不变，只有 modifier 和机器编码发生变化。

## 跨形态代表例子

单个 f16 例子不足以说明 `.ASHIFT` 与其他合法维度的组合。下面列出 expanded 结果中的真实 O3 核心指令：

| case | PTX 关键形态 | O3 核心 SASS |
|---|---|---|
| `THOR_MMA_000201` | `mma + f16 + group 1` | `UTCHMMA.ASHIFT tmem[...]` |
| `THOR_MMA_000329` | `mma + f8f6f4 + group 1` | `UTCQMMA.ASHIFT tmem[...]` |
| `THOR_MMA_000393` | `mma + i8 + group 1` | `UTCIMMA.ASHIFT tmem[...]` |
| `THOR_MMA_001225` | `mma.sp + i8 + group 1` | `UTCIMMA.ASHIFT tmem[...]` |
| `THOR_MMA_001641` | `mma.sp + i8 + group 2` | `UTCIMMA.2CTA.ASHIFT tmem[...]` |

collector 也能与合法 `.ashift` 状态组合。`THOR_MMA_000633` 的第二条目标指令在 O3 为：

```sass
UTCHMMA.2CTA.ASHIFT
    tmem[UR7].A_REUSE, gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

这里 `.2CTA`、`.ASHIFT` 和 `.A_REUSE` 分别属于 CTA group、A 行移位和 collector 三个正交字段。`UTCOMMA` 没列入合法 `.ashift` 家族，是因为当前 `UTCOMMA` 形态属于 block scaling，而 block scaling 与 `.ashift` 已被阴性探针确认不兼容。

## 代表性覆盖口径

按主要静态 lowering 机制计算，本页已经覆盖：

| 主要机制 | 覆盖位置 |
|---|---|
| `.ashift → .ASHIFT` 原位编码 | 直接映射与 1,536 次配对 |
| `UTCHMMA/UTCQMMA/UTCIMMA` 三个合法 opcode 家族 | 跨形态表 |
| CTA group 1/2 | 主例子与跨形态表 |
| `mma/mma.sp` | 跨形态表 |
| 与 A collector 的操作数字段组合 | `THOR_MMA_000633` |
| 不新增外围 shift/load/control 指令 | 外围 SASS 统计 |
| TS-only、非 block-scale 的合法性边界 | 两个阴性探针 |

这些机制均有正向或阴性证据；未逐条展示的主要是共享同一 `UTCHMMA` 家族的 `tf32` 和所有 collector 状态的重复实例。因此保守记为 **至少 95% 的主要变化机制**，不是 95% 的精确 semantic form。

## 证据和限制

- 正向 `syntax`/`expanded` 样本中的 `.ashift → .ASHIFT` 映射没有反例。
- 两个相关阴性探针均得到预期拒绝。
- 这里证明的是静态 lowering 和语法边界；行移位后的数值结果尚未由实机输出单独验证。
