# variant：`mma`、`mma.sp`、`mma.ws`、`mma.ws.sp`

## variant 是什么

variant 是同一基础 MMA 指令的语义变体：

| variant | 含义 |
|---|---|
| `mma` | 普通矩阵乘加 |
| `mma.sp` | sparse，稀疏矩阵乘加 |
| `mma.ws` | weight-stationary，权重驻留模式 |
| `mma.ws.sp` | 权重驻留与稀疏模式同时存在 |

**稀疏** 表示矩阵中部分元素按约定不参与存储或计算；**权重驻留** 表示让
B 操作数在 collector 中保持并复用。

## `.ws` 的直接映射

| PTX variant | SASS 主助记符 |
|---|---|
| `mma` | 不增加 `.WS` |
| `mma.sp` | 不增加 `.WS` |
| `mma.ws` | 增加 `.WS` |
| `mma.ws.sp` | 增加 `.WS` |

例如：

```text
tcgen05.mma...     → UTCHMMA...
tcgen05.mma.ws...  → UTCHMMA.WS...
```

`.ws` 还把 collector 的主要对象从 A 改为 B0–B3。具体规则见
[`collector.md`](collector.md)。

## `.sp` 为什么没有 `.SP`

本实验中，`mma.sp` 和 `mma.ws.sp` 都没有生成同名 `.SP` SASS modifier：

```text
mma       → UTCHMMA
mma.sp    → UTCHMMA

mma.ws    → UTCHMMA.WS
mma.ws.sp → UTCHMMA.WS
```

这不表示稀疏语义被删除。`.sp` 增加的 metadata 会进入操作数位置和机器编码，
并影响物理寄存器分配。

**metadata** 是描述哪些稀疏元素存在的附加信息；**物理寄存器分配** 是
`ptxas` 把 PTX 虚拟寄存器安排到具体 R/UR/P/UP 编号的过程。

## 稀疏变体的寄存器证据

在 O3 的 `lane0_issuer` 上下文比较中：

- 168 组核心寄存器布局变化全部属于 `.sp` 变体；
- 这些变化都是纯重编号；
- 核心 opcode 和规范操作没有变化。

**纯重编号** 指寄存器类别和复用关系不变，只是具体编号改变，例如
`UR4 → UR7`。这说明 `.sp` 可能通过操作数与寄存器布局体现，而不需要独立助记符。

## `.ws.sp` 不能只拆成两条独立规则

分别知道：

```text
ws → .WS
sp → 无可见 .SP
```

还不足以完整解释 `ws.sp`，因为：

- `.ws` 使用 B collector；
- `.sp` 增加 metadata；
- 两者共同影响操作数位置和寄存器编号；
- `.ws` 只允许 CTA group 1。

因此 `mma.ws.sp` 应理解为一个受约束组合，而不是两个任意 modifier 的字符串相加。
组合规则见 [`interactions.md`](interactions.md)。

## 完整例子

PTX：

```ptx
tcgen05.mma.ws.cta_group::1.kind::f16.collector::b2::fill
    [%d_tmem], %desc_a, %desc_b, %idesc, %enable;
tcgen05.mma.ws.cta_group::1.kind::f16.collector::b2::use
    [%d_tmem], %desc_a, %desc_b, %idesc, %enable;
```

第二条核心 SASS：

```sass
UTCHMMA.WS
    gdesc[UR8],
    gdesc[UR10].B_REUSE.B_KEEP.BUFFER2,
    tmem[UR6], tmem[UR4], idesc[UR5], UP0 ;
```

完整 fill → use 函数见[综合报告的附录 A.3](../tcgen05_mma_PTX到SASS映射规则报告.md)。

## 是否改变外围 SASS

### `.sp`：会，而且影响不只在核心指令

`.sp` 的映射不是 `UTC*MMA.SP`，而是：

```text
mma.sp
    → 主 opcode 仍为 UTC*MMA
    → metadata TMEM 地址进入核心操作数
    → 重新选择 metadata 的装载、地址形成和寄存器组合指令
```

以同一个 SS、f16、O3 例子表示，核心指令从：

```sass
UTCHMMA gdesc[UR8], gdesc[UR10],
         tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

变成：

```sass
UTCHMMA gdesc[UR6], gdesc[UR8],
         tmem[UR4], tmem[UR10], idesc[UR11], UP0;
```

这里没有 `.SP`，但 metadata 引入后，`tmem[...]` 的角色及其他寄存器位置重新
安排。外围指令的选择集合是：

| metadata 产生方式 | 主要 SASS 选择 |
|---|---|
| 直接 uniform 参数 | `LDCU.128`，或 `LDCU` + `LDCU.64` + `UMOV` |
| derived producer | `LDC`、`IADD3`、`MOV` |
| 谓词/控制重新分配 | `UISETP`、`ISETP`、`PLOP3`、`BRA` |
| 调度填充 | `NOP` |

最常见的选择变化是用一次 `LDCU.128` 取代较窄的 `LDCU`、`LDCU.64` 和
`UMOV` 组合。以下计数只是验证这套选择在多少配对中发生。

下面是同一 SS、f16、`runtime_zero` 上下文的真实 O0/O3 对照。

O0 中，dense case `THOR_MMA_000001` 的 A/B descriptor 和 mask 经过普通
GPR、`MOV` 与 `R2UR` 后进入核心指令。以下 O0 代码是选指相关片段，省略了
部分同值 `MOV`：

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
R2UR     UR12, R10;
R2UR     UR13, R11;
R2UR     UR14, R12;
R2UR     UR15, R8;
UTCHMMA  gdesc[UR4], gdesc[UR6],
          tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;
```

sparse case `THOR_MMA_000833` 在 O0 多出 metadata load 和地址形成；最终核心
助记符仍没有 `.SP`：

```sass
MOV      R2, 0x18;
LDC      R2, c[0x0][R2+0x380];
MOV      R3, 0x1c;
LDC      R3, c[0x0][R3+0x380];
IADD3    R2, PT, PT, R2, RZ, RZ;
MOV      R4, R2;
MOV      R5, R3;
R2UR     UR8, R4;
R2UR     UR9, R5;
R2UR     UR12, R11;
R2UR     UR13, R12;
R2UR     UR14, R8;
R2UR     UR15, R9;
UTCHMMA  gdesc[UR4], gdesc[UR6],
          tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;
```

O3 将上述 GPR 搬运合并为 uniform constant load。dense case：

```sass
LDCU     UR4,  c[0x0][0x3b0];
LDCU     UR5,  c[0x0][0x39c];
LDCU     UR6,  c[0x0][0x380];
LDCU.64  UR8,  c[0x0][0x388];
LDCU.64  UR10, c[0x0][0x390];
UISETP.NE.U32.AND UP0, UPT, UR4, URZ, UPT;
UMOV      UR4, URZ;
UTCHMMA   gdesc[UR8], gdesc[UR10],
           tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

对应的 sparse case：

```sass
LDCU      UR5, c[0x0][0x3b0];
LDCU      UR4, c[0x0][0x380];
LDCU.64   UR6, c[0x0][0x388];
LDCU.128  UR8, c[0x0][0x390];
UISETP.NE.U32.AND UP0, UPT, UR5, URZ, UPT;
UTCHMMA    gdesc[UR6], gdesc[UR8],
            tmem[UR4], tmem[UR10], idesc[UR11], UP0;
```

O0 解释 metadata 是怎样形成的，O3 则展示最终选择：`.sp` 没有选择新的 MMA
助记符，但参数装载合并成 `LDCU.128`，metadata、`idesc` 和其他核心操作数
使用的 UR 也被重新安排。

将每个 `mma.sp` 与对应的 `mma`、每个 `mma.ws.sp` 与对应的 `mma.ws`
严格配对，共得到 4,608 个源码/上下文配对，即 18,432 次 O0–O3 比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 5,564/18,432 |
| 外围指令类型或排列 | 18,432/18,432 |
| 核心位置活跃寄存器 | 2,848/18,432 |
| 核心 MMA 操作数或编码 | 13,824/18,432 |

外围序列每次都变化，主要原因是 `.sp` 引入 metadata 后，参数装载会在
`LDCU`、`LDCU.64`、`LDCU.128` 等形式之间重新组合，并可能改变准备指令的
排列。指令总数不一定变化，因为多条窄装载可以融合成较宽装载。

剩余 4,608 次比较的核心 MMA 文本和编码相同，不表示 `.sp` 没有作用；这些
配对的差异全部位于核心指令之前的数据准备和寄存器值中。

### `.ws`：作为完整 variant 会影响外围 lowering

`.ws` 的直接选择规则是：

```text
mma / mma.sp
    → UTC*MMA
    → 普通 A collector
    → disable-output-lane mask 操作数

mma.ws / mma.ws.sp
    → UTC*MMA.WS
    → B0–B3 collector
    → 不再使用普通 MMA 的 disable-output-lane mask 契约
```

因此普通 MMA 为 mask 选择的 `MOV/R2UR/UMOV/LOP3.LUT`，在 WS 中可能被删除；
如果删除改变了调度间隔，反汇编中可能留下 `NOP`。WS 本身没有固定新增一条
外围指令，它主要通过取消普通 mask 准备序列来改变选择集合。

同一个无 zero-column-mask 的 WS case `THOR_MMA_004865` 在两个主要观察级为：

```sass
// O0：辅助零值和 enable 生产尚未折叠
UTCHMMA.WS gdesc[UR4], gdesc[UR6],
            tmem[UR12], tmem[UR8], idesc[UR9], UR10, UP0;

// O3：准备序列折叠后的最终形式
UTCHMMA.WS gdesc[UR8], gdesc[UR10],
            tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

两级都稳定选择 `.WS`；O0 的额外 `UR10` 是尚未折叠的辅助操作数，不是另一个
WS modifier。

`.ws` 会同时改变 collector 角色和 PTX 操作数契约，不能构造只增加 `.ws`
字符串、其他操作数完全不变的合法 PTX。这里采用最接近的合法配对：

- CTA group 1；
- B0 discard 对普通 A discard；
- 不使用 zero-column-mask descriptor；
- kind、A 来源、稀疏性、上下文和优化级相同。

该配对得到 256 个源码/上下文设计，即 1,024 次 SASS 比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 304/1,024 |
| 外围指令类型或排列 | 352/1,024 |
| 核心位置活跃寄存器 | 352/1,024 |
| 核心 MMA 编码 | 1,024/1,024 |

O0 的 256 次比较全部改变了外围序列；O1–O3 每级各有 32/256 次。这主要来自
普通 MMA 的 disable-output-lane mask 与 WS 操作数契约不同。因而应把 `.ws`
理解成一个 lowering variant，而不是只有 `.WS` 后缀的局部改写。

### zero-column-mask descriptor：总会改变外围指令类型

WS 还可以在末尾增加 zero-column-mask descriptor，用于描述哪些 B 矩阵列按零
处理。它是可选操作数，不是点号 modifier，但同样属于 variant 的 lowering
契约。

它的映射关系是：

```text
无 zero-column-mask descriptor
    → 核心 UTC*MMA.WS 不带额外 descriptor register

有 zero-column-mask descriptor
    → 核心 UTC*MMA.WS 增加一个 UR descriptor 操作数
    → 直接参数选择 LDCU.64
    → derived producer 选择 LDC.64 + MOV
```

例如：

```sass
// 无 descriptor
UTCHMMA.WS ..., idesc[UR5], UP0;

// 有 descriptor
UTCHMMA.WS ..., idesc[UR5], UR12, UP0;
```

在带 guard 或非 uniform producer 的组合中，还可能在
`ISETP/BRA` 与 `UISETP/PLOP3` 之间重新选择控制序列；`NOP` 只反映随后的调度
调整。

O0 中，无 descriptor 的 `THOR_MMA_004865` 直接形成一个零值操作数：

```sass
MOV      R4, RZ;
MOV      R5, RZ;
MOV      R9, R4;
MOV      R10, R5;
R2UR     UR10, R9;
UTCHMMA.WS gdesc[UR4], gdesc[UR6],
            tmem[UR12], tmem[UR8], idesc[UR9], UR10, UP0;
```

带 descriptor 的 `THOR_MMA_005001` 则实际选择 64 位 load：

```sass
MOV      R2, 0x28;
LDC.64   R2, c[0x0][R2+0x380];
MOV      R5, R2;
MOV      R6, R3;
MOV      R4, R5;
MOV      R5, R6;
MOV      R9, R4;
MOV      R10, R5;
R2UR     UR10, R9;
UTCHMMA.WS gdesc[UR4], gdesc[UR6],
            tmem[UR12], tmem[UR8], idesc[UR9], UR10, UP0;
```

两条 O0 核心指令可以完全相同，差别由 `UR10` 的生产路径表达。到 O3 后，
区别变得更直接。无 descriptor：

```sass
LDCU.64   UR8,  c[0x0][0x388];
LDCU.64   UR10, c[0x0][0x390];
UTCHMMA.WS gdesc[UR8], gdesc[UR10],
            tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

带 descriptor：

```sass
LDCU.64   UR8,  c[0x0][0x388];
LDCU.64   UR10, c[0x0][0x390];
LDCU.64   UR12, c[0x0][0x3a8];
UTCHMMA.WS gdesc[UR8], gdesc[UR10],
            tmem[UR6], tmem[UR4], idesc[UR5], UR12, UP0;
```

这里可以直接看到 `%zero_mask_desc` 选择了一条额外 `LDCU.64`，其结果以
`UR12` 的形式进入核心 `UTCHMMA.WS`。

将“存在该 descriptor”与“不存在”配对后，得到 2,176 个源码/上下文设计，
即 8,704 次 SASS 比较：

| 检查项 | 发生变化 |
|---|---:|
| 完整函数 SASS 指令数 | 2,536/8,704 |
| 外围指令类型或排列 | 8,704/8,704 |
| 核心位置活跃寄存器 | 7,552/8,704 |
| 核心 MMA 操作数或编码 | 6,528/8,704 |

指令数变化时，带 descriptor 的版本增加 8 条或 16 条；O0 有
1,996/2,176 次数量变化，O1–O3 每级各 180/2,176 次。剩余 2,176 次核心
指令文本和编码相同，区别由外围加载到寄存器中的 descriptor 值承载。

## 证据与边界

- `.WS` 与 variant 的对应关系在 52,736 条目标 occurrence 中反例为 0。
- 所有目标助记符中均未观察到 `.SP`。
- 当前结果能确认 `.sp` 影响操作数/编码和寄存器，尚未逐 bit 解释稀疏编码。
