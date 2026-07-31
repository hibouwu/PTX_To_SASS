# `.ashift`：A 操作数行移位

## 先说结论

合法的 PTX `.ashift` 会直接变成 SASS `.ASHIFT`：

```text
PTX:  tcgen05.mma...ashift
SASS: UTC*MMA...ASHIFT
```

但这不是一个可随意附加的通用 modifier。当前 Thor/PTX 9.0 组合中，它要求
A 来自 TMEM，并且不能与 block scaling 组合。

## `.ashift` 是什么

`.ashift` 表示对 A 操作数的行位置采用硬件支持的移位解释。这里的 A 是
矩阵乘加 `D = A × B + D` 中的左输入矩阵；**TMEM（Tensor Memory）**是
Tensor Core 使用的专用存储空间。

`.ashift` 改变的是 MMA 如何解释 A 的位置，不是额外插入一条通用整数移位
指令。因此在 SASS 中表现为核心 MMA 的 `.ASHIFT` modifier。

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
UTCHMMA.2CTA.ASHIFT
    tmem[UR7], gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

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

其中“TS”表示 A 来自 TMEM、B 来自 SMEM descriptor。来源模式详见
[`operand_source.md`](operand_source.md)。

## 两个已验证的非法组合

| 非法构造 | 结果 | 说明 |
|---|---|---|
| SMEM descriptor A + `.ashift` | `ptxas` 拒绝 | `.ashift` 要求 TMEM A |
| block scaling + `.ashift` | `ptxas` 拒绝 | 两者不能自由叠加 |

这些是**阴性探针**：实验者故意构造非法 PTX，以确认工具链真的拒绝越界组合。
阴性探针的价值是确认边界，不是证明硬件运行语义。

## 与 collector 的关系

`.ashift` 与 collector 状态也不能只靠字符串机械拼接。生成矩阵只保留合法的
状态序列，例如先 `fill`，再在匹配的最终使用中组合相应状态。判断某条写法
是否合法时，应同时查看 variant、A 来源和 collector 前序状态。

## 是否改变外围 SASS

`.ashift` 的选择集合只有一个元素：

```text
UTC*MMA
    → UTC*MMA.ASHIFT

外围 load/move/shift/control 指令
    → 不新增
```

尤其不会选择 `SHF`、`SHR`、`SHL` 或其他独立整数移位指令。A 的行移位模式
直接编码在 MMA 中，而不是先用一条 SASS 指令改写 A 地址。

下面的数据用于确认 `.ASHIFT` 在不同上下文和优化级都没有被展开。

不会。将全部 384 个 `.ashift` 源码/上下文用例与对应的非 `.ashift` 用例
配对，并比较 O0–O3，共得到 1,536 次 SASS 比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 0/1,536 |
| 外围指令类型或排列 | 0/1,536 |
| 去掉 `.ASHIFT` 后的核心操作数和寄存器编号 | 0/1,536 |
| 核心位置活跃寄存器 | 0/1,536 |
| 核心 MMA 编码 | 1,536/1,536 |

所以 `.ashift` 是一个原位编码到 MMA 的 modifier：

```sass
UTCHMMA.2CTA ...
→ UTCHMMA.2CTA.ASHIFT ...
```

它不会额外生成移位指令，也不会改变 `LDCU`、`ELECT`、`PLOP3`、`BRA`
等外围序列。当前样本中连核心寄存器编号都保持不变，只有 modifier 和机器编码
发生变化。

## 证据和限制

- 正向 `syntax`/`expanded` 样本中的 `.ashift → .ASHIFT` 映射没有反例。
- 两个相关阴性探针均得到预期拒绝。
- 这里证明的是静态 lowering 和语法边界；行移位后的数值结果尚未由实机输出
  单独验证。
