# block scaling：缩放因子如何进入 lowering

## 先说结论

block scaling 不总是产生一个同名的 SASS modifier。当前样本中的可见结果是：

| PTX 规范语义 | 可见 SASS 结果 |
|---|---|
| `scale_vec::1X` | `UTCQMMA` 家族 |
| `scale_vec::2X` | `UTCOMMA` 家族，无独立 `.2X` |
| `scale_vec::4X` | `UTCOMMA.4X` |
| `block16` 规范别名 | `UTCOMMA.4X` |
| `block32` 规范别名 | `UTCOMMA`，无独立 `.BLOCK32` |

因此，看到“没有同名后缀”不能推断缩放信息被丢弃。信息可能由 opcode 家族、操作数、instruction descriptor 或机器编码共同表达。

## 专有名词

- **block scaling（分块缩放）**：一个数据块共享一个或一组缩放因子，用于表示低精度矩阵数据。
- **scale factor（缩放因子）**：把低精度编码恢复到目标数值范围所需的乘法因子。
- **scale vector（缩放向量）**：描述缩放因子沿矩阵数据如何成组应用。
- **instruction descriptor，`idesc`**：描述 MMA 形状、数据类型和布局等信息的指令描述值。
- **规范别名**：源码拼写不同，但在特定 kind、形状或 K 值条件下表示同一规范语义的写法。

## PTX 操作数也会变化

block-scaled 形态不只是给主指令增加 qualifier，还会增加缩放相关操作数：

```ptx
tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.scale_vec::4X
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem],
    %enable;
```

`%scale_a_tmem` 和 `%scale_b_tmem` 是 A、B 的缩放因子地址，不是矩阵数据本身。具体参数顺序应以生成 manifest 中该 semantic form 的 PTX 为准；上例用于说明 lowering 中新增的是哪一类信息。

`scale_vec::4X` 的核心 SASS 助记符可见 `.4X`：

```sass
UTCOMMA.4X ...
```

而 `scale_vec::2X` 没有 `.2X` 文本：

```sass
UTCOMMA ...
```

所以分析 block scaling 时必须同时看完整操作数和编码，不能只看助记符字符串。

## kind 与 scale vector 是联合规则

scale vector 不是脱离 `kind` 独立选择 opcode：

- `mxf8f6f4` 的已覆盖规范形态进入 `UTCQMMA`；
- `mxf4` 和 `mxf4nvf4` 的已覆盖规范形态进入 `UTCOMMA`；
- `.4X` 只在相应的 `UTCOMMA` 规范形态中可见。

因此，这里的规则应读作“在已覆盖合法 kind/scale-vector 组合中”，不能写成任意 `scale_vec::1X` 都无条件对应 `UTCQMMA`。

## 与 `.ashift` 的边界

block-scaled MMA 不能再组合 `.ashift`。阴性探针有意构造该组合，`ptxas` 以非法 modifier 拒绝。两者不是两个可以自由叠加的独立后缀。

## 别名为什么不能一律合并

`.block16`、`.block32` 与 `scale_vec` 写法的等价性可能依赖 kind 和 `idesc.K`。当 K 值尚未冻结时，生成器保留它们为不同 source variant，不会只因为反汇编助记符相似就强行合并。

**source variant** 指表达同一或相近语义的具体 PTX 源码写法。

## 是否改变外围 SASS

要把“启用 block scaling”和“已经启用后选择哪种 scale vector”分开回答。

### 启用 block scaling：会改变外围 lowering

启用 block scaling 的核心映射是增加 scale-factor 操作数，而不一定更换主 opcode：

```text
f8f6f4
    → UTCQMMA ..., idesc, enable

mxf8f6f4.block_scale
    → UTCQMMA ..., idesc, tmem[scale-factor], enable
```

对应 PTX 是：

```ptx
// 非 block-scaled：THOR_MMA_000081
tcgen05.mma.cta_group::1.kind::f8f6f4
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;

// block-scaled：THOR_MMA_001665
tcgen05.mma.cta_group::1.kind::mxf8f6f4.block_scale
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;
```

实际 O3 例子：

```sass
// 非 block-scaled
UTCQMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;

// block-scaled
UTCQMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR12], UP0;
```

A/B scale address 的产生方式决定外围选择：

| scale-factor 地址来源 | 主要 SASS 选择 |
|---|---|
| 直接 uniform 参数 | `LDCU.64`，一次取得两个 32 位 scale address |
| derived producer | `LDC` + `IADD3` |
| 需要 GPR/UGPR 转换 | `MOV`、`R2UR` |
| guard/producer 类别随寄存器重新分配 | `ISETP/BRA` 或 `UISETP/PLOP3` |
| 调度调整 | `NOP`、`UMOV` |

O0 中，非 block-scaled `THOR_MMA_000081` 没有 scale address 的生产路径。以下是选指相关片段，省略部分同值 `MOV` 和无关 mask 准备：

```ptx
tcgen05.mma.cta_group::1.kind::f8f6f4
    [%d_tmem], %desc_a, %desc_b, %idesc,
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
UTCQMMA  gdesc[UR4], gdesc[UR6],
          tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;
```

block-scaled `THOR_MMA_001665` 多出两个 32 位 scale address load、两条 `IADD3`，最后把结果送入 `tmem[UR10]`：

```ptx
tcgen05.mma.cta_group::1.kind::mxf8f6f4.block_scale
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;
```

```sass
MOV      R3, 0x20;
LDC      R3, c[0x0][R3+0x380];
MOV      R4, R3;
MOV      R3, 0x24;
LDC      R3, c[0x0][R3+0x380];
MOV      R5, R3;
IADD3    R9,  PT, PT, R4, RZ, RZ;
IADD3    R10, PT, PT, R5, RZ, RZ;
R2UR     UR10, R9;
R2UR     UR11, R10;
UTCQMMA  gdesc[UR4], gdesc[UR6],
          tmem[UR12], tmem[UR8], idesc[UR9], tmem[UR10], UP0;
```

到 O3，以上地址形成被合并为 uniform load。非 block-scaled：

```ptx
tcgen05.mma.cta_group::1.kind::f8f6f4
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

```sass
LDCU.64  UR8,  c[0x0][0x388];
LDCU.64  UR10, c[0x0][0x390];
UTCQMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

启用 block scaling：

```ptx
tcgen05.mma.cta_group::1.kind::mxf8f6f4.block_scale
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;
```

```sass
LDCU.64  UR8,  c[0x0][0x388];
LDCU.64  UR10, c[0x0][0x390];
LDCU.64  UR12, c[0x0][0x3a0];
UTCQMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR12], UP0;
```

这里两条相邻的 32 位 scale address 被一次 `LDCU.64` 装入 `UR12:UR13`，核心 MMA 再通过 `tmem[UR12]` 使用这组 scale-factor 地址。O0 展示地址如何产生，O3 展示最终合并后的选指。

同一个 kind 不能同时拥有 block-scaled 和非 block-scaled 合法形态，因此无法做完全同 kind 的单因素配对。最接近的合法对照是 `mxf8f6f4 + scale_vec::1X` 与 `f8f6f4`，其余 variant、来源、collector、上下文和优化级保持一致。

320 个源码/上下文配对形成 1,280 次 SASS 比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 452/1,280 |
| 外围指令类型或排列 | 1,280/1,280 |
| 核心操作数与寄存器摆放 | 1,280/1,280 |
| 核心位置活跃寄存器 | 1,280/1,280 |
| 核心 MMA 编码 | 1,280/1,280 |

原因不是 `.block_scale` 文字本身，而是 block scaling 新增 A/B scale-factor 地址。它们需要额外装载、占用寄存器，并进入核心 MMA 的操作数布局。因此启用 block scaling 是一次操作数契约变化，会波及上下文 SASS。

### 在 block-scaled 家族内选择 `2X/4X`：只改核心 MMA

这个层级不再选择新的外围指令：

```text
scale_vec::2X
    → UTCOMMA ...

scale_vec::4X
    → UTCOMMA.4X ...

外围 load/move/control 集合
    → 保持相同
```

`scale_vec::4X` 与同 kind 的 `scale_vec::2X` 有 320 个配对，即 1,280 次 SASS 比较。全部结果都是：

```ptx
tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.scale_vec::2X
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;

tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.scale_vec::4X
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem], %enable;
```

对应的真实核心 SASS 是：

```sass
// scale_vec::2X，THOR_MMA_001905
// O0
UTCOMMA gdesc[UR4], gdesc[UR6],
         tmem[UR12], tmem[UR8], idesc[UR9], tmem[UR10], UP0;
// O3
UTCOMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR12], UP0;

// scale_vec::4X，THOR_MMA_001945
// O0
UTCOMMA.4X gdesc[UR4], gdesc[UR6],
            tmem[UR12], tmem[UR8], idesc[UR9], tmem[UR10], UP0;
// O3
UTCOMMA.4X gdesc[UR8], gdesc[UR10],
            tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR12], UP0;
```

这里 O0 与 O3 的寄存器编号会整体重排，但同一优化级内 `2X/4X` 的操作数布局相同；指令选择只从 `UTCOMMA` 变为 `UTCOMMA.4X`，外围指令保持相同。

- 完整函数指令数相同；
- 外围指令类型和排列相同；
- 核心寄存器编号及活跃数量相同；
- 只增加可见 `.4X` 并改变核心编码。

### 规范别名：当前配对生成完全相同的 SASS

当前 descriptor 条件下的可见选择关系为：

```text
block16  ↔ scale_vec::4X → UTCOMMA.4X
block32  ↔ scale_vec::2X → UTCOMMA

mxf8f6f4 的 omitted / block32 / scale_vec::1X
    → UTCQMMA
```

在可形成合法配对的样本中：

- `block16` 与对应 `scale_vec::4X`；
- `block32` 与对应 `scale_vec::2X`；
- `mxf8f6f4` 的 omitted、`block32` 与 `scale_vec::1X`；
- `mxf4` 的 omitted 与 `block32`

生成的核心指令文本、寄存器活跃数量和编码均相同。这个结果只说明当前 descriptor 条件下的 lowering 等价；别名是否能合并仍要服从 kind 和 `idesc.K` 条件。

## 跨 variant 与 CTA group 的组合见证

前面的展开示例集中在 group 1 的普通 MMA。block scaling 与合法的 CTA group、来源和 sparse variant 组合时，核心规则仍按字段叠加：

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

两条都保留 `.2CTA.4X` 和 scale-factor `tmem[...]` 操作数；sparse 版本没有同名 `.SP`，metadata 通过寄存器角色和编码表达。它们还说明 block-scaled 形态没有普通 MMA 的 disable-output-lane mask 契约，group 1→2 不需要额外扩展 4 个 mask。

## 代表性覆盖口径

| 主要机制 | 覆盖位置 |
|---|---|
| 启用 block scaling 增加 scale-factor 操作数 | O0/O3 与 1,280 次配对 |
| `mxf8f6f4 → UTCQMMA` | 1X 对照 |
| `mxf4/mxf4nvf4 → UTCOMMA` | 2X/4X 对照 |
| 2X 无后缀、4X 选择 `.4X` | 家族内严格配对 |
| block16/block32/omitted 规范别名 | 别名小节 |
| SS/TS 的 scale/address producer | O0/O3 与 operand-source 交叉 |
| CTA group 1/2 和 sparse 组合 | 跨组合见证 |
| 与 `.ashift` 不兼容 | 阴性探针 |
| descriptor 条件与运行时边界 | 别名和证据限制 |

主要静态机制均已有正向、配对或阴性证据，保守记为 **至少 95% 的主要变化机制**。未覆盖的是所有 `idesc.K` 位型下的别名等价性和实机数值结果。

## 证据和限制

- `syntax` 与 `expanded` 集合覆盖合法的 `scale_vec::1X/2X/4X`、 `.block16/.block32` 组合。
- 映射结论来自四优化级的 SASS attribution 和规范化 semantic form。
- 本实验尚未冻结所有 descriptor 位型，也没有做实机数值验证。因此可以报告可见 lowering 规律，不能声称已经解释每个编码位的含义。
