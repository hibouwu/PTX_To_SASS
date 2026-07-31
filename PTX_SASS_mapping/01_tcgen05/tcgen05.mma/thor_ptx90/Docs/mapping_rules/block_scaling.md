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

因此，看到“没有同名后缀”不能推断缩放信息被丢弃。信息可能由 opcode
家族、操作数、instruction descriptor 或机器编码共同表达。

## 专有名词

- **block scaling（分块缩放）**：一个数据块共享一个或一组缩放因子，用于表示
  低精度矩阵数据。
- **scale factor（缩放因子）**：把低精度编码恢复到目标数值范围所需的乘法因子。
- **scale vector（缩放向量）**：描述缩放因子沿矩阵数据如何成组应用。
- **instruction descriptor，`idesc`**：描述 MMA 形状、数据类型和布局等信息的
  指令描述值。
- **规范别名**：源码拼写不同，但在特定 kind、形状或 K 值条件下表示同一规范
  语义的写法。

## PTX 操作数也会变化

block-scaled 形态不只是给主指令增加 qualifier，还会增加缩放相关操作数：

```ptx
tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.scale_vec::4X
    [%d_tmem], %desc_a, %desc_b, %idesc,
    [%scale_a_tmem], [%scale_b_tmem],
    %enable;
```

`%scale_a_tmem` 和 `%scale_b_tmem` 是 A、B 的缩放因子地址，不是矩阵数据
本身。具体参数顺序应以生成 manifest 中该 semantic form 的 PTX 为准；上例
用于说明 lowering 中新增的是哪一类信息。

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

因此，这里的规则应读作“在已覆盖合法 kind/scale-vector 组合中”，不能写成
任意 `scale_vec::1X` 都无条件对应 `UTCQMMA`。

## 与 `.ashift` 的边界

block-scaled MMA 不能再组合 `.ashift`。阴性探针有意构造该组合，`ptxas`
以非法 modifier 拒绝。两者不是两个可以自由叠加的独立后缀。

## 别名为什么不能一律合并

`.block16`、`.block32` 与 `scale_vec` 写法的等价性可能依赖 kind 和
`idesc.K`。当 K 值尚未冻结时，生成器保留它们为不同 source variant，
不会只因为反汇编助记符相似就强行合并。

**source variant** 指表达同一或相近语义的具体 PTX 源码写法。

## 是否改变外围 SASS

要把“启用 block scaling”和“已经启用后选择哪种 scale vector”分开回答。

### 启用 block scaling：会改变外围 lowering

启用 block scaling 的核心映射是增加 scale-factor 操作数，而不一定更换主
opcode：

```text
f8f6f4
    → UTCQMMA ..., idesc, enable

mxf8f6f4.block_scale
    → UTCQMMA ..., idesc, tmem[scale-factor], enable
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

真实 O3 对照中，非 block-scaled `THOR_MMA_000081` 为：

```sass
LDCU.64  UR8,  c[0x0][0x388];
LDCU.64  UR10, c[0x0][0x390];
UTCQMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

启用 block scaling 的 `THOR_MMA_001665` 为：

```sass
LDCU.64  UR8,  c[0x0][0x388];
LDCU.64  UR10, c[0x0][0x390];
LDCU.64  UR12, c[0x0][0x3a0];
UTCQMMA  gdesc[UR8], gdesc[UR10],
          tmem[UR6], tmem[UR4], idesc[UR5], tmem[UR12], UP0;
```

这里两条相邻的 32 位 scale address 被一次 `LDCU.64` 装入 `UR12:UR13`，
核心 MMA 再通过 `tmem[UR12]` 使用这组 scale-factor 地址。

同一个 kind 不能同时拥有 block-scaled 和非 block-scaled 合法形态，因此无法
做完全同 kind 的单因素配对。最接近的合法对照是
`mxf8f6f4 + scale_vec::1X` 与 `f8f6f4`，其余 variant、来源、collector、
上下文和优化级保持一致。

320 个源码/上下文配对形成 1,280 次 SASS 比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 452/1,280 |
| 外围指令类型或排列 | 1,280/1,280 |
| 核心操作数与寄存器摆放 | 1,280/1,280 |
| 核心位置活跃寄存器 | 1,280/1,280 |
| 核心 MMA 编码 | 1,280/1,280 |

原因不是 `.block_scale` 文字本身，而是 block scaling 新增 A/B scale-factor
地址。它们需要额外装载、占用寄存器，并进入核心 MMA 的操作数布局。因此启用
block scaling 是一次操作数契约变化，会波及上下文 SASS。

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

`scale_vec::4X` 与同 kind 的 `scale_vec::2X` 有 320 个配对，即 1,280 次
SASS 比较。全部结果都是：

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

生成的核心指令文本、寄存器活跃数量和编码均相同。这个结果只说明当前 descriptor
条件下的 lowering 等价；别名是否能合并仍要服从 kind 和 `idesc.K` 条件。

## 证据和限制

- `syntax` 与 `expanded` 集合覆盖合法的 `scale_vec::1X/2X/4X`、
  `.block16/.block32` 组合。
- 映射结论来自四优化级的 SASS attribution 和规范化 semantic form。
- 本实验尚未冻结所有 descriptor 位型，也没有做实机数值验证。因此可以报告
  可见 lowering 规律，不能声称已经解释每个编码位的含义。
