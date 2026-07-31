# `tcgen05.mma` 从 PTX 到 SASS 的映射规则

> 适用范围：NVIDIA Thor、PTX ISA 9.0、目标架构 `sm_110a`
>
> 工具环境：CUDA 13.0，`ptxas` V13.0.88，`nvdisasm` V13.0.85
>
> 报告性质：静态编译与反汇编结果，不包含 GPU 实机数值验证
>
> 数据来源：`thor_ptx90/results/` 中的生成清单、编译报告、SASS 归属记录和上下文差分摘要

> 查找单个 modifier 或语义维度时，先看
> [`mapping_rules/README.md`](mapping_rules/README.md)；本文保留跨维度解释、
> 完整 lowering 和函数级 PTX/SASS 对照。

## 先说结论

`tcgen05.mma` 从 PTX 编译成 SASS 后，可以分成两层理解：

1. **核心计算指令**主要由 PTX 中的计算类型、操作数来源、CTA（协作线程块）
   数量、weight-stationary（权重驻留）模式、block scaling（分块缩放）和
   collector（操作数收集器）状态决定。
2. **外围指令序列**主要由 guard、issuer、操作数生成方式和完成协议决定。

在本次 32,256 组配对比较中，外围上下文没有一次改变核心 MMA 的 SASS
指令家族。换句话说，`UTCHMMA`、`UTCQMMA`、`UTCIMMA` 或 `UTCOMMA`
选哪一个，取决于“做什么矩阵运算”，而不是取决于“由哪个线程发射”或
“后面如何完成同步”。

但“核心指令家族不变”不等于“生成的机器代码不变”。上下文仍然会改变：

- 核心指令使用的谓词；
- 物理寄存器编号和寄存器类别；
- 指令执行位置上的活跃寄存器数量；
- 核心指令前后的控制、准备和同步指令；
- 最终机器指令的编码。

因此，正确的心智模型不是“一条 PTX 固定翻译成一条完全固定的 SASS”，而是：

```text
PTX 语义形态
    决定核心 SASS 指令家族、modifier 和操作数形态

PTX 所处上下文
    决定谓词、寄存器分配和外围 lowering 序列
```

这里的 **lowering** 指编译器把较抽象的 PTX 指令逐步变成具体硬件指令的过程。
PTX 是 NVIDIA GPU 的虚拟指令集；SASS 是绑定具体 GPU 架构的机器指令。

## 1. 从一条 PTX 指令开始理解

下面是一条简化后的 PTX：

```ptx
tcgen05.mma.cta_group::2.kind::f16.ashift
    [%d_tmem], [%a_tmem], %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3,
     %mask4, %mask5, %mask6, %mask7},
    %enable;
```

可以把它拆成以下部分：

| 部分 | 白话解释 |
|---|---|
| `tcgen05.mma` | 执行一次第五代 Tensor Core 矩阵乘加 |
| `.cta_group::2` | 两个 CTA 共同参与 |
| `.kind::f16` | 使用以 FP16 为代表的运算家族 |
| `.ashift` | 使用 TMEM A 操作数时，对 A 的行位置做硬件支持的移位 |
| `[%d_tmem]` | 结果 D 位于 Tensor Memory |
| `[%a_tmem]` | 输入矩阵 A 位于 Tensor Memory |
| `%desc_b` | 输入矩阵 B 由 shared-memory descriptor 描述 |
| `%idesc` | instruction descriptor，描述形状和精确数据类型等信息 |
| `%mask0...%mask7` | 指定哪些输出 lane 被禁用 |
| `%enable` | 决定本次运算是否把旧的 D 累加进去 |

其中：

- **Tensor Core** 是 GPU 中专门执行矩阵乘加的计算单元。
- **MMA** 是 matrix multiply-accumulate，即矩阵乘法并累加。
- **TMEM** 是 Tensor Memory，供新一代 Tensor Core 指令使用的专用存储空间。
- **shared memory** 是一个 CTA 内线程共享的片上存储空间，本文简称 SMEM。
- **descriptor** 是描述一块数据如何存放和解释的编码值，不是数据本身。
- **lane** 是一组并行线程中的一个执行位置。

这条 PTX 在当前实验条件下会产生类似下面的核心 SASS：

```text
UTCHMMA.2CTA.ASHIFT
    tmem[UR7], gdesc[UR8], tmem[UR6],
    tmem[UR4], idesc[UR5], UP0
```

SASS 中：

- `UTCHMMA` 是实际触发 Tensor Core MMA 的机器指令。
- `.2CTA` 表示两个 CTA 参与。
- `.ASHIFT` 对应 PTX 的 `.ashift`。
- `tmem[...]` 表示 TMEM 操作数。
- `gdesc[...]` 表示由通用 descriptor 描述的操作数。
- `idesc[...]` 表示 instruction descriptor。
- `UR7` 之类的名字是 uniform register，即同一执行组共享值的物理寄存器。
- `UP0` 是 uniform predicate register，即 uniform 形式的真假条件寄存器。

## 2. 核心 SASS 指令家族如何选择

### 2.1 `kind` 决定哪一种 MMA 指令家族

PTX 的 `kind` 给出运算所属的数据类型家族。当前结果得到以下稳定映射：

| PTX `kind` | 核心 SASS | 含义 |
|---|---|---|
| `f16` | `UTCHMMA` | FP16 类浮点矩阵运算 |
| `tf32` | `UTCHMMA` | TF32 类浮点矩阵运算 |
| `f8f6f4` | `UTCQMMA` | FP8/FP6/FP4 混合低精度矩阵运算 |
| `mxf8f6f4` | `UTCQMMA` | 带块缩放的 FP8/FP6/FP4 运算 |
| `i8` | `UTCIMMA` | INT8 整数矩阵运算 |
| `mxf4` | `UTCOMMA` | 带块缩放的 MXF4 运算 |
| `mxf4nvf4` | `UTCOMMA` | MXF4 与 NVF4 家族运算 |

这里的 **指令家族** 指共享一个主 opcode 的机器指令集合。**opcode** 是机器
指令中表示“要执行什么操作”的字段。`UTCHMMA` 等名字是反汇编器显示出来的
**助记符**，即便于人阅读的 opcode 名称。

这条规则描述的是家族选择，不代表 `f16` 和 `tf32` 的完整机器编码相同。
更精确的类型、矩阵形状、major 方向等信息还可能存放在 `idesc` 中。

### 2.2 CTA group 决定是否出现 `.2CTA`

**CTA** 是 Cooperative Thread Array，即 CUDA 中的 thread block。

| PTX | SASS |
|---|---|
| `.cta_group::1` | 不增加 CTA 数量 modifier |
| `.cta_group::2` | 增加 `.2CTA` |

例如：

```text
tcgen05.mma.cta_group::1.kind::f16
→ UTCHMMA

tcgen05.mma.cta_group::2.kind::f16
→ UTCHMMA.2CTA
```

**modifier** 是附加在主助记符或操作数后面的修饰字段，用来表达 CTA 数量、
操作模式、复用状态等信息。

### 2.3 weight-stationary 决定 `.WS`

PTX 的 `.ws` 表示 **weight-stationary** 模式，即让作为“权重”的 B 操作数在
硬件内部保持和复用，减少重复读取。

| PTX variant | SASS |
|---|---|
| `mma` | 普通 MMA 助记符 |
| `mma.sp` | 普通 MMA 助记符，稀疏信息进入操作数或编码 |
| `mma.ws` | 增加 `.WS` |
| `mma.ws.sp` | 增加 `.WS`，稀疏信息进入操作数或编码 |

**variant** 指同一基础指令的语义变体。`.sp` 表示 sparse，即稀疏矩阵形式。
稀疏形式额外需要 **metadata**，也就是描述哪些元素存在的元数据。

一个重要发现是：`.sp` 没有直接变成可见的 `.SP` SASS modifier。因此不能只看
SASS 助记符判断一条指令是不是稀疏 MMA，还必须看操作数位置和机器编码。

### 2.4 `.ashift` 直接映射为 `.ASHIFT`

`.ashift` 只适用于 A 来自 TMEM 的合法形态：

```text
PTX .ashift
→ SASS .ASHIFT
```

例如：

```text
UTCQMMA.2CTA
→ UTCQMMA.2CTA.ASHIFT
```

本实验的阴性用例也验证了两个非法边界：

- A 来自 SMEM descriptor 时使用 `.ashift`，`ptxas` 会拒绝；
- block-scaled MMA 使用 `.ashift`，`ptxas` 会拒绝。

**阴性用例** 指实验者有意构造的非法输入，用来确认工具确实拒绝错误组合。

## 3. TS 和 SS：A、B 从哪里取数

本文使用两个字母描述 A、B 操作数来源：

- `T` 表示 Tensor Memory；
- `S` 表示 shared memory descriptor。

`tcgen05.mma` 当前存在两种来源模式：

| 模式 | A 来源 | B 来源 | SASS 前两个源操作数 |
|---|---|---|---|
| SS | SMEM descriptor | SMEM descriptor | `gdesc[...]`, `gdesc[...]` |
| TS | TMEM address | SMEM descriptor | `tmem[...]`, `gdesc[...]` |

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
|---|---:|---:|---:|
| SS | 432 | 552 | 4,416 |
| TS | 464 | 600 | 4,800 |

这里：

- **semantic form** 是去掉 guard、producer 等上下文后，真正描述指令语义形态
  的规范记录。
- **源码实现** 是实际生成的一份 PTX kernel 写法。不同写法可能表达同一个
  semantic form。
- **syntax 集合** 是受约束语法矩阵。
- **expanded 集合** 是语法矩阵再与多个静态上下文组合后的扩展矩阵。

TS 的实现数更多，因为只有 TS 能合法组合 `.ashift`。

## 4. block scaling 和 scale vector 如何映射

**block scaling** 指一个数据块共享缩放因子，以支持更低精度的数据表示。
**scale vector** 描述缩放因子沿矩阵数据如何成组应用。

本实验观察到：

| PTX 规范语义 | 可见 SASS 结果 |
|---|---|
| `scale_vec::1X` | `UTCQMMA` 家族 |
| `scale_vec::2X` | `UTCOMMA` 家族，没有独立 `.2X` 文本 |
| `scale_vec::4X` | `UTCOMMA.4X` |
| `block16` 规范别名 | `UTCOMMA.4X` |
| `block32` 规范别名 | `UTCOMMA`，没有独立 `.BLOCK32` 文本 |

“没有独立文本”不等于信息被编译器丢弃。它可能已经由 opcode 家族、`idesc`
或机器编码共同表达。这里只能说反汇编文本中看不到一对一的同名 modifier。

## 5. collector 如何映射

**collector** 是 Tensor Core 操作数收集和复用机制。它允许硬件暂存 A 或 B，
让后续 MMA 重用已经收集的操作数。

collector 的四个动作可以这样理解：

| 动作 | 白话解释 |
|---|---|
| `fill` | 装入 collector，并保留给后续使用 |
| `use` | 使用已装入的值，使用后仍保留 |
| `lastuse` | 最后一次使用，之后可以释放 |
| `discard` | 本次使用后不保留 |

### 5.1 A collector

| PTX collector | SASS A 操作数 modifier |
|---|---|
| `a::discard` | 无 A modifier |
| `a::fill` | `.A_KEEP` |
| `a::use` | `.A_REUSE.A_KEEP` |
| `a::lastuse` | `.A_REUSE` |

其中：

- `KEEP` 表示使用后继续保留；
- `REUSE` 表示使用已经收集的值。

例如：

```text
.collector::a::fill
→ gdesc[UR8].A_KEEP

.collector::a::use
→ gdesc[UR8].A_REUSE.A_KEEP

.collector::a::lastuse
→ gdesc[UR8].A_REUSE
```

### 5.2 B collector

B collector 用于 weight-stationary 形式：

| PTX collector | SASS B 操作数 modifier |
|---|---|
| `bN::discard` | 无 `B_KEEP` 或 `B_REUSE` |
| `bN::fill` | `.B_KEEP` |
| `bN::use` | `.B_REUSE.B_KEEP` |
| `bN::lastuse` | `.B_REUSE` |

`N` 是 buffer 编号：

| PTX buffer | SASS |
|---|---|
| `b0` | 默认 buffer，不显示编号 |
| `b1` | `.BUFFER1` |
| `b2` | `.BUFFER2` |
| `b3` | `.BUFFER3` |

例如：

```text
.collector::b2::use
→ gdesc[UR10].B_REUSE.B_KEEP.BUFFER2
```

## 6. 上下文如何改变 lowering

**上下文** 指目标 PTX 指令之外、但可能影响编译结果的信息，例如 guard、
操作数由常量还是计算产生、由哪个 lane 发射，以及指令之后是否增加完成协议。

本实验以 `runtime_zero` 为基线。**基线** 是所有处理组都要与之比较的参考写法。
每组实验保持 semantic form 和 source variant 一致，只改变一个上下文 profile。

**profile** 是一组明确的上下文赋值。**配对比较** 指把同一个设计在基线和处理
profile 下的结果一一对齐比较。

### 6.1 enable 决定是否累加旧 D

`enable-input-d` 是一个谓词：

- true：执行 `D = A × B + D`；
- false：执行 `D = A × B`，不读取旧 D。

**谓词** 是一个真假条件，用于控制指令是否执行或选择某种行为。

在 O1、O2、O3 下，编译器会把已知常量折叠进核心 SASS。例如：

```text
运行时 enable:
..., UP0

静态 false:
..., !UPT
```

`UPT` 是恒真的 uniform predicate；`!UPT` 是对它取反，因此恒假。
这种把运行时表达式替换为编译期常量的行为叫 **常量折叠**。

在 O0 下，核心 SASS 没有进行这种折叠。`O0` 到 `O3` 是编译优化级：

- `O0`：尽量少优化，便于观察原始 lowering；
- `O1`：启用基础优化；
- `O2`：启用更完整的优化；
- `O3`：最高常用优化级。

在当前微型 kernel 中，O2 和 O3 的全部 13,184 个目标 occurrence，其核心
操作文本、编码和活跃寄存器计数完全相同。

**occurrence** 指 PTX 源码中一条实际出现的目标指令。有些 collector 测试会在
一个 kernel 中连续出现多条 `tcgen05.mma`，所以 occurrence 数大于 kernel 数。

### 6.2 guard 有两种 lowering 方式

**guard** 是写在 PTX 指令前的执行条件，例如：

```ptx
@%p tcgen05.mma ...
```

它可能直接成为 SASS 指令前的谓词：

```text
@UP1 UTCHMMA ...
```

也可能由外围控制指令处理，使核心 MMA 文本不出现显式 guard。

O2/O3 的 1,152 组 guard 比较中：

- 352 组改变了核心规范操作；
- 508 组改变了核心寄存器布局；
- 496 组改变了核心位置的活跃寄存器数量。

正 guard 和负 guard 的变化数量相同，说明 guard 的真假极性会改变具体条件，
但没有改变编译器采用哪类 lowering 路径的覆盖范围。

### 6.3 lane-0 issuer 主要改变寄存器压力

**issuer** 是实际发射 MMA 指令的线程。`lane0_issuer` profile 限制 lane 0
成为发射者。

在 O1/O2/O3 下：

- 核心规范操作变化为 0；
- 1,152/1,152 组核心活跃寄存器数发生变化；
- 168 组核心物理寄存器发生纯重编号，全部来自稀疏 `.sp` 变体。

这说明只比较 opcode 会漏掉 issuer 对资源使用的影响。

### 6.4 derived producer 在优化后被消除

**producer** 是产生目标指令输入值的前序计算。`derived_producers` profile
通过额外计算得到 descriptor、地址或谓词，而不是直接使用参数。

结果是：

- O0 的完整 kernel 序列发生变化；
- O1/O2/O3 的完整规范化 kernel 序列完全不变。

这说明这些额外 producer 在 O1 以上被编译器吸收或消除。

### 6.5 completion 改变后继协议，不改变核心 MMA

**completion** 是 MMA 发出后如何确认完成的协议，例如 commit 和 mbarrier。

- **commit** 表示提交此前发出的异步 Tensor Core 操作；
- **mbarrier** 是 memory barrier，一种记录异步工作到达和完成状态的同步对象。

`commit_completion` 在所有优化级都会改变完整 kernel 序列和指令数，但不会
改变核心 MMA 助记符、核心操作数或核心寄存器布局。因此 completion 应当建模为
MMA 的后继协议，而不是 MMA opcode 的组成部分。

## 7. 如何理解寄存器变化

SASS 使用真实物理寄存器。本文涉及四类寄存器：

| 名称 | SASS 写法 | 用途 |
|---|---|---|
| GPR | `R0`、`R1`…… | 普通线程私有数据 |
| UGPR | `UR0`、`UR1`…… | uniform 数据 |
| PRED | `P0`、`P1`…… | 普通真假条件 |
| UPRED | `UP0`、`UP1`…… | uniform 真假条件 |

**uniform** 表示同一执行组中的线程共享相同值。

报告把寄存器变化分成三类：

1. **仅重编号**：例如 `UR4 → UR7`，类别和复用关系不变。
2. **类别变化**：例如 `UP0 → UPT`，从可写谓词变成特殊恒真谓词。
3. **别名关系变化**：原本两个操作数引用同一个寄存器，后来变成不同寄存器，
   或反过来。

这里的 **别名** 指两个操作数是否指向同一个物理寄存器。

32,256 组上下文比较的结果是：

| 现象 | 数量 | 比例 |
|---|---:|---:|
| 核心寄存器布局变化 | 10,344 | 32.1% |
| 其中仅重编号 | 1,320 | 4.1% |
| 寄存器类别变化 | 9,024 | 28.0% |
| 别名关系变化 | 9,024 | 28.0% |
| 核心位置活跃数变化 | 15,488 | 48.0% |
| kernel 峰值活跃数变化 | 17,592 | 54.5% |

**活跃寄存器** 指在某条指令位置之前已经保存了值、并且之后还可能被使用的
寄存器。活跃寄存器越多，寄存器压力通常越大。

**kernel 峰值活跃数** 是整个 kernel 中同时活跃寄存器数量的最大值。
kernel 是由 CPU 启动、在 GPU 上执行的一段函数。

在 O1/O2/O3 的 baseline 中，核心 MMA 位置的平均活跃寄存器为：

| 模式 | GPR | PRED | UGPR | UPRED |
|---|---:|---:|---:|---:|
| SS | 1 | 2 | 8.21，最大 9 | 1 |
| TS | 1 | 2 | 7.12，最大 8 | 1 |

SS 比 TS 平均多约一个活跃 UGPR，说明 shared-memory A descriptor 比 TMEM A
地址需要更多 uniform 状态。

本次上下文比较没有发现 `LDL`/`STL` 本地内存指令数量变化。
`LDL` 和 `STL` 是读写 thread-local memory 的 SASS 指令，常被用作寄存器
**spill** 的线索。spill 指物理寄存器不足时，编译器暂时把值放到本地内存。
不过，仅凭 `LDL`/`STL` 仍不能断言一定发生了 spill。

## 8. 核心指令和完整 lowering 必须分开看

本次比较得到：

| 比较对象 | 发生变化的配对 |
|---|---:|
| 核心 MMA 助记符 | 0 / 32,256 |
| 核心规范操作 | 9,024 / 32,256 |
| 完整 kernel 规范序列 | 28,800 / 32,256 |
| kernel 指令数 | 17,396 / 32,256 |

**规范操作** 是把具体寄存器编号和指令地址消除后得到的可比较形式。例如
`UR4` 和 `UR9` 都会抽象成“第一个 UGPR”，但 R、UR、P、UP 的类别不会混合。
这个过程叫 **规范化**。

因此：

- 判断“执行哪一种 Tensor Core 运算”，看核心助记符和核心 modifier；
- 判断“PTX 在这个上下文中怎样实现”，看完整 kernel；
- 判断“资源使用是否改变”，看具体寄存器、活跃数和本地内存指令；
- 判断“机器码是否完全相同”，必须比较完整指令编码，不能只看文本。

## 9. 可以写成规则的内容

根据当前证据，可以把规则分成三档。

### A. 当前样本中零反例的确定性规则

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
    → KEEP/REUSE modifier 组合
```

### B. 必须带条件的上下文规则

```text
已知 enable 常量 + O1 以上
    → enable predicate 被折叠为 UPT 或 !UPT

guard
    → 直接 SASS predication 或外围控制路径

lane0 issuer
    → 核心 opcode 通常不变，但活跃寄存器改变

derived producer + O1 以上
    → 当前测试中的额外 producer 被优化消除

completion
    → 改变后继序列，不改变核心 MMA
```

**predication** 指在一条机器指令上直接附加真假执行条件，而不是单独跳转。

### C. 当前还不能写成确定规则的内容

以下内容尚未被实验逐字段冻结：

- `idesc` 中 M、N、K 的精确矩阵形状；
- A、B、D 的精确数据类型组合；
- row-major/column-major 等 major 方向；
- SMEM descriptor 的 stride 和 swizzle；
- 每个 PTX 字段对应的精确机器编码 bit。

其中：

- **M、N、K** 是矩阵乘法 `M×K` 乘以 `K×N` 的三个尺寸；
- **major** 指数据以行还是以列为主要连续方向；
- **stride** 是相邻行或列在地址上的距离；
- **swizzle** 是为了改善存储访问分布而进行的地址重排；
- **bit** 是二进制编码中的一个 0 或 1 位。

当前用例把这些 descriptor 当作运行时参数，所以可以证明 `ptxas` 接受语法并
生成 SASS，但不能反推出 descriptor 内每个字段的独立映射。

## 10. 这份报告证明了什么，又没有证明什么

已经证明：

- 当前受约束合法语法矩阵可以被 CUDA 13.0 `ptxas` 接受；
- 每条目标 PTX occurrence 都能归属到一条核心 MMA SASS；
- 上述 kind、CTA group、TS/SS、WS、ASHIFT 和 collector 映射在当前样本中稳定；
- 上下文对核心操作、寄存器和完整 kernel 的影响可以被配对测量；
- 协议层的 42 个静态用例在 O0/O1/O2/O3 全部通过编译；
- 三个已知非法组合得到预期拒绝。

尚未证明：

- 这些 raw descriptor 在 Thor 实机上代表合法矩阵布局；
- 运算得到正确数值；
- `.cta_group::2` 的两个 CTA 在真实 cluster launch 中正确协作；
- 哪种写法性能更好；
- 所有可能的 descriptor 位型都已覆盖。

**静态编译** 只说明工具链能生成目标机器码。**实机语义验证** 还需要合法
descriptor、真实 TMEM allocation、输入数据、结果对照和同步检查。

## 11. 实验规模和证据来源

| 层次 | 结果 |
|---|---:|
| syntax 源码实现 | 1,152 |
| semantic form | 896 |
| expanded 源码实现 | 9,216 |
| expanded logical design | 7,168 |
| syntax 编译 | 72 / 72 PASS |
| expanded 编译 | 576 / 576 PASS |
| SASS case attribution | 36,864 / 36,864 COMPLETE |
| SASS target occurrence | 52,736 |
| 上下文配对比较 | 32,256 / 32,256 COMPLETE |
| 协议层编译 | 168 / 168 PASS |
| effect-slice SASS 检查 | 32 / 32 PASS |
| 阴性探针 | 3 / 3 PASS |

**logical design** 是 semantic form 与适用静态上下文组合后的逻辑实验点。
**attribution** 是把 PTX 中的目标 occurrence 与 SASS 中对应核心指令配对。
**shard** 是为了避免单个 PTX 文件过大而切分出的源码分片。

主要机器可读来源：

- `results/expanded/sources/manifest.jsonl`：每条源码实现的实验坐标；
- `results/expanded/sass/sass_attribution.jsonl`：PTX 与核心 SASS 的配对；
- `results/context-comparison/context_summary.csv`：上下文差分汇总；
- `results/context-comparison/comparison_report.json`：输入与输出哈希；
- `results/protocol-layers/compile_report.json`：协议层验证；
- `results/negative-probes/negative_probe_report.json`：非法组合诊断。

**JSONL** 是每行一个 JSON 对象的文本格式，适合保存大量逐条记录。
**CSV** 是逗号分隔表格格式。**哈希** 是文件内容的数字指纹，用于确认文件
没有被意外修改。

## 附录 A：三个完整 PTX → SASS 对照例子

下面三个例子均来自本实验的 syntax 集合，PTX 版本为 9.0，目标为
`sm_110a`，SASS 由对应 cubin 使用 `nvdisasm` 反汇编得到。展示的是 O3
完整函数，而不只是核心 MMA 一行。

为了读懂完整 SASS，先认识外围指令：

| SASS 内容 | 作用 |
|---|---|
| `.section/.global/.type/.size/.other` | 函数在二进制文件中的元数据，不是实际执行的指令 |
| `LDC` | 从 constant memory 装入普通寄存器 |
| `LDCU` | 从 constant memory 装入 uniform 寄存器 |
| `UISETP` | 比较 uniform 整数并生成 uniform predicate |
| `UMOV` | 在 uniform 寄存器之间移动或构造值 |
| `PLOP3.LUT` | 用查找表执行谓词布尔运算 |
| `ELECT` | 从参与线程中选出负责当前发射路径的线程 |
| `BRA.U.ANY` | 根据 uniform-any 条件跳转 |
| `EXIT` | 结束 kernel |
| 末尾 `BRA` 和 `NOP` | 函数结束路径以及用于代码对齐的填充 |

**constant memory** 是 GPU 的只读常量地址空间。kernel 参数会由驱动放入其中，
SASS 使用 `c[0x0][偏移]` 读取。**布尔运算** 是对真/假值进行与、或、非等操作。
**LUT** 是 lookup table，即查找表。**代码对齐** 是让函数或指令从硬件要求的
地址边界开始。

反汇编左侧的 `/*00a0*/` 是指令在函数中的十六进制字节偏移，不是 PTX 行号。
`.L_x_*` 是编译器生成的跳转标签。`@P0` 表示只有谓词 `P0` 为真时才执行该条
SASS。`NOP` 是 no operation，即不执行实际工作。`.section` 后的 `"ax"` 表示
这段内容可被加载并执行，`@progbits` 表示 section 中保存实际程序字节。
`STO_CUDA_ENTRY` 等 `.other` 内容是 ELF 二进制中的 CUDA 符号属性，不参与
MMA 计算；**ELF** 是 cubin 使用的一种可执行文件组织格式。

### A.1 SS、CTA group 1、普通 FP16 MMA

这个例子展示 A、B 都使用 SMEM descriptor 的 SS 模式。

| 证据字段 | 值 |
|---|---|
| case | `THOR_MMA_000001` |
| PTX shard | `thor_tcgen05_mma_0000.ptx` |
| kernel | `thor_tcgen05_mma_000001` |
| O3 核心 SASS offset | `0x00a0` |

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

这里的公共测试模板声明了 metadata、scale、guard 和 mbarrier 等参数，即使这个
具体 case 没有使用其中一部分。`ld.param` 是 PTX 的参数装载指令，`.u32/.u64`
表示 32/64 位无符号整数，`.b32/.b64` 表示只关心位宽的 32/64 位寄存器类型。
`.visible .entry` 声明一个可从外部启动的 GPU kernel 入口，`.param` 声明
kernel 参数，`.reg` 声明 PTX 虚拟寄存器，`.pred` 表示谓词类型。`setp.ne`
比较两个值是否不相等并生成谓词，`mov` 移动或构造值，`ret` 从 kernel 返回。

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

1. `LDC/LDCU` 从 kernel 参数区装入 D 地址、A/B descriptor、`idesc` 和 enable。
2. `UISETP` 把 32 位 enable 值转换为 `UP0` 谓词。
3. `UMOV UR4, URZ` 构造值为零的输出 mask。
4. `ELECT` 和 `BRA.U.ANY` 维护 single-thread issue 所需的选举循环。
5. `UTCHMMA` 的前两个源操作数都是 `gdesc`，直接体现 SS。

**single-thread issue** 表示一组参与线程中只有被选出的线程实际发射核心指令。
`RZ/URZ` 是恒为零的普通/uniform 特殊寄存器，`PT/UPT` 是恒真的普通/uniform
谓词。`NE` 表示 not equal（不相等），`U32` 表示无符号 32 位整数，`AND`
表示逻辑与。`PLOP3.LUT` 末尾的立即数指定具体布尔真值表；**立即数** 是直接
写在指令里的常量。

### A.2 TS、CTA group 2、ASHIFT

这个例子同时展示 TS、两个 CTA 和 A 行移位。

| 证据字段 | 值 |
|---|---|
| case | `THOR_MMA_000078` |
| PTX shard | `thor_tcgen05_mma_0001.ptx` |
| kernel | `thor_tcgen05_mma_000078` |
| O3 核心 SASS offset | `0x0090` |

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

这一例中最重要的一行是：

```text
UTCHMMA.2CTA.ASHIFT tmem[...], gdesc[...], ...
```

它同时验证：

- `kind::f16 → UTCHMMA`；
- `cta_group::2 → .2CTA`；
- `.ashift → .ASHIFT`；
- TS 的 A 操作数是 `tmem`，B 操作数是 `gdesc`。

### A.3 WS、B2 collector 的 fill → use

这个例子有两个目标 occurrence：第一条填充 B2 collector，第二条复用并继续保留。

| 证据字段 | 值 |
|---|---|
| case | `THOR_MMA_000620` |
| PTX shard | `thor_tcgen05_mma_0009.ptx` |
| kernel | `thor_tcgen05_mma_000620` |
| O3 核心 SASS offset | `0x00a0`、`0x0100` |

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
    /*0170*/ NOP;
    /*0180*/ NOP;
    /*0190*/ NOP;
    /*01a0*/ NOP;
    /*01b0*/ NOP;
    /*01c0*/ NOP;
    /*01d0*/ NOP;
    /*01e0*/ NOP;
    /*01f0*/ NOP;
.L_x_176:
```

两条核心指令正好体现 collector 状态转换：

```text
fill → .B_KEEP.BUFFER2
use  → .B_REUSE.B_KEEP.BUFFER2
```

`fill` 只负责装入并保留，所以出现 `B_KEEP`；下一条 `use` 使用已经装入的值，
所以同时出现 `B_REUSE`，并因为之后仍要保留而继续带有 `B_KEEP`。

这三个函数也说明“完整 lowering”为什么不能只数核心 MMA：每条 MMA 周围都有
参数装载、谓词生成、线程选举和控制循环。核心数值运算仍由一条
`UTCHMMA*` 完成，但整个 PTX kernel 会对应多条 SASS。

## 12. 术语速查

| 术语 | 解释 |
|---|---|
| GPU | Graphics Processing Unit，并行计算处理器 |
| CPU | Central Processing Unit，负责启动 GPU kernel 的主处理器 |
| NVIDIA Thor | 本实验面向的 NVIDIA GPU 家族 |
| compute capability | NVIDIA 表示 GPU 指令和功能代际的版本号 |
| `sm_110a` | Thor 架构专用的 PTX 编译目标 |
| CUDA Toolkit | NVIDIA 提供的 GPU 编译器、库和开发工具集合 |
| CUDA | NVIDIA 的 GPU 并行计算平台和编程模型 |
| PTX | GPU 虚拟指令集，尚未绑定具体机器编码 |
| PTX ISA | PTX Instruction Set Architecture，即 PTX 指令集规范 |
| SASS | GPU 实际执行的、与架构绑定的机器指令 |
| `ptxas` | 把 PTX 编译成目标 GPU 机器码的汇编器 |
| `nvdisasm` | 把 GPU 机器码反汇编成人可读 SASS 的工具 |
| cubin | 保存已编译 GPU 二进制代码的文件 |
| kernel | 由 CPU 启动、在 GPU 上执行的函数 |
| lowering | 从抽象指令逐步变成具体机器指令的编译过程 |
| opcode | 表示机器指令执行什么操作的编码字段 |
| 助记符 | opcode 的人类可读名称，如 `UTCHMMA` |
| modifier | 对主指令或操作数追加的模式修饰 |
| operand | 指令读取或写入的值，即操作数 |
| MMA | matrix multiply-accumulate，矩阵乘加 |
| A、B、D | MMA 中的两个输入矩阵 A、B 和输出/累加矩阵 D |
| Tensor Core | GPU 中专门执行矩阵运算的硬件单元 |
| TMEM | Tensor Memory，Tensor Core 使用的专用存储空间 |
| SMEM | shared memory，一个 CTA 内共享的片上存储 |
| FP16 / `f16` | 16 位浮点数据类型家族 |
| TF32 / `tf32` | NVIDIA Tensor Core 使用的 TensorFloat-32 数据格式 |
| FP8/FP6/FP4 | 分别使用约 8、6、4 位表示的低精度浮点格式家族 |
| INT8 / `i8` | 8 位整数数据类型 |
| MX | microscaling，多组低精度数据共享局部缩放因子的格式体系 |
| NVF4 | NVIDIA 定义的 4 位浮点格式 |
| descriptor | 描述数据地址、布局和解释方式的编码值 |
| `gdesc` | SASS 中的通用数据 descriptor 操作数 |
| `idesc` | 描述 MMA 类型、形状等信息的 instruction descriptor |
| CTA | Cooperative Thread Array，即 CUDA thread block |
| lane | 并行线程组中的一个执行位置 |
| guard | 控制一条指令是否执行的真假条件 |
| predicate | 保存真假值的条件寄存器 |
| issuer | 实际发射一条指令的线程 |
| producer | 生成目标指令输入值的前序计算 |
| completion | 提交和确认异步操作完成的后继协议 |
| commit | 提交此前发出的异步操作 |
| mbarrier | 记录异步到达和完成状态的内存屏障 |
| sparse / `.sp` | 稀疏矩阵形式 |
| metadata | 描述稀疏元素位置等附加信息的数据 |
| weight-stationary / `.ws` | 让权重操作数保持并复用的计算模式 |
| block scaling | 一个数据块共享缩放因子的低精度表示方式 |
| scale vector | 描述缩放因子沿矩阵数据如何分组应用 |
| collector | 暂存并复用 Tensor Core 操作数的硬件机制 |
| GPR / `R` | 普通线程私有通用寄存器 |
| UGPR / `UR` | 保存 uniform 值的通用寄存器 |
| PRED / `P` | 普通谓词寄存器 |
| UPRED / `UP` | uniform 谓词寄存器 |
| uniform | 同一执行组中的线程共享相同值 |
| 活跃寄存器 | 当前保存有效值、以后还会被使用的寄存器 |
| 寄存器压力 | 同时需要保留的寄存器数量带来的资源压力 |
| spill | 寄存器不足时把值临时放到本地内存 |
| alias | 两个操作数引用同一物理寄存器 |
| encoding | 一条机器指令最终的二进制表示 |
| bit | 二进制编码中的一个 0 或 1 |
| O0/O1/O2/O3 | 从少优化到高优化的四个编译优化级 |
| semantic form | 不含外围上下文的规范指令语义形态 |
| source variant | 同一语义的不同 PTX 源码拼写 |
| profile | 一组明确的实验上下文赋值 |
| `runtime_zero` | 本实验基线：无 guard/完成协议，直接使用参数，输出禁用 mask 为零，enable 保持运行时输入 |
| static context | 编译时已知、可能影响 lowering 的外围条件 |
| baseline | 与其他处理组比较的参考用例 |
| occurrence | PTX 源码中一条实际出现的目标指令 |
| attribution | 把 PTX occurrence 配对到对应 SASS 指令 |
| normalization | 消除地址和具体编号等噪声后再比较 |
| JSON | 使用键和值表达结构化数据的文本格式 |
| JSONL | 每行保存一个 JSON 对象的大规模记录格式 |
| CSV | 使用逗号分隔字段的表格文本格式 |
| SHA-256 | 根据文件内容计算的 256 位哈希，用于校验文件身份 |
| PASS / COMPLETE | 分别表示检查通过和结构化处理完整 |
| static | 编译期可观察，不代表已经在 GPU 上执行 |
| runtime | 程序在真实 GPU 上运行的阶段 |

## 最后的阅读原则

以后看到一条 `tcgen05.mma`，可以按以下顺序预测它的 SASS：

1. 看 `kind`，确定 `UTCHMMA`、`UTCQMMA`、`UTCIMMA` 或 `UTCOMMA`。
2. 看 CTA group，决定是否添加 `.2CTA`。
3. 看是否 `.ws`，决定是否添加 `.WS`。
4. 看是否 `.ashift`，决定是否添加 `.ASHIFT`。
5. 看 A 来源，决定第一个源操作数是 `gdesc` 还是 `tmem`。
6. 看 collector，决定 `KEEP`、`REUSE` 和 `BUFFERn`。
7. 看 enable 和 guard，判断谓词是运行时寄存器、常量 `UPT/!UPT`，
   还是指令前的 `@UPn`。
8. 最后查看完整 kernel，判断 issuer、producer 和 completion 带来的外围序列。

这套顺序能够预测当前实验已经覆盖的核心映射，但不能替代对 `idesc` 位型和
Thor 实机运行结果的后续验证。
