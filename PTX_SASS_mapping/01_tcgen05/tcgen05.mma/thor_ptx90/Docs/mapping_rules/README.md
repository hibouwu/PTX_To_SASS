# `tcgen05.mma` PTX → SASS 映射规则索引

> 适用范围：PTX ISA 9.0、NVIDIA Thor、`sm_110a`
>
> 证据来源：`thor_ptx90/results/`
>
> 条目性质：静态编译和反汇编规则，不代表实机数值或性能结论

## 一句话结论

`tcgen05.mma` 的 PTX → SASS 映射不是“一条 PTX 字符串替换成一条 SASS
字符串”，而是两层规则：

1. `kind`、CTA group、variant、TS/SS、collector、block scaling 和
   `.ashift` 决定核心 MMA 的 opcode、modifier 和操作数形态。
2. guard、issuer、producer、enable 常量和 completion 决定谓词、寄存器分配
   以及核心指令前后的完整 lowering 序列。

**opcode** 是机器指令执行何种操作的编码字段；**modifier** 是附加在主指令或
操作数上的模式修饰；**lowering** 是编译器把 PTX 逐步变成具体 SASS 的过程。

## 按问题查文档

| 想回答的问题 | 文档 |
|---|---|
| `kind` 为什么变成不同 UT*C*MMA 家族？ | [`kind_and_opcode.md`](kind_and_opcode.md) |
| `.cta_group::2` 如何进入 SASS？ | [`cta_group.md`](cta_group.md) |
| `.ws`、`.sp`、`.ws.sp` 分别改变什么？ | [`variant.md`](variant.md) |
| TS/SS、TMEM/SMEM descriptor 如何对应？ | [`operand_source.md`](operand_source.md) |
| collector 的 fill/use/lastuse/discard 如何映射？ | [`collector.md`](collector.md) |
| block scaling 和 scale vector 如何体现？ | [`block_scaling.md`](block_scaling.md) |
| `.ashift` 如何映射，什么组合非法？ | [`ashift.md`](ashift.md) |
| 多个 modifier 同时存在时怎样解释？ | [`interactions.md`](interactions.md) |

完整函数级 PTX/SASS 对照、上下文和寄存器分析仍保留在
[`../tcgen05_mma_PTX到SASS映射规则报告.md`](../tcgen05_mma_PTX到SASS映射规则报告.md)。

## 核心规则速览

```text
kind
    → UTCHMMA / UTCQMMA / UTCIMMA / UTCOMMA

cta_group::2
    → .2CTA

mma.ws / mma.ws.sp
    → .WS

ashift
    → .ASHIFT

SS
    → gdesc(A), gdesc(B)

TS
    → tmem(A), gdesc(B)

collector
    → A_KEEP/A_REUSE 或 B_KEEP/B_REUSE/BUFFERn
```

这些确定性规则已经在 expanded 集合的 52,736 条目标 SASS occurrence 上检查，
当前样本中的反例数为 0。**occurrence** 指 PTX 中一条实际出现的目标指令。

## modifier 到 SASS 指令集合的选择

| PTX 维度 | 核心 SASS 选择 | 可能改变的外围指令集合 |
|---|---|---|
| 非 block kind | `UTCHMMA/UTCQMMA/UTCIMMA` | 无 |
| CTA group 2 | `UTC*MMA.2CTA`；completion 选 `UTCBAR.2CTA` | `MOV`、`R2UR`、`UMOV`、`LOP3.LUT` |
| `.sp` | 主 opcode 不加 `.SP`；metadata 进入 `tmem[...]` 操作数 | `LDCU.128`、`LDCU(.64)`、`UMOV`，或 `LDC`、`IADD3`、`MOV` |
| `.ws` | `UTC*MMA.WS`；选择 B collector | 取消普通 mask 路径中的 `MOV/R2UR/UMOV/LOP3` |
| zero-column-mask descriptor | `UTC*MMA.WS` 增加一个 UR 操作数 | `LDCU.64`，或 `LDC.64` + `MOV` |
| SS | A 选择 `gdesc[UR]` | `LDCU.64`，或 `LDC.64` + `MOV/R2UR` |
| TS | A 选择 `tmem[UR]` | `LDCU`，或 `LDC` + `IADD3` |
| collector | `.A/B_KEEP`、`.A/B_REUSE`、`.BUFFERn` | 无 |
| 启用 block scaling | 核心增加 `tmem[scale-factor]` 操作数 | `LDCU.64`，或 `LDC` + `IADD3`，必要时 `MOV/R2UR` |
| block 家族内的 `2X/4X` | `UTCOMMA` 或 `UTCOMMA.4X` | 无 |
| `.ashift` | `UTC*MMA.ASHIFT` | 无独立 shift 或其他外围指令 |

`UTC*MMA` 是本组文档对 `UTCHMMA/UTCQMMA/UTCIMMA/UTCOMMA` 的简写。外围
集合中的指令可以按作用分组：

- `LDCU/LDCU.64/LDCU.128`：把 kernel 参数或常量装入 uniform register；
- `LDC/LDC.64`：把参数或常量装入普通 GPR；
- `MOV/UMOV/R2UR`：在普通寄存器、uniform register 或立即数之间搬运；
- `IADD3`：为 derived producer 形成地址；
- `LOP3/PLOP3/ISETP/UISETP/BRA`：形成 mask、谓词或控制流；
- `UTCBAR/UTCBAR.2CTA`：完成或提交相关的 Tensor Core barrier；
- `NOP`：调度填充，不直接实现 modifier 语义。

详细配对数量和变化原因写在各维度文档中；联合判断见
[`interactions.md`](interactions.md)。

## 这些影响是怎样检查的

每组比较先在 PTX manifest 中找到合法配对，只改变待研究维度，其余 semantic
form、源码变体和上下文保持一致；CTA group、WS 和 block scaling 会连带改变
操作数契约，因此使用同一上下文 profile 下最接近的合法 counterpart。随后分别
比较 O0、O1、O2、O3：

1. 从完整函数反汇编统计 SASS 指令数量；
2. 去掉目标 MMA，比较外围指令的助记符及排列；
3. 从 attribution 比较核心 MMA 的操作数、寄存器编号和机器编码；
4. 从 liveness 结果比较核心位置的 GPR、PRED、UGPR、UPRED 活跃数量。

因此，文档中的“1,536 次比较”表示源码/上下文配对再乘以四个优化级，不表示
有 1,536 个互不相关的 semantic form。**counterpart** 是除待研究维度外尽可能
相同的合法对照；**liveness** 是某条指令位置仍保存有效值的寄存器集合。

各条目的主要代码示例统一使用 O0/O3：

- O0 展示尚未合并的 `LDC/MOV/IADD3/R2UR` 等 lowering 过程；
- O3 展示最终的 uniform load、核心操作数和寄存器布局；
- O1/O2 用于定位优化从哪一级开始稳定，只保留在统计证据中。

这里把 O0/O3 称为两个主要**观察点**；它们是两次独立编译的结果，不是编译器
内部 pass 的逐帧快照。

## 为什么还需要 `interactions.md`

modifier 并不都能彼此独立解释：

- `.sp` 没有生成同名 `.SP` SASS modifier；
- `.ashift` 只允许 A 来自 TMEM，且不能与 block scaling 组合；
- `.ws` 改变的是 B collector 的解释方式，并限制 CTA group 为 1；
- collector modifier 出现在操作数上，不一定出现在主 opcode 上；
- `scale_vec::2X` 和 `block32` 没有可见的同名 SASS 后缀；
- guard 和 issuer 可能只改变寄存器与外围序列，不改变核心助记符。

所以单个条目回答“这个维度通常映射到哪里”，综合报告和 interactions 条目回答
“多个维度同时存在时，最终怎样组合”。

## 如何理解证据等级

| 等级 | 含义 |
|---|---|
| 确定性规则 | 当前适用样本中零反例，并有单因素或结构性证据 |
| 条件规则 | 只在特定 variant、操作数来源或优化级成立 |
| 观察结果 | 数据中稳定出现，但尚不能归因到独立编码字段 |
| 未覆盖 | descriptor 位型或实机语义尚未冻结和运行 |

**单因素证据** 指比较时只改变一个实验维度。**descriptor** 是描述数据地址、
布局和解释方式的编码值，不是矩阵数据本身。

## 共同术语

- **PTX**：NVIDIA GPU 的虚拟指令集。
- **SASS**：具体 GPU 实际执行的机器指令。
- **MMA**：matrix multiply-accumulate，矩阵乘加。
- **Tensor Core**：GPU 中执行矩阵运算的专用硬件。
- **TMEM**：Tensor Memory，Tensor Core 使用的专用存储空间。
- **SMEM**：shared memory，一个 CTA 内共享的片上存储。
- **CTA**：Cooperative Thread Array，即 CUDA thread block。
- **semantic form**：不包含外围上下文的规范指令语义形态。
- **context**：guard、issuer、producer、completion 等外围条件。

各条目会继续解释本页没有覆盖的专有名词。

## 数据规模

| 数据层 | 数量 |
|---|---:|
| semantic form | 896 |
| syntax 源码实现 | 1,152 |
| expanded 源码实现 | 9,216 |
| expanded 目标 occurrence | 13,184 |
| 四优化级 SASS attribution | 52,736 |
| 上下文配对比较 | 32,256 |

**attribution** 指把 PTX occurrence 与对应的核心 SASS 指令配对。
