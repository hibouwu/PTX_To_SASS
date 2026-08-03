# `tcgen05.mma` 从 PTX 编译到 SASS 时发生什么变化

> 适用范围：NVIDIA Thor 架构、PTX ISA 9.0、编译目标 `sm_110a`
>
> 工具环境：CUDA 13.0，汇编器 `ptxas` V13.0.88，反汇编器 `nvdisasm` V13.0.85
>
> 报告性质：静态编译与反汇编结果的规则总结，不包含在 GPU 实机上运行的数值验证
>
> 数据来源：`thor_ptx90/results/` 目录中的生成清单、编译报告、SASS 归属记录和上下文差分摘要

> 查找单个修饰符（modifier）或语义维度时，先看
> [`mapping_rules/README.md`](mapping_rules/README.md)。本文保留跨维度解释、
> 完整编译降级过程和函数级 PTX 与 SASS 的对照。

## 编译器如何处理 `tcgen05.mma`：两层规则

`tcgen05.mma` 从 PTX 编译成 SASS 后，可以用两层规则描述：

1. 核心计算指令由 PTX 中的计算类型、操作数来源、协作线程块（Cooperative Thread Array，CTA）数量、权重驻留（weight-stationary）模式、分块缩放（block scaling）和操作数收集器（collector）状态共同决定。
2. 外围指令序列由 guard、发射线程、操作数生成方式和完成协议共同决定。

在本次 32,256 组配对比较中，外围上下文没有一次改变核心矩阵乘加（Matrix Multiply-Accumulate，MMA）指令的 SASS 指令家族。`UTCHMMA`、`UTCQMMA`、`UTCIMMA` 或 `UTCOMMA` 选哪一个，取决于“执行何种矩阵运算”，不取决于“由哪个线程发射”或“后续如何完成同步”。

但是，“核心指令家族不变”不等于“生成的机器代码不变”。上下文仍然会改变以下内容：

- 核心指令使用的谓词（predicate）寄存器；
- 物理寄存器编号和寄存器类别（普通寄存器 GPR、统一寄存器 UGPR、普通谓词 PRED、统一谓词 UPRED）；
- 指令执行位置上的活跃寄存器数量；
- 核心指令前后的控制、准备和同步指令；
- 最终机器指令的二进制编码。

因此，正确的理解模型不是“一条 PTX 固定翻译成一条完全确定的 SASS”，而是：

```text
PTX 语义形态
    决定核心 SASS 指令家族、修饰符和操作数形态

PTX 所处上下文
    决定谓词、寄存器分配和外围编译降级序列
```

这里的编译降级（lowering）指编译器把抽象的 PTX 指令逐步转化为具体硬件指令的过程。PTX 是 NVIDIA GPU 的虚拟指令集，SASS 是绑定特定 GPU 架构的机器指令。

## 从一条 PTX 指令开始

下面是一条简化后的 PTX 指令：

```ptx
tcgen05.mma.cta_group::2.kind::f16.ashift
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7},
    %enable;
```

各部分的含义：

| 部分 | 含义 |
|---|---|
| `tcgen05.mma` | 执行一次第五代张量核心（Tensor Core）矩阵乘加 |
| `.cta_group::2` | 两个 CTA 共同参与 |
| `.kind::f16` | 使用以 FP16 为代表的运算家族 |
| `.ashift` | 对 TMEM A 操作数的行位置做硬件移位 |
| `[%d_tmem]` | 结果 D 位于张量内存（Tensor Memory，TMEM） |
| `[%a_tmem]` | 输入矩阵 A 位于 TMEM |
| `%desc_b` | 输入矩阵 B 由共享内存描述符（shared-memory descriptor）描述 |
| `%idesc` | 指令描述符（instruction descriptor），描述形状和精确数据类型 |
| `%mask0...%mask7` | 指定哪些输出 lane 不写入结果 |
| `%enable` | 决定本次运算是否累加旧的 D |

相关术语：

- 张量核心（Tensor Core）是 GPU 中专门执行矩阵乘加的计算单元。
- TMEM 是供张量核心指令使用的专用存储空间。
- 共享内存（shared memory，本文简称 SMEM）是一个 CTA 内线程共享的片上存储空间。
- 描述符（descriptor）是描述数据如何存放和解释的编码值，不是数据本身。
- lane 是一组并行线程中的一个执行位置。

在当前实验条件下，这条 PTX 会产生类似下面的核心 SASS：

```text
UTCHMMA.2CTA.ASHIFT
    tmem[UR7], gdesc[UR8], tmem[UR6],
    tmem[UR4], idesc[UR5], UP0
```

SASS 中各部分的含义：

- `UTCHMMA` 是实际触发张量核心 MMA 的机器指令。
- `.2CTA` 表示两个 CTA 参与。
- `.ASHIFT` 对应 PTX 的 `.ashift`。
- `tmem[...]` 表示 TMEM 操作数。
- `gdesc[...]` 表示由通用描述符描述的操作数。
- `idesc[...]` 表示指令描述符。
- `UR7` 等名称是统一寄存器（uniform register），同一执行组共享值的物理寄存器。
- `UP0` 是统一谓词寄存器（uniform predicate register）。

## 核心 SASS 指令家族如何选择

### kind 决定使用哪一条 MMA 指令家族

PTX 的 `kind` 指定运算所属的数据类型家族。当前实验结果给出以下稳定映射：

| PTX `kind` | 核心 SASS | 含义 |
|---|---|---|
| `f16` | `UTCHMMA` | FP16 类浮点矩阵运算 |
| `tf32` | `UTCHMMA` | TF32 类浮点矩阵运算 |
| `f8f6f4` | `UTCQMMA` | FP8/FP6/FP4 混合低精度矩阵运算 |
| `mxf8f6f4` | `UTCQMMA` | 带分块缩放的 FP8/FP6/FP4 运算 |
| `i8` | `UTCIMMA` | INT8 整数矩阵运算 |
| `mxf4` | `UTCOMMA` | 带分块缩放的 MXF4 运算 |
| `mxf4nvf4` | `UTCOMMA` | MXF4 与 NVF4 家族运算 |

指令家族指共享一个主操作码（opcode）的机器指令集合。操作码是机器指令中表示“执行什么操作”的字段。`UTCHMMA` 等名字是反汇编器显示的助记符（mnemonic），即便于人阅读的操作码名称。

这条规则只描述家族选择，不代表 `f16` 和 `tf32` 的完整机器编码相同。更精确的类型、矩阵形状（M、N、K）和主方向（row-major 或 column-major）等信息还存放在 `idesc` 中。

### CTA group 决定是否出现 `.2CTA`

| PTX | SASS |
|---|---|
| `.cta_group::1` | 不添加 CTA 数量修饰符 |
| `.cta_group::2` | 添加 `.2CTA` |

例如：

```text
tcgen05.mma.cta_group::1.kind::f16
→ UTCHMMA

tcgen05.mma.cta_group::2.kind::f16
→ UTCHMMA.2CTA
```

修饰符（modifier）是附加在主助记符或操作数后面的字段，表达 CTA 数量、操作模式、复用状态等信息。

### weight-stationary 模式决定 `.WS`

PTX 的 `.ws` 表示权重驻留模式：让 B 操作数在硬件内部保持和复用，减少重复读取。

| PTX 变体（variant） | SASS |
|---|---|
| `mma` | 普通 MMA 助记符 |
| `mma.sp` | 普通 MMA 助记符，稀疏信息进入操作数或编码 |
| `mma.ws` | 添加 `.WS` |
| `mma.ws.sp` | 添加 `.WS`，稀疏信息进入操作数或编码 |

变体（variant）指同一基础指令的语义变体。`.sp` 表示稀疏（sparse）矩阵形式，额外需要元数据（metadata）来描述哪些元素存在。

一个重要发现：`.sp` 没有直接变成可见的 `.SP` SASS 修饰符。不能只看 SASS 助记符判断一条指令是不是稀疏 MMA，必须同时检查操作数位置和机器编码。

### `.ashift` 直接映射为 `.ASHIFT`

`.ashift` 只适用于 A 来自 TMEM 的合法形态：

```text
PTX .ashift
→ SASS .ASHIFT
```

例如 `UTCQMMA.2CTA` 加上 `.ashift` 后变成 `UTCQMMA.2CTA.ASHIFT`。

本实验的阴性用例也验证了两个非法边界：

- A 来自 SMEM 描述符时使用 `.ashift`：`ptxas` 拒绝。
- 分块缩放的 MMA 使用 `.ashift`：`ptxas` 拒绝。

阴性用例是实验者故意构造的非法输入，用来确认工具确实拒绝了错误组合。

## A、B 操作数从哪里取：TS 与 SS

本文用两个字母描述 A、B 操作数来源：

- `T` 表示张量内存（TMEM）；
- `S` 表示共享内存描述符。

`tcgen05.mma` 当前存在两种来源模式：

| 模式 | A 来源 | B 来源 | SASS 前两个源操作数 |
|---|---|---|---|
| SS | SMEM 描述符 | SMEM 描述符 | `gdesc[...]`, `gdesc[...]` |
| TS | TMEM 地址 | SMEM 描述符 | `tmem[...]`, `gdesc[...]` |

实际例子：

```text
SS:
UTCHMMA gdesc[UR8], gdesc[UR10], ...

TS:
UTCHMMA tmem[UR7], gdesc[UR8], ...
```

当前用例中没有发现来源映射反例。

覆盖量如下：

| 模式 | semantic form | syntax 源码实现 | expanded 源码实现 |
|---|---|---|---|
| SS | 432 | 552 | 4,416 |
| TS | 464 | 600 | 4,800 |

semantic form 是去掉 guard、producer 等上下文后，描述指令语义形态的规范记录。源码实现是实际生成的一份 PTX kernel 写法，不同写法可能表达同一个 semantic form。syntax 集合是受约束语法矩阵，expanded 集合是语法矩阵与多个静态上下文组合后的扩展矩阵。

TS 的实现数更多，因为只有 TS 能合法组合 `.ashift`。

## 分块缩放和缩放向量如何映射

分块缩放（block scaling）指一个数据块共享缩放因子（scale factor），以支持更低精度的数据表示。缩放向量（scale vector）描述缩放因子沿矩阵数据如何成组应用。

本实验观察到：

| PTX 规范语义 | 可见 SASS 结果 |
|---|---|
| `scale_vec::1X` | `UTCQMMA` 家族 |
| `scale_vec::2X` | `UTCOMMA` 家族，没有独立 `.2X` 文本 |
| `scale_vec::4X` | `UTCOMMA.4X` |
| `block16` 规范别名 | `UTCOMMA.4X` |
| `block32` 规范别名 | `UTCOMMA`，没有独立 `.BLOCK32` 文本 |

“没有独立文本”不表示信息被编译器丢弃。它可能已经由操作码家族、`idesc` 或机器编码共同表达。这里只能说反汇编文本中看不到一对一的同名修饰符。

## collector 如何映射

collector 是张量核心操作数收集和复用机制。硬件暂存 A 或 B，让后续 MMA 重用已经收集的操作数。四个动作的含义：

| 动作 | 含义 |
|---|---|
| `fill` | 装入 collector 并保留给后续使用 |
| `use` | 使用已装入的值，使用后仍保留 |
| `lastuse` | 最后一次使用，之后可以释放 |
| `discard` | 本次使用后不保留 |

### A collector

| PTX collector | SASS A 操作数修饰符 |
|---|---|
| `a::discard` | 无 A 修饰符 |
| `a::fill` | `.A_KEEP` |
| `a::use` | `.A_REUSE.A_KEEP` |
| `a::lastuse` | `.A_REUSE` |

`KEEP` 表示使用后继续保留，`REUSE` 表示使用已经收集的值。

例如：

```text
.collector::a::fill
→ gdesc[UR8].A_KEEP

.collector::a::use
→ gdesc[UR8].A_REUSE.A_KEEP

.collector::a::lastuse
→ gdesc[UR8].A_REUSE
```

### B collector

B collector 用于权重驻留形式：

| PTX collector | SASS B 操作数修饰符 |
|---|---|
| `bN::discard` | 无 `B_KEEP` 或 `B_REUSE` |
| `bN::fill` | `.B_KEEP` |
| `bN::use` | `.B_REUSE.B_KEEP` |
| `bN::lastuse` | `.B_REUSE` |

`N` 是缓冲区编号：

| PTX buffer | SASS |
|---|---|
| `b0` | 默认缓冲区，不显示编号 |
| `b1` | `.BUFFER1` |
| `b2` | `.BUFFER2` |
| `b3` | `.BUFFER3` |

例如：

```text
.collector::b2::use
→ gdesc[UR10].B_REUSE.B_KEEP.BUFFER2
```

## 上下文如何改变编译降级

上下文指目标 PTX 指令之外但可能影响编译结果的信息，包括 guard、操作数由常量还是计算产生、由哪个 lane 发射，以及指令之后是否增加完成协议。

本实验以 `runtime_zero` 为基线（baseline）。基线是所有处理组与之比较的参考写法。每组实验保持 semantic form 和源码变体一致，只改变一个上下文配置文件（profile）。配置文件是一组明确的上下文赋值。配对比较指把同一个设计在基线和处理配置文件下的结果一一对齐比较。

### enable 决定是否累加旧 D

`enable-input-d` 是一个谓词：

- true：执行 `D = A × B + D`
- false：执行 `D = A × B`，不读取旧 D

在 O1、O2、O3 编译优化级下，编译器把已知常量折叠进核心 SASS。例如：

```text
运行时 enable:
..., UP0

静态 false:
..., !UPT
```

`UPT` 是恒真的统一谓词，`!UPT` 是对它取反，因此恒假。编译器把运行时表达式替换为编译期常量的行为叫常量折叠。

O0 到 O3 是四个编译优化级：O0 尽量少优化以便观察原始降级过程，O1 启用基础优化，O2 启用更完整的优化，O3 是最高常用优化级。

在当前微型 kernel 中，O2 和 O3 的全部 13,184 个目标出现位置（occurrence）的核心操作文本、编码和活跃寄存器计数完全相同。出现位置指 PTX 源码中一条实际出现的目标指令。

### guard 有两种降级方式

guard 是写在 PTX 指令前的执行条件，例如 `@%p tcgen05.mma ...`。它可能直接成为 SASS 指令前的谓词：

```text
@UP1 UTCHMMA ...
```

也可能由外围控制指令处理，使核心 MMA 文本不出现显式 guard。

O2/O3 的 1,152 组 guard 比较中：352 组改变了核心规范操作，508 组改变了核心寄存器布局，496 组改变了核心位置的活跃寄存器数量。

正 guard 和负 guard 的变化数量相同。guard 的真假极性会改变具体条件，但没有改变编译器采用哪类降级路径的覆盖范围。

### lane-0 发射线程主要改变寄存器压力

发射线程（issuer）是实际发射 MMA 指令的线程。`lane0_issuer` 配置文件限制 lane 0 成为发射者。

在 O1/O2/O3 下：核心规范操作变化为 0，1,152/1,152 组核心活跃寄存器数发生变化，168 组核心物理寄存器发生纯重编号（全部来自稀疏 `.sp` 变体）。

只比较操作码会漏掉发射线程对资源使用的影响。

### derived producer 在优化后被消除

producer 是产生目标指令输入值的前序计算。`derived_producers` 配置文件通过额外计算得到描述符、地址或谓词，而不是直接使用参数。

结果是：O0 的完整 kernel 序列发生变化，但 O1/O2/O3 的完整规范化 kernel 序列完全不变。这些额外 producer 在 O1 以上被编译器吸收或消除。

### completion 改变后继协议，不改变核心 MMA

completion 是 MMA 发出后如何确认完成的协议，包括 commit 和 mbarrier。

- commit 表示提交此前发出的异步张量核心操作。
- mbarrier 是内存屏障（memory barrier），一种记录异步工作到达和完成状态的同步对象。

`commit_completion` 在所有优化级都会改变完整 kernel 序列和指令数，但不会改变核心 MMA 助记符、核心操作数或核心寄存器布局。completion 应当建模为 MMA 的后继协议，而不是 MMA 操作码的组成部分。

## 寄存器变化如何理解

SASS 使用真实物理寄存器。本文涉及四类：

| 名称 | SASS 写法 | 用途 |
|---|---|---|
| GPR（普通通用寄存器） | `R0`、`R1`…… | 普通线程私有数据 |
| UGPR（统一通用寄存器） | `UR0`、`UR1`…… | 同一执行组共享的数据 |
| PRED（普通谓词寄存器） | `P0`、`P1`…… | 普通真假条件 |
| UPRED（统一谓词寄存器） | `UP0`、`UP1`…… | 统一真假条件 |

报告把寄存器变化分成三类：

1. 仅重编号：例如 `UR4 → UR7`，类别和复用关系不变。
2. 类别变化：例如 `UP0 → UPT`，从可写谓词变成特殊恒真谓词。
3. 别名关系变化：原本两个操作数引用同一个寄存器，后来变成不同寄存器，或反过来。别名指两个操作数是否指向同一个物理寄存器。

32,256 组上下文比较的结果：

| 现象 | 数量 | 比例 |
|---|---|---|
| 核心寄存器布局变化 | 10,344 | 32.1% |
| 其中仅重编号 | 1,320 | 4.1% |
| 寄存器类别变化 | 9,024 | 28.0% |
| 别名关系变化 | 9,024 | 28.0% |
| 核心位置活跃数变化 | 15,488 | 48.0% |
| kernel 峰值活跃数变化 | 17,592 | 54.5% |

活跃寄存器指在某条指令位置之前已经保存了值、并且之后还可能被使用的寄存器。kernel 峰值活跃数是整个 kernel 中同时活跃寄存器数量的最大值。

在 O1/O2/O3 baseline 的核心 MMA 位置，平均活跃寄存器为：

| 模式 | GPR | PRED | UGPR | UPRED |
|---|---|---|---|---|
| SS | 1 | 2 | 8.21，最大 9 | 1 |
| TS | 1 | 2 | 7.12，最大 8 | 1 |

SS 比 TS 平均多约一个活跃 UGPR。共享内存 A 描述符比 TMEM A 地址需要更多统一状态。

本次上下文比较没有发现 `LDL`/`STL` 本地内存指令数量变化。`LDL` 和 `STL` 是读写线程本地内存的 SASS 指令，常被用作寄存器溢出（spill）的线索。spill 指物理寄存器不足时编译器暂时把值放到本地内存。仅凭 `LDL`/`STL` 仍不能断言一定发生了 spill。

## 核心指令和完整降级必须分开看

本次比较得到：

| 比较对象 | 发生变化的配对 |
|---|---|
| 核心 MMA 助记符 | 0 / 32,256 |
| 核心规范操作 | 9,024 / 32,256 |
| 完整 kernel 规范序列 | 28,800 / 32,256 |
| kernel 指令数 | 17,396 / 32,256 |

规范操作是把具体寄存器编号和指令地址消除后得到的可比较形式。例如 `UR4` 和 `UR9` 都会抽象成“第一个 UGPR”，但 R、UR、P、UP 的类别不会混合。这个过程叫规范化（normalization）。

因此：

- 判断“执行哪一种张量核心运算”，看核心助记符和核心修饰符。
- 判断“PTX 在这个上下文中怎样实现”，看完整 kernel。
- 判断“资源使用是否改变”，看具体寄存器、活跃数和本地内存指令。
- 判断“机器码是否完全相同”，必须比较完整指令编码，不能只看文本。

## 当前可以写成的规则

根据当前证据，规则分三档。

### 当前样本中零反例的确定性规则

```text
kind
    → UTCHMMA / UTCQMMA / UTCIMMA / UTCOMMA 家族

cta_group::2
    → .2CTA

mma.ws / mma.ws.sp
    → .WS

ashift
    → .ASHIFT

SS
    → A 使用 gdesc，B 使用 gdesc

TS
    → A 使用 tmem，B 使用 gdesc

collector fill/use/lastuse/discard
    → KEEP/REUSE 修饰符组合
```

### 必须带条件的上下文规则

```text
已知 enable 常量 + O1 以上
    → enable 谓词被折叠为 UPT 或 !UPT

guard
    → 直接 SASS 谓词化或外围控制路径

lane0 issuer
    → 核心操作码通常不变，但活跃寄存器改变

derived producer + O1 以上
    → 当前测试中的额外 producer 被优化消除

completion
    → 改变后继序列，不改变核心 MMA
```

谓词化（predication）指在一条机器指令上直接附加真假执行条件，而不是单独跳转。

### 当前还不能写成确定规则的内容

以下内容尚未被实验逐字段冻结：

- `idesc` 中 M、N、K 的精确矩阵形状（M、N、K 是矩阵乘法的三个尺寸：`M×K` 乘以 `K×N`）；
- A、B、D 的精确数据类型组合；
- row-major 或 column-major 方向（major 指数据以行还是以列为主要连续方向）；
- SMEM 描述符的步长（stride，相邻行或列在地址上的距离）和地址重排（swizzle，为改善存储访问分布而做的地址重排）；
- 每个 PTX 字段对应的精确机器编码位（bit，二进制编码中的一个 0 或 1）。

当前用例把这些描述符当作运行时参数，可以证明 `ptxas` 接受语法并生成 SASS，但不能反推出描述符内每个字段的独立映射。

## 这份报告证明了什么，又没有证明什么

已经证明：

- 当前受约束合法语法矩阵可以被 CUDA 13.0 `ptxas` 接受。
- 每条目标 PTX 出现位置都能归属到一条核心 MMA SASS。
- 上述 kind、CTA group、TS/SS、WS、ASHIFT 和 collector 映射在当前样本中稳定，反例数为 0。
- 上下文对核心操作、寄存器和完整 kernel 的影响可以被配对测量。
- 协议层的 42 个静态用例（34 个独立协议原语和 8 个完整生命周期）在 O0/O1/O2/O3 全部通过编译。
- 三个已知非法组合得到预期拒绝。

尚未证明：

- 这些原始描述符在 Thor 实机上代表合法矩阵布局。
- 运算得到正确数值。
- `.cta_group::2` 的两个 CTA 在真实 cluster launch 中正确协作。
- 哪种写法性能更好。
- 所有可能的描述符位型都已覆盖。

静态编译只说明工具链能生成目标机器码。实机语义验证还需要合法描述符、真实 TMEM 分配、输入数据、结果对照和同步检查。

## 实验规模和证据来源

| 层次 | 结果 |
|---|---|
| syntax 源码实现 | 1,152 |
| semantic form | 896 |
| expanded 源码实现 | 9,216 |
| expanded 逻辑设计点（logical design） | 7,168 |
| syntax 编译 | 72 / 72 通过 |
| expanded 编译 | 576 / 576 通过 |
| SASS 归属配对 | 36,864 / 36,864 完成 |
| SASS 目标出现位置 | 52,736 |
| 上下文配对比较 | 32,256 / 32,256 完成 |
| 协议层编译 | 168 / 168 通过 |
| 效应切片 SASS 检查 | 32 / 32 通过 |
| 阴性探针 | 3 / 3 通过 |

逻辑设计点是 semantic form 与适用静态上下文组合后的逻辑实验点。归属配对（attribution）是把 PTX 中的目标出现位置与 SASS 中对应核心指令配对。

主要机器可读来源：

- `results/expanded/sources/manifest.jsonl`：每条源码实现的实验坐标。
- `results/expanded/sass/sass_attribution.jsonl`：PTX 与核心 SASS 的配对。
- `results/context-comparison/context_summary.csv`：上下文差分汇总。
- `results/context-comparison/comparison_report.json`：输入与输出哈希。
- `results/protocol-layers/compile_report.json`：协议层验证。
- `results/negative-probes/negative_probe_report.json`：非法组合诊断。

JSONL 是每行一个 JSON 对象的文本格式，适合保存大量逐条记录。CSV 是逗号分隔表格格式。哈希（SHA-256）是文件内容的数字指纹，用于确认文件没有被意外修改。

## 附录 A：三个完整 PTX → SASS 对照例子

下面三个例子均来自本实验的 syntax 集合，PTX 版本为 9.0，编译目标为 `sm_110a`。SASS 由对应 cubin 使用 `nvdisasm` 反汇编得到。展示的是 O3 完整函数，而不只是核心 MMA 一行。

外围 SASS 指令速查：

| SASS 内容 | 作用 |
|---|---|
| `.section/.global/.type/.size/.other` | 函数在二进制文件中的元数据 |
| `LDC` | 从常量内存（constant memory）装入普通寄存器 |
| `LDCU` | 从常量内存装入统一寄存器 |
| `UISETP` | 比较统一整数并生成统一谓词 |
| `UMOV` | 在统一寄存器之间移动或构造值 |
| `PLOP3.LUT` | 用查找表执行谓词布尔运算 |
| `ELECT` | 从参与线程中选出负责当前发射路径的线程 |
| `BRA.U.ANY` | 根据统一任意条件跳转 |
| `EXIT` | 结束 kernel |
| 末尾 `BRA` 和 `NOP` | 函数结束路径以及代码对齐填充 |

常量内存是 GPU 的只读常量地址空间，kernel 参数由驱动放入其中，SASS 使用 `c[0x0][偏移]` 读取。查找表（Look-Up Table，LUT）用预设真值表实现布尔运算。代码对齐让函数或指令从硬件要求的地址边界开始。

反汇编左侧的 `/*00a0*/` 是指令在函数中的十六进制字节偏移。`.L_x_*` 是编译器生成的跳转标签。`@P0` 表示只有谓词 `P0` 为真时才执行该条 SASS。`NOP` 不执行实际工作。`.section` 后的 `"ax"` 表示这段内容可被加载并执行，`@progbits` 表示该节中保存实际程序字节。`STO_CUDA_ENTRY` 等 `.other` 内容是 ELF 二进制中的 CUDA 符号属性，不参与 MMA 计算。ELF 是 cubin 使用的一种可执行文件组织格式。

### A.1 SS、CTA group 1、普通 FP16 MMA

这个例子展示 A、B 都使用 SMEM 描述符的 SS 模式。

| 证据字段 | 值 |
|---|---|
| case | `THOR_MMA_000001` |
| PTX 分片 | `thor_tcgen05_mma_0000.ptx` |
| kernel | `thor_tcgen05_mma_000001` |
| O3 核心 SASS 偏移 | `0x00a0` |

完整 PTX kernel：

```ptx
.visible .entry thor_tcgen05_mma_000001(
    .param .u32 p_d_tmem,
    .param .u32 p_a_tmem,
    .param .u64 p_desc_a,
    .param .u64 p_desc_b,
    .param .u32 p_meta_tmem,
    .param .u32 p_idesc,
    .param .u32 p_scale_a_tmem,
    .param .u32 p_scale_b_tmem,
    .param .u64 p_zero_mask_desc,
    .param .u32 p_enable,
    .param .u32 p_guard,
    .param .u64 p_mbar
)
{
    .reg .b32 %d_tmem, %a_tmem, %meta_tmem, %idesc;
    .reg .b32 %scale_a_tmem, %scale_b_tmem, %enable_u32, %guard_u32;
    .reg .b64 %desc_a, %desc_b, %zero_mask_desc, %mbar;
    .reg .pred %enable, %guard, %issuer;
    .reg .b32 %mask<4>;

    ld.param.b32 %d_tmem, [p_d_tmem];
    ld.param.b32 %a_tmem, [p_a_tmem];
    ld.param.b64 %desc_a, [p_desc_a];
    ld.param.b64 %desc_b, [p_desc_b];
    ld.param.b32 %meta_tmem, [p_meta_tmem];
    ld.param.b32 %idesc, [p_idesc];
    ld.param.b32 %scale_a_tmem, [p_scale_a_tmem];
    ld.param.b32 %scale_b_tmem, [p_scale_b_tmem];
    ld.param.b64 %zero_mask_desc, [p_zero_mask_desc];
    ld.param.b32 %enable_u32, [p_enable];
    ld.param.b32 %guard_u32, [p_guard];
    ld.param.b64 %mbar, [p_mbar];

    setp.ne.u32 %enable, %enable_u32, 0;
    setp.ne.u32 %guard, %guard_u32, 0;
    mov.b32 %mask0, 0;
    mov.b32 %mask1, 0;
    mov.b32 %mask2, 0;
    mov.b32 %mask3, 0;

    tcgen05.mma.cta_group::1.kind::f16
        [%d_tmem], %desc_a, %desc_b, %idesc,
        {%mask0, %mask1, %mask2, %mask3}, %enable;
    ret;
}
```

公共测试模板声明了 metadata、scale、guard 和 mbarrier 等参数，即使这个具体 case 没有使用其中一部分。`ld.param` 是 PTX 的参数装载指令，`.u32/.u64` 表示 32/64 位无符号整数，`.b32/.b64` 表示只关心位宽的 32/64 位寄存器类型。`.visible .entry` 声明一个可从外部启动的 GPU kernel 入口。`setp.ne` 比较两个值是否不相等并生成谓词。`mov` 移动或构造值。`ret` 从 kernel 返回。

完整 O3 SASS：

```sass
.section .text.thor_tcgen05_mma_000001,"ax",@progbits
.align 128
.global thor_tcgen05_mma_000001
.type   thor_tcgen05_mma_000001,@function
.size   thor_tcgen05_mma_000001,
        (.L_x_215 - thor_tcgen05_mma_000001)
.other  thor_tcgen05_mma_000001,
        @"STO_CUDA_ENTRY STV_DEFAULT"

thor_tcgen05_mma_000001:
.text.thor_tcgen05_mma_000001:
    /*0000*/ LDC R1, c[0x0][0x37c] ;
    /*0010*/ LDCU UR4, c[0x0][0x3b0] ;
    /*0020*/ PLOP3.LUT P0, PT, PT, PT, PT, 0x80, 0x8 ;
    /*0030*/ LDCU UR5, c[0x0][0x39c] ;
    /*0040*/ LDCU UR6, c[0x0][0x380] ;
    /*0050*/ LDCU.64 UR8, c[0x0][0x388] ;
    /*0060*/ LDCU.64 UR10, c[0x0][0x390] ;
    /*0070*/ UISETP.NE.U32.AND UP0, UPT, UR4, URZ, UPT ;
    /*0080*/ UMOV UR4, URZ ;

.L_x_150:
    /*0090*/ @P0 ELECT P1, URZ, PT ;
    /*00a0*/ UTCHMMA
                 gdesc[UR8], gdesc[UR10],
                 tmem[UR6], tmem[UR4],
                 idesc[UR5], UP0 ;
    /*00b0*/ @P1 PLOP3.LUT P0, PT, P1, PT, PT, 0x8, 0x80 ;
    /*00c0*/ PLOP3.LUT P1, PT, PT, PT, PT, 0x8, 0x80 ;
    /*00d0*/ @P0 BRA.U.ANY `(.L_x_150) ;
    /*00e0*/ EXIT ;

.L_x_151:
    /*00f0*/ BRA `(.L_x_151);
    /*0100*/ NOP;
    /*0110*/ NOP;
    /*0120*/ NOP;
    /*0130*/ NOP;
    /*0140*/ NOP;
    /*0150*/ NOP;
    /*0160*/ NOP;
    /*0170*/ NOP;
.L_x_215:
```

阅读顺序：

1. `LDC` 和 `LDCU` 从 kernel 参数区装入 D 地址、A/B 描述符、`idesc` 和 enable。
2. `UISETP` 把 32 位 enable 值转换为 `UP0` 谓词。
3. `UMOV UR4, URZ` 构造值为零的输出 mask。`URZ` 是恒为零的统一特殊寄存器。
4. `ELECT` 和 `BRA.U.ANY` 维护单线程发射所需的选举循环。
5. `UTCHMMA` 的前两个源操作数都是 `gdesc`，直接体现 SS 模式。

`RZ` 是恒为零的普通特殊寄存器。`PT` 和 `UPT` 是恒真的普通谓词和统一谓词。`NE` 表示不相等，`U32` 表示无符号 32 位整数，`AND` 表示逻辑与。`PLOP3.LUT` 末尾的立即数指定具体布尔真值表，立即数是直接写在指令里的常量。

### A.2 TS、CTA group 2、ASHIFT

这个例子同时展示 TS、两个 CTA 和 A 行移位。

| 证据字段 | 值 |
|---|---|
| case | `THOR_MMA_000078` |
| PTX 分片 | `thor_tcgen05_mma_0001.ptx` |
| kernel | `thor_tcgen05_mma_000078` |
| O3 核心 SASS 偏移 | `0x0090` |

完整 PTX kernel：

```ptx
.visible .entry thor_tcgen05_mma_000078(
    .param .u32 p_d_tmem,
    .param .u32 p_a_tmem,
    .param .u64 p_desc_a,
    .param .u64 p_desc_b,
    .param .u32 p_meta_tmem,
    .param .u32 p_idesc,
    .param .u32 p_scale_a_tmem,
    .param .u32 p_scale_b_tmem,
    .param .u64 p_zero_mask_desc,
    .param .u32 p_enable,
    .param .u32 p_guard,
    .param .u64 p_mbar
)
{
    .reg .b32 %d_tmem, %a_tmem, %meta_tmem, %idesc;
    .reg .b32 %scale_a_tmem, %scale_b_tmem, %enable_u32, %guard_u32;
    .reg .b64 %desc_a, %desc_b, %zero_mask_desc, %mbar;
    .reg .pred %enable, %guard, %issuer;
    .reg .b32 %mask<8>;

    ld.param.b32 %d_tmem, [p_d_tmem];
    ld.param.b32 %a_tmem, [p_a_tmem];
    ld.param.b64 %desc_a, [p_desc_a];
    ld.param.b64 %desc_b, [p_desc_b];
    ld.param.b32 %meta_tmem, [p_meta_tmem];
    ld.param.b32 %idesc, [p_idesc];
    ld.param.b32 %scale_a_tmem, [p_scale_a_tmem];
    ld.param.b32 %scale_b_tmem, [p_scale_b_tmem];
    ld.param.b64 %zero_mask_desc, [p_zero_mask_desc];
    ld.param.b32 %enable_u32, [p_enable];
    ld.param.b32 %guard_u32, [p_guard];
    ld.param.b64 %mbar, [p_mbar];

    setp.ne.u32 %enable, %enable_u32, 0;
    setp.ne.u32 %guard, %guard_u32, 0;
    mov.b32 %mask0, 0;
    mov.b32 %mask1, 0;
    mov.b32 %mask2, 0;
    mov.b32 %mask3, 0;
    mov.b32 %mask4, 0;
    mov.b32 %mask5, 0;
    mov.b32 %mask6, 0;
    mov.b32 %mask7, 0;

    tcgen05.mma.cta_group::2.kind::f16.ashift
        [%d_tmem], [%a_tmem], %desc_b, %idesc,
        {%mask0, %mask1, %mask2, %mask3,
         %mask4, %mask5, %mask6, %mask7}, %enable;
    ret;
}
```

完整 O3 SASS：

```sass
.section .text.thor_tcgen05_mma_000078,"ax",@progbits
.align 128
.global thor_tcgen05_mma_000078
.type   thor_tcgen05_mma_000078,@function
.size   thor_tcgen05_mma_000078,
        (.L_x_203 - thor_tcgen05_mma_000078)
.other  thor_tcgen05_mma_000078,
        @"STO_CUDA_ENTRY STV_DEFAULT"

thor_tcgen05_mma_000078:
.text.thor_tcgen05_mma_000078:
    /*0000*/ LDC R1, c[0x0][0x37c] ;
    /*0010*/ LDCU UR4, c[0x0][0x3b0] ;
    /*0020*/ PLOP3.LUT P0, PT, PT, PT, PT, 0x80, 0x8 ;
    /*0030*/ LDCU UR5, c[0x0][0x39c] ;
    /*0040*/ LDCU.64 UR8, c[0x0][0x390] ;
    /*0050*/ LDCU.64 UR6, c[0x0][0x380] ;
    /*0060*/ UISETP.NE.U32.AND UP0, UPT, UR4, URZ, UPT ;
    /*0070*/ UMOV UR4, URZ ;

.L_x_119:
    /*0080*/ @P0 ELECT P1, URZ, PT ;
    /*0090*/ UTCHMMA.2CTA.ASHIFT
                 tmem[UR7], gdesc[UR8],
                 tmem[UR6], tmem[UR4],
                 idesc[UR5], UP0 ;
    /*00a0*/ @P1 PLOP3.LUT P0, PT, P1, PT, PT, 0x8, 0x80 ;
    /*00b0*/ PLOP3.LUT P1, PT, PT, PT, PT, 0x8, 0x80 ;
    /*00c0*/ @P0 BRA.U.ANY `(.L_x_119) ;
    /*00d0*/ EXIT ;

.L_x_120:
    /*00e0*/ BRA `(.L_x_120);
    /*00f0*/ NOP;
    /*0100*/ NOP;
    /*0110*/ NOP;
    /*0120*/ NOP;
    /*0130*/ NOP;
    /*0140*/ NOP;
    /*0150*/ NOP;
    /*0160*/ NOP;
    /*0170*/ NOP;
.L_x_203:
```

最重要的一行是：

```text
UTCHMMA.2CTA.ASHIFT tmem[...], gdesc[...], ...
```

它同时验证了四条规则：

- `kind::f16 → UTCHMMA`
- `cta_group::2 → .2CTA`
- `.ashift → .ASHIFT`
- TS 模式：A 操作数是 `tmem`，B 操作数是 `gdesc`

### A.3 WS、B2 collector 的 fill → use

这个例子有两次目标出现：第一条填充 B2 collector，第二条复用并继续保留。

| 证据字段 | 值 |
|---|---|
| case | `THOR_MMA_000620` |
| PTX 分片 | `thor_tcgen05_mma_0009.ptx` |
| kernel | `thor_tcgen05_mma_000620` |
| O3 核心 SASS 偏移 | `0x00a0`、`0x0100` |

完整 PTX kernel：

```ptx
.visible .entry thor_tcgen05_mma_000620(
    .param .u32 p_d_tmem,
    .param .u32 p_a_tmem,
    .param .u64 p_desc_a,
    .param .u64 p_desc_b,
    .param .u32 p_meta_tmem,
    .param .u32 p_idesc,
    .param .u32 p_scale_a_tmem,
    .param .u32 p_scale_b_tmem,
    .param .u64 p_zero_mask_desc,
    .param .u32 p_enable,
    .param .u32 p_guard,
    .param .u64 p_mbar
)
{
    .reg .b32 %d_tmem, %a_tmem, %meta_tmem, %idesc;
    .reg .b32 %scale_a_tmem, %scale_b_tmem, %enable_u32, %guard_u32;
    .reg .b64 %desc_a, %desc_b, %zero_mask_desc, %mbar;
    .reg .pred %enable, %guard, %issuer;

    ld.param.b32 %d_tmem, [p_d_tmem];
    ld.param.b32 %a_tmem, [p_a_tmem];
    ld.param.b64 %desc_a, [p_desc_a];
    ld.param.b64 %desc_b, [p_desc_b];
    ld.param.b32 %meta_tmem, [p_meta_tmem];
    ld.param.b32 %idesc, [p_idesc];
    ld.param.b32 %scale_a_tmem, [p_scale_a_tmem];
    ld.param.b32 %scale_b_tmem, [p_scale_b_tmem];
    ld.param.b64 %zero_mask_desc, [p_zero_mask_desc];
    ld.param.b32 %enable_u32, [p_enable];
    ld.param.b32 %guard_u32, [p_guard];
    ld.param.b64 %mbar, [p_mbar];

    setp.ne.u32 %enable, %enable_u32, 0;
    setp.ne.u32 %guard, %guard_u32, 0;

    tcgen05.mma.ws.cta_group::1.kind::f16.collector::b2::fill
        [%d_tmem], %desc_a, %desc_b, %idesc, %enable;
    tcgen05.mma.ws.cta_group::1.kind::f16.collector::b2::use
        [%d_tmem], %desc_a, %desc_b, %idesc, %enable;
    ret;
}
```

完整 O3 SASS：

```sass
.section .text.thor_tcgen05_mma_000620,"ax",@progbits
.align 128
.global thor_tcgen05_mma_000620
.type   thor_tcgen05_mma_000620,@function
.size   thor_tcgen05_mma_000620,
        (.L_x_176 - thor_tcgen05_mma_000620)
.other  thor_tcgen05_mma_000620,
        @"STO_CUDA_ENTRY STV_DEFAULT"

thor_tcgen05_mma_000620:
.text.thor_tcgen05_mma_000620:
    /*0000*/ LDC R1, c[0x0][0x37c] ;
    /*0010*/ LDCU UR4, c[0x0][0x3b0] ;
    /*0020*/ PLOP3.LUT P0, PT, PT, PT, PT, 0x80, 0x8 ;
    /*0030*/ LDCU UR5, c[0x0][0x39c] ;
    /*0040*/ LDCU UR6, c[0x0][0x380] ;
    /*0050*/ LDCU.64 UR8, c[0x0][0x388] ;
    /*0060*/ LDCU.64 UR10, c[0x0][0x390] ;
    /*0070*/ UISETP.NE.U32.AND UP0, UPT, UR4, URZ, UPT ;
    /*0080*/ UMOV UR4, URZ ;

.L_x_49:
    /*0090*/ @P0 ELECT P1, URZ, PT ;
    /*00a0*/ UTCHMMA.WS
                 gdesc[UR8],
                 gdesc[UR10].B_KEEP.BUFFER2,
                 tmem[UR6], tmem[UR4],
                 idesc[UR5], UP0 ;
    /*00b0*/ @P1 PLOP3.LUT P0, PT, P1, PT, PT, 0x8, 0x80 ;
    /*00c0*/ PLOP3.LUT P1, PT, PT, PT, PT, 0x8, 0x80 ;
    /*00d0*/ @P0 BRA.U.ANY `(.L_x_49) ;
    /*00e0*/ PLOP3.LUT P0, PT, PT, PT, PT, 0x80, 0x8 ;

.L_x_50:
    /*00f0*/ @P0 ELECT P1, URZ, PT ;
    /*0100*/ UTCHMMA.WS
                 gdesc[UR8],
                 gdesc[UR10].B_REUSE.B_KEEP.BUFFER2,
                 tmem[UR6], tmem[UR4],
                 idesc[UR5], UP0 ;
    /*0110*/ @P1 PLOP3.LUT P0, PT, P1, PT, PT, 0x8, 0x80 ;
    /*0120*/ PLOP3.LUT P1, PT, PT, PT, PT, 0x8, 0x80 ;
    /*0130*/ @P0 BRA.U.ANY `(.L_x_50) ;
    /*0140*/ EXIT ;

.L_x_51:
    /*0150*/ BRA `(.L_x_51);
    /*0160*/ NOP;
    ...
.L_x_176:
```

两条核心指令体现 collector 状态转换：

```text
fill → .B_KEEP.BUFFER2
use  → .B_REUSE.B_KEEP.BUFFER2
```

`fill` 装入并保留，因此出现 `B_KEEP`。下一条 `use` 使用已经装入的值，同时出现 `B_REUSE`，并因为之后仍要保留而继续带有 `B_KEEP`。

这三个函数也说明为什么不能只数核心 MMA：每条 MMA 周围都有参数装载、谓词生成、线程选举和控制循环。核心数值运算仍由一条 `UTCHMMA*` 完成，但整个 PTX kernel 会对应多条 SASS。

## 附录 B：术语速查

| 术语 | 解释 |
|---|---|
| GPU | 并行计算处理器 |
| NVIDIA Thor | 本实验面向的 NVIDIA GPU 系列 |
| 计算能力（compute capability） | NVIDIA 表示 GPU 指令和功能代际的版本号 |
| `sm_110a` | Thor 架构专用的 PTX 编译目标 |
| CUDA Toolkit | NVIDIA 提供的 GPU 编译器、库和开发工具集合 |
| PTX | GPU 虚拟指令集，尚未绑定具体机器编码 |
| PTX ISA | PTX 指令集架构规范 |
| SASS | GPU 实际执行的、与架构绑定的机器指令 |
| `ptxas` | 把 PTX 编译成目标 GPU 机器码的汇编器 |
| `nvdisasm` | 把 GPU 机器码反汇编成人可读 SASS 的工具 |
| cubin | 保存已编译 GPU 二进制代码的文件 |
| kernel | 由 CPU 启动、在 GPU 上执行的函数 |
| 编译降级（lowering） | 从抽象指令逐步变成具体机器指令的编译过程 |
| 操作码（opcode） | 表示机器指令执行什么操作的编码字段 |
| 助记符（mnemonic） | 操作码的人类可读名称，如 `UTCHMMA` |
| 修饰符（modifier） | 对主指令或操作数追加的模式修饰 |
| 操作数（operand） | 指令读取或写入的值 |
| MMA | 矩阵乘加（Matrix Multiply-Accumulate） |
| A、B、D | MMA 中的两个输入矩阵 A、B 和输出/累加矩阵 D |
| 张量核心（Tensor Core） | GPU 中专门执行矩阵运算的硬件单元 |
| TMEM | 张量内存（Tensor Memory），张量核心使用的专用存储空间 |
| SMEM | 共享内存（shared memory），一个 CTA 内共享的片上存储 |
| FP16 / `f16` | 16 位浮点数据类型家族 |
| TF32 / `tf32` | TensorFloat-32 数据格式 |
| FP8/FP6/FP4 | 分别使用约 8、6、4 位表示的低精度浮点格式家族 |
| INT8 / `i8` | 8 位整数数据类型 |
| MX | 显微缩放（microscaling），多组低精度数据共享局部缩放因子 |
| NVF4 | NVIDIA 定义的 4 位浮点格式 |
| 描述符（descriptor） | 描述数据地址、布局和解释方式的编码值 |
| `gdesc` | SASS 中的通用数据描述符操作数 |
| `idesc` | 指令描述符（instruction descriptor），描述 MMA 类型、形状等信息 |
| CTA | 协作线程块（Cooperative Thread Array），即 CUDA thread block |
| lane | 并行线程组中的一个执行位置 |
| guard | 控制一条指令是否执行的真假条件 |
| 谓词（predicate） | 保存真假值的条件寄存器 |
| 发射线程（issuer） | 实际发射一条指令的线程 |
| producer | 生成目标指令输入值的前序计算 |
| completion | 提交和确认异步操作完成的后继协议 |
| commit | 提交此前发出的异步操作 |
| mbarrier | 内存屏障（memory barrier），记录异步到达和完成状态 |
| 稀疏 / `.sp` | 稀疏矩阵形式 |
| 元数据（metadata） | 描述稀疏元素位置等附加信息的数据 |
| 权重驻留 / `.ws` | 让权重操作数保持并复用的计算模式 |
| 分块缩放（block scaling） | 一个数据块共享缩放因子 |
| 缩放向量（scale vector） | 描述缩放因子沿矩阵数据如何分组应用 |
| collector | 暂存并复用张量核心操作数的硬件机制 |
| GPR / `R` | 普通通用寄存器（General-Purpose Register） |
| UGPR / `UR` | 统一通用寄存器（Uniform General-Purpose Register） |
| PRED / `P` | 普通谓词寄存器 |
| UPRED / `UP` | 统一谓词寄存器（Uniform Predicate Register） |
| 活跃寄存器 | 当前保存有效值、以后还会被使用的寄存器 |
| spill | 寄存器不足时把值临时放到本地内存 |
| 别名（alias） | 两个操作数引用同一物理寄存器 |
| 编码（encoding） | 一条机器指令最终的二进制表示 |
| O0/O1/O2/O3 | 从少优化到高优化的四个编译优化级 |
| semantic form | 不含外围上下文的规范指令语义形态 |
| 源码变体（source variant） | 同一语义的不同 PTX 源码拼写 |
| 配置文件（profile） | 一组明确的实验上下文赋值 |
| occurrence | PTX 源码中一条实际出现的目标指令 |
| 归属配对（attribution） | 把 PTX 出现位置配对到对应 SASS 指令 |
| 规范化（normalization） | 消除地址和具体编号等噪声后再比较 |
| 哈希（SHA-256） | 根据文件内容计算的 256 位数字指纹 |
| 静态 | 编译期可观察，不代表已经在 GPU 上执行 |

## 附录 C：分析一条 `tcgen05.mma` 的推荐顺序

以后看到一条 `tcgen05.mma`，可以按以下顺序预测它的 SASS：

1. 看 `kind`，确定使用 `UTCHMMA`、`UTCQMMA`、`UTCIMMA` 还是 `UTCOMMA`。
2. 看 CTA group，决定是否添加 `.2CTA`。
3. 看是否 `.ws`，决定是否添加 `.WS`。
4. 看是否 `.ashift`，决定是否添加 `.ASHIFT`。
5. 看 A 来源，决定第一个源操作数是 `gdesc` 还是 `tmem`。
6. 看 collector，决定 `KEEP`、`REUSE` 和 `BUFFERn`。
7. 看 enable 和 guard，判断谓词是运行时寄存器、常量 `UPT`/`!UPT`，还是指令前的 `@UPn`。
8. 最后查看完整 kernel，判断发射线程、producer 和 completion 带来的外围序列。

这套顺序能够预测当前实验已经覆盖的核心映射，但不能替代对 `idesc` 位型和 Thor 实机运行结果的后续验证。
