# 分块缩放（block scaling）：缩放因子如何进入编译降级

## 先说结论

分块缩放不总是产生一个同名的 SASS 修饰符。当前样本中的可见结果是：

| PTX 规范语义 | 可见 SASS 结果 |
|---|---|
| `scale_vec::1X` | `UTCQMMA` 家族 |
| `scale_vec::2X` | `UTCOMMA` 家族，无独立 `.2X` |
| `scale_vec::4X` | `UTCOMMA.4X` |
| `block16` 规范别名 | `UTCOMMA.4X` |
| `block32` 规范别名 | `UTCOMMA`，无独立 `.BLOCK32` |

看到"没有同名后缀"不能推断缩放信息被丢弃。信息可能由操作码家族、操作数、指令描述符（instruction descriptor，`idesc`）或机器编码共同表达。

## 专有名词

- 分块缩放（block scaling）：一个数据块共享一个或一组缩放因子，用于表示低精度矩阵数据。
- 缩放因子（scale factor）：把低精度编码恢复到目标数值范围所需的乘法因子。
- 缩放向量（scale vector）：描述缩放因子沿矩阵数据如何成组应用。
- 指令描述符（`idesc`）：描述 MMA 形状、数据类型和布局等信息的指令描述值。
- 规范别名：源码拼写不同，但在特定 kind、形状或 K 值条件下表示同一规范语义的写法。

## PTX 操作数也会变化

分块缩放形态不只是给主指令增加限定符，还会增加缩放相关操作数：

```ptx
tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.scale_vec::4X
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem],
    %enable;
```

`%scale_a_tmem` 和 `%scale_b_tmem` 是 A、B 的缩放因子地址，不是矩阵数据本身。具体参数顺序应以生成清单中该 semantic form 的 PTX 为准。

`scale_vec::4X` 的核心 SASS 助记符可见 `.4X`：

```sass
UTCOMMA.4X ...
```

而 `scale_vec::2X` 没有 `.2X` 文本：

```sass
UTCOMMA ...
```

分析分块缩放时必须同时看完整操作数和编码，不能只看助记符字符串。

## kind 与 scale vector 是联合规则

scale vector 不是脱离 `kind` 独立选择操作码：

- `mxf8f6f4` 的已覆盖规范形态进入 `UTCQMMA`。
- `mxf4` 和 `mxf4nvf4` 的已覆盖规范形态进入 `UTCOMMA`。
- `.4X` 只在相应的 `UTCOMMA` 规范形态中可见。

这里的规则应读作"在已覆盖合法 kind 和 scale-vector 组合中"，不能写成任意 `scale_vec::1X` 都无条件对应 `UTCQMMA`。

## 与 `.ashift` 的边界

分块缩放 MMA 不能再组合 `.ashift`。阴性探针有意构造该组合，`ptxas` 以非法修饰符拒绝。两者不是两个可以自由叠加的独立后缀。

## 别名为什么不能一律合并

`.block16`、`.block32` 与 `scale_vec` 写法的等价性可能依赖 kind 和 `idesc.K`。当 K 值尚未冻结时，生成器保留它们为不同源码变体（source variant），不会只因为反汇编助记符相似就强行合并。

## 分块缩放是否改变外围 SASS

要把"启用分块缩放"和"已经启用后选择哪种 scale vector"分开回答。

### 启用分块缩放：会改变外围编译降级

启用分块缩放的核心映射是增加 scale-factor 操作数，不一定更换主操作码：

```text
f8f6f4
    → UTCQMMA ..., idesc, enable

mxf8f6f4.block_scale
    → UTCQMMA ..., idesc, tmem[scale-factor], enable
```

对应 PTX 和 O3 SASS：

```ptx
// 非分块缩放：THOR_MMA_000081
tcgen05.mma.cta_group::1.kind::f8f6f4
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

// 分块缩放：THOR_MMA_001665
tcgen05.mma.cta_group::1.kind::mxf8f6f4.block_scale
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;
```

```sass
// 非分块缩放
UTCQMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// 分块缩放
UTCQMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR12], UP0;
```

A/B scale address 的产生方式决定外围选择：

| scale-factor 地址来源 | 主要 SASS 选择 |
|---|---|
| 直接统一参数 | `LDCU.64`，一次取得两个 32 位 scale address |
| derived producer | `LDC` + `IADD3` |
| 需要 GPR/UGPR 转换 | `MOV`、`R2UR` |
| guard/producer 类别随寄存器重新分配 | `ISETP`/`BRA` 或 `UISETP`/`PLOP3` |
| 调度调整 | `NOP`、`UMOV` |

O3 中，非分块缩放的装载：

```sass
LDCU.64  UR8,  c[0x0][0x388];
LDCU.64  UR10, c[0x0][0x390];
UTCQMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

启用分块缩放后：

```sass
LDCU.64  UR8,  c[0x0][0x388];
LDCU.64  UR10, c[0x0][0x390];
LDCU.64  UR12, c[0x0][0x3a0];
UTCQMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR12], UP0;
```

两条相邻的 32 位 scale address 被一次 `LDCU.64` 装入 `UR12:UR13`，核心 MMA 再通过 `tmem[UR12]` 使用这组 scale-factor 地址。

同一个 kind 不能同时拥有分块缩放和非分块缩放合法形态，因此无法做完全同 kind 的单因素配对。最接近的合法对照是 `mxf8f6f4 + scale_vec::1X` 与 `f8f6f4`。

320 个源码/上下文配对形成 1,280 次 SASS 比较：

| 检查项 | 发生变化 |
|---|---|
| 完整函数 SASS 指令数 | 452/1,280 |
| 外围指令类型或排列 | 1,280/1,280 |
| 核心操作数与寄存器摆放 | 1,280/1,280 |
| 核心位置活跃寄存器 | 1,280/1,280 |
| 核心 MMA 编码 | 1,280/1,280 |

原因不是 `.block_scale` 文字本身，而是分块缩放新增了 A/B scale-factor 地址。它们需要额外装载、占用寄存器，并进入核心 MMA 的操作数布局。启用分块缩放是一次操作数契约变化，会波及上下文 SASS。

### 在分块缩放家族内选择 `2X`/`4X`：只改核心 MMA

这个层级不再选择新的外围指令：

```text
scale_vec::2X
    → UTCOMMA ...

scale_vec::4X
    → UTCOMMA.4X ...

外围 load/move/control 集合
    → 保持相同
```

`scale_vec::4X` 与同 kind 的 `scale_vec::2X` 有 320 个配对，即 1,280 次 SASS 比较。全部结果都是：完整函数指令数相同，外围指令类型和排列相同，核心寄存器编号及活跃数量相同，只增加可见 `.4X` 并改变核心编码。

在 O3 `runtime_zero` 中，筛出 40 个独立 witness 组；等价拼写和重复实例展开为 352 个具体寄存器相同、移除 `.4X` 后整条核心操作相同的非 4X→4X 候选 pair，全部得到固定 XOR：word 0=`0x4000000000000000`，word 1=`0x0000000000000000`，且方向是清除 word 0 的该位。因此当前工具链的 `.4X` 已能归纳到 word 0 的单比特，而 `.2X`/`block32` 等没有同名文本的模式仍需结合 `idesc` 和多对一逆映射分析。完整计数见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)，descriptor 边界见 [`descriptor_and_encoding.md`](descriptor_and_encoding.md)。

### 规范别名：当前配对生成完全相同的 SASS

当前描述符条件下的可见选择关系为：

```text
block16  ↔ scale_vec::4X → UTCOMMA.4X
block32  ↔ scale_vec::2X → UTCOMMA

mxf8f6f4 的 omitted / block32 / scale_vec::1X
    → UTCQMMA
```

在可形成合法配对的样本中（`block16` 与对应 `scale_vec::4X`、`block32` 与对应 `scale_vec::2X` 等），生成的核心指令文本、寄存器活跃数量和编码均相同。这个结果只说明当前描述符条件下的编译降级等价。别名是否能合并仍要服从 kind 和 `idesc.K` 条件。

## 跨变体与 CTA group 的组合见证

分块缩放与合法的 CTA group、来源和稀疏变体组合时，核心规则仍按字段叠加：

```sass
// THOR_MMA_003145：mma + TS + group 2 + mxf4nvf4 + 4X
UTCOMMA.2CTA.4X
    tmem[UR7], gdesc[UR8],
    tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR10], UP0;

// THOR_MMA_004745：mma.sp + TS + group 2 + mxf4nvf4 + 4X
UTCOMMA.2CTA.4X
    tmem[UR5], gdesc[UR8],
    tmem[UR4], tmem[UR10], idesc[UR11], tmem[UR12], UP0;
```

两条都保留 `.2CTA.4X` 和 scale-factor `tmem[...]` 操作数。稀疏版本没有同名 `.SP`，metadata 通过寄存器角色和编码表达。分块缩放形态没有普通 MMA 的输出禁用 lane 掩码契约，group 1→2 不需要额外扩展 4 个 mask。

## 代表性覆盖口径

| 主要机制 | 覆盖位置 |
|---|---|
| 启用分块缩放增加 scale-factor 操作数 | O0/O3 与 1,280 次配对 |
| `mxf8f6f4 → UTCQMMA` | 1X 对照 |
| `mxf4`/`mxf4nvf4 → UTCOMMA` | 2X/4X 对照 |
| 2X 无后缀、4X 选择 `.4X` | 家族内严格配对 |
| block16/block32/omitted 规范别名 | 别名小节 |
| SS/TS 的 scale/address producer | O0/O3 与 operand-source 交叉 |
| CTA group 1/2 和稀疏组合 | 跨组合见证 |
| 与 `.ashift` 不兼容 | 阴性探针 |
| 描述符条件与运行时边界 | 别名和证据限制 |

当前清单中的主要静态机制均已有正向、配对或阴性证据。由于 descriptor 位型不是封闭枚举集合，本文不再给出没有严格分母的百分比；未覆盖的是所有 `idesc.K` 位型下的别名等价性和实机数值结果。

## 证据和限制

- `syntax` 与 `expanded` 集合覆盖合法的 `scale_vec::1X`/`2X`/`4X` 和 `.block16`/`.block32` 组合。
- 映射结论来自四优化级的 SASS 归属配对和规范化 semantic form。
- 本实验尚未冻结所有描述符位型，也没有做实机数值验证。可以报告可见编译降级规律，不能声称已经解释每个编码位的含义。
