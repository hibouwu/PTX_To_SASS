# modifier 联合作用：怎样拼成完整 lowering

## 为什么需要这一页

单个规则条目回答“一个维度通常映射到哪里”，但 `tcgen05.mma` 的 modifier
不是一组可以任意排列组合的开关。它们会限制彼此的适用范围，有些信息还只在
操作数或机器编码中体现。

因此，完整分析应先判断组合是否合法，再按层解释 lowering。

## 推荐的阅读顺序

```text
1. kind
   选择 UTCHMMA / UTCQMMA / UTCIMMA / UTCOMMA

2. CTA group
   group 2 增加 .2CTA

3. variant
   WS 增加 .WS；SP 不产生同名 .SP

4. block scaling
   某些规范形态选择不同 opcode 家族或增加 .4X

5. ashift
   合法 TS 形态增加 .ASHIFT

6. operand source 与 collector
   决定 tmem/gdesc 和 KEEP/REUSE/BUFFERn

7. 上下文
   决定谓词、寄存器编号和核心指令前后的外围序列
```

这个顺序是分析方法，不表示 SASS 文本必须严格按同样顺序书写所有字段。

## 组合约束表

| 维度 | 可以和什么组合 | 关键限制 |
|---|---|---|
| `.cta_group::2` | 普通 MMA、合法 TS/SS | WS 固定为 group 1 |
| `.ws` | B collector、合法 kind | 使用 B collector，不使用普通 A collector |
| `.sp` | 普通或 WS variant | 没有可见同名 `.SP`，需看 metadata/编码 |
| `.ashift` | 普通 TS MMA、CTA group 1/2 | A 必须来自 TMEM；不能 block scale |
| A collector | 普通 MMA | 状态序列必须合法 |
| B collector | WS MMA | buffer 为 b0–b3；状态序列必须合法 |
| block scaling | 对应的低精度 kind | scale vector、别名和 `idesc.K` 联合解释 |

## 三个典型组合

### 1. kind + CTA group + TS + `.ashift`

```text
kind::f16 + cta_group::2 + TS + ashift
→ UTCHMMA.2CTA.ASHIFT tmem[...], gdesc[...], ...
```

这里四个维度分别决定 opcode 家族、`.2CTA`、A/B 操作数类型和 `.ASHIFT`。

### 2. WS + B2 collector use

```text
mma.ws + collector::b2::use
→ UTCHMMA.WS ... gdesc[...].B_REUSE.B_KEEP.BUFFER2 ...
```

`.WS` 位于主助记符，collector 状态位于 B 操作数。只比较助记符会遗漏
`use` 和 `fill` 的差别。

### 3. sparse + WS

```text
mma.ws.sp
→ UTC*MMA.WS ...
```

这里可见 `.WS`，但没有同名 `.SP`。稀疏语义由额外 metadata、操作数位置或
机器编码承载。因此 `.ws.sp` 不能被简单解释成字符串 `.WS.SP`。

## 哪些维度不是独立效应

### `.sp` 是隐藏效应

`.sp` 不改变为同名主 opcode modifier。必须把稀疏 metadata 和编码纳入比较，
否则会错误地得出“`.sp` 没有作用”。

### block scaling 是 kind、scale vector 和 descriptor 的联合效应

`scale_vec::2X` 与 `block32` 没有同名 SASS 后缀；`scale_vec::4X` 和某些
`block16` 形态可见 `.4X`。这些规则依赖合法 kind 和 descriptor 条件。

### collector 是状态机，不是单条无状态 modifier

`use` 和 `lastuse` 依赖先前的 `fill`。单独摘出第二条指令虽然能读出
`REUSE/KEEP`，却不足以证明整段 PTX 合法。

## 上下文与核心规则怎样相遇

外围上下文通常不改 opcode 家族，但仍能改变机器代码：

| 上下文维度 | 主要影响 |
|---|---|
| `enable-input-d` 常量 | 核心 MMA 的输入 D 谓词可折叠为 `UPT`/`!UPT` |
| PTX guard | 核心谓词或外围控制流 |
| lane 0 issuer | 发射控制、活跃寄存器和寄存器编号 |
| derived producer | O1–O3 可能优化掉生产者或重排准备序列 |
| completion | 核心 MMA 后的提交、barrier 和等待序列 |

**谓词**是控制指令是否执行或选择某种输入语义的真假条件。`UPT` 是 uniform
predicate true；`!UPT` 是其取反。

32,256 组上下文配对中，没有观察到上下文改变核心 MMA 的 opcode/modifier
规范形态；但寄存器编号、活跃集合、外围指令和编码仍会变化。详细统计见
[`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)。

## 哪些 modifier 会波及外围 SASS

下面的“外围”指去掉目标 MMA 后的参数装载、谓词、选举、分支和完成协议。
“有条件”表示只在部分上下文或优化级发生，不表示结果不稳定。

选择外围指令时，可以先判断 PTX 是否改变了操作数契约：

```text
只改变 MMA 编码模式
    collector / ashift / scale_vec 2X↔4X
    → 不选择新的外围指令

增加或替换 64 位 descriptor
    SS A / zero-column-mask
    → 直接参数：LDCU.64
    → derived producer：LDC.64 + MOV/R2UR

增加 32 位 TMEM 或 scale address
    TS A / block scaling
    → 直接参数：LDCU，两个相邻地址可合并为 LDCU.64
    → derived producer：LDC + IADD3

增加 disable-output-lane mask
    CTA group 1→2
    → MOV/UMOV + R2UR
    → 需要位逻辑时选择 LOP3.LUT

改变完成协议范围
    CTA group 1→2
    → UTCBAR → UTCBAR.2CTA
```

`NOP` 不在这个语义选择树中，因为它是编译器根据最终调度间隔插入的填充，
不是某个 PTX modifier 的语义实现指令。

| 维度 | 核心 MMA | 外围指令数/类型 | 核心寄存器/活跃数 | 最准确的心智模型 |
|---|---|---|---|---|
| 非 block kind | opcode 或 descriptor 解释变化 | 不变 | 不变 | 原位选择计算家族 |
| CTA group 2 | 增加 `.2CTA` | 有条件变化 | 有条件变化 | 核心模式加 mask/完成协议变化 |
| `.sp` | metadata/编码，不显示 `.SP` | 总会改变类型，数量有时改变 | 有条件变化 | 稀疏操作数契约 |
| `.ws` | 增加 `.WS` | 有条件变化 | 有条件变化 | collector 和操作数契约共同变化 |
| zero-column-mask descriptor | descriptor 操作数或其值 | 总会改变类型，数量有时改变 | 通常变化 | WS 可选操作数契约 |
| TS/SS | `tmem` 对 `gdesc` | 总会改变类型，数量有时改变 | 总会改变 | A 来源契约变化 |
| collector | `KEEP/REUSE/BUFFERn` | 不变 | 不变 | 原位操作数 modifier |
| 启用 block scaling | opcode 加 scale-factor 操作数 | 总会改变类型，数量有时改变 | 总会改变 | scale-factor 操作数契约 |
| `scale_vec::2X/4X` | 可见 `.4X` 或隐式编码 | 不变 | 不变 | block 家族内的原位模式 |
| `.ashift` | 增加 `.ASHIFT` | 不变 | 不变 | 原位 MMA modifier |

这里的关键分界不是“PTX 上有没有点号 modifier”，而是它是否改变操作数契约：

- 只改变核心编码字段的 modifier，通常不会生成外围指令；
- 新增、删除或改变操作数宽度/类别的 modifier，会改变参数装载和寄存器分配；
- CTA group 还会改变 mask 数量和 completion 指令，因此处在两者之间。

## 写映射规则时应使用的措辞

- 可以写：“在当前覆盖的合法样本中，`.cta_group::2 → .2CTA`，零反例。”
- 应写：“`.sp` 没有可见同名 modifier，信息进入其他字段。”
- 应写：“`scale_vec::4X → .4X` 受 kind 和规范形态约束。”
- 不应写：“所有 PTX modifier 都一对一变成同名 SASS modifier。”
- 不应写：“核心助记符相同就说明完整机器代码相同。”

## 最终检查清单

分析一条新的 lowering 时，依次确认：

1. PTX variant 和 kind 是否属于已覆盖集合；
2. CTA group 与 WS 是否兼容；
3. A/B 来源是 TS 还是 SS；
4. block scaling、`.ashift` 是否满足条件；
5. collector 是否有合法的前序状态；
6. 稀疏 metadata 和 scale-factor 操作数是否完整；
7. 核心 SASS 的 opcode、modifier 和操作数是否分别对应；
8. 差异是否其实来自 guard、issuer、producer、enable 或 completion。
