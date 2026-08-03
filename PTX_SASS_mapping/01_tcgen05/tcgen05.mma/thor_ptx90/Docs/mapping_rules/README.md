# `tcgen05.mma` PTX → SASS 映射规则索引

> 适用范围：PTX ISA 9.0、NVIDIA Thor 架构、编译目标 `sm_110a`
>
> 证据来源：`thor_ptx90/results/` 目录下的编译报告和归属记录
>
> 条目性质：基于静态编译和反汇编结果的规则总结

## `tcgen05.mma` 如何从 PTX 编译到 SASS

`tcgen05.mma` 的 PTX → SASS 映射由两层规则构成：

1. `kind`、CTA group、变体（variant）、TS/SS、collector、分块缩放（block scaling）和 `.ashift` 决定核心 MMA 指令的操作码（opcode）、修饰符（modifier）和操作数形态。
2. guard、发射线程（issuer）、producer、enable 常量和 completion 决定谓词、寄存器分配以及核心指令前后的完整编译降级（lowering）序列。

操作码是机器指令执行何种操作的编码字段。修饰符是附加在主指令或操作数上的模式修饰。编译降级是编译器把 PTX 逐步变成具体 SASS 的过程。

## 按问题查文档

| 问题 | 文档 |
|---|---|
| `kind` 如何决定 SASS 指令家族？ | [`kind_and_opcode.md`](kind_and_opcode.md) |
| `.cta_group::2` 如何进入 SASS？ | [`cta_group.md`](cta_group.md) |
| `.ws`、`.sp`、`.ws.sp` 分别改变什么？ | [`variant.md`](variant.md) |
| TS/SS、TMEM/SMEM 描述符如何对应？ | [`operand_source.md`](operand_source.md) |
| guard 如何变成核心谓词或外围控制流？ | [`guard.md`](guard.md) |
| lane 0 发射线程如何改变控制流和寄存器？ | [`issuer.md`](issuer.md) |
| 直接参数与 derived producer 如何影响外围指令？ | [`operand_generation.md`](operand_generation.md) |
| commit、mbarrier、fence、wait 如何构成内存一致性与完成协议？ | [`memory_consistency.md`](memory_consistency.md) |
| collector 的 fill/use/lastuse/discard 如何映射？ | [`collector.md`](collector.md) |
| 分块缩放和缩放向量如何体现？ | [`block_scaling.md`](block_scaling.md) |
| `.ashift` 如何映射，什么组合非法？ | [`ashift.md`](ashift.md) |
| 多个修饰符同时存在时怎样解释？ | [`interactions.md`](interactions.md) |
| 这些规则能否用于从核心 SASS 反推 PTX，哪些字段会多对一？ | [`reverse_mapping_rules.md`](reverse_mapping_rules.md) |
| descriptor 边界、核心机器编码 bitfield 和可回放逆向规则是什么？ | [`descriptor_and_encoding.md`](descriptor_and_encoding.md)、[生成 canonical JSON](../../results/rule-mining/canonical_mapping_rules.json) |
| Thor 主机重跑是否复现了规则，哪些差异不稳定？ | [`reproducibility.md`](reproducibility.md) |

完整函数级 PTX/SASS 对照、上下文和寄存器分析见 [`../tcgen05_mma_PTX到SASS映射规则报告.md`](../tcgen05_mma_PTX到SASS映射规则报告.md)。

## 按 PTX 操作码与限定符（qualifier）查规则

下表第一列把 `.sp`、`.ws` 和 `.ws.sp` 视为 PTX 操作码变体，限定符从它们之后开始编号。因此限定符 1 固定是 `.cta_group::{1,2}`，限定符 2 固定是 `.kind::*`。`—` 表示该代表形态没有后续限定符。

TS/SS 属于操作数契约而不是操作码限定符，单独放在"关键操作数"列。表中列出的是主要合法形态，不表示后续限定符可以自由组合。联合合法性见 [`interactions.md`](interactions.md)。

| PTX 操作码 | 限定符 1（CTA group） | 限定符 2（kind） | 限定符 3 | 限定符 4 | 限定符 5 | 关键操作数 | 主要 SASS 结果 | 详细规则 |
|---|---|---|---|---|---|---|---|---|
| `tcgen05.mma` | `.cta_group::{1,2}` | `.kind::*` | — | — | — | SS：`desc_a, desc_b`；TS：`[a_tmem], desc_b` | `UTC*MMA`；group 2 增加 `.2CTA`；A 为 `gdesc` 或 `tmem` | [`kind_and_opcode.md`](kind_and_opcode.md)、[`cta_group.md`](cta_group.md)、[`operand_source.md`](operand_source.md) |
| `tcgen05.mma.sp` | `.cta_group::{1,2}` | `.kind::*` | — | — | — | 增加 `metadata_tmem` | 主操作码不增加 `.SP`；metadata 进入 `tmem[...]` 操作数 | [`variant.md`](variant.md)、[`operand_source.md`](operand_source.md) |
| `tcgen05.mma.ws` | `.cta_group::1` | `.kind::*` | — | — | — | B 使用权重驻留契约 | `UTC*MMA.WS` | [`variant.md`](variant.md)、[`collector.md`](collector.md) |
| `tcgen05.mma.ws.sp` | `.cta_group::1` | `.kind::*` | — | — | — | 稀疏元数据 + 权重驻留 B 契约 | `UTC*MMA.WS`；仍没有独立 `.SP` | [`variant.md`](variant.md)、[`collector.md`](collector.md) |
| `tcgen05.mma` 或 `tcgen05.mma.sp` | `.cta_group::{1,2}` | `.kind::*` | `.collector::a::{fill,use,lastuse,discard}` | — | — | collector 状态附着在 A 操作数 | `.A_KEEP`、`.A_REUSE` | [`collector.md`](collector.md) |
| `tcgen05.mma.ws` 或 `tcgen05.mma.ws.sp` | `.cta_group::1` | `.kind::*` | `.collector::bN::{fill,use,lastuse,discard}` | — | — | collector 状态附着在 B 操作数，`N=0..3` | `.B_KEEP`、`.B_REUSE`、`.BUFFERn` | [`collector.md`](collector.md) |
| `tcgen05.mma` | `.cta_group::{1,2}` | `.kind::*` | `.block_scale` | `.scale_vec::{1X,2X,4X}` 或 `.block{16,32}` | `.collector::a::*`（可选） | 增加 A/B scale-factor TMEM 操作数 | `UTCQMMA` 或 `UTCOMMA[.4X]`；`.2X/.block32` 不一定显式出现 | [`block_scaling.md`](block_scaling.md)、[`collector.md`](collector.md) |
| `tcgen05.mma.sp` | `.cta_group::{1,2}` | `.kind::*` | `.block_scale` | `.scale_vec::{1X,2X,4X}` 或 `.block{16,32}` | `.collector::a::*`（可选） | 稀疏元数据 + A/B scale-factor TMEM 操作数 | 分块缩放的操作码/操作数规则与稀疏元数据规则共同生效 | [`block_scaling.md`](block_scaling.md)、[`variant.md`](variant.md) |
| `tcgen05.mma` 或 `tcgen05.mma.sp` | `.cta_group::{1,2}` | `.kind::*` | `.ashift` | — | — | 只允许 TS，即 A 来自 TMEM | `UTC*MMA.ASHIFT`，group 2 可组合为 `.2CTA.ASHIFT` | [`ashift.md`](ashift.md)、[`operand_source.md`](operand_source.md) |

例如 `tcgen05.mma.ws.sp.cta_group::1.kind::f16.collector::b2::fill` 可以逐列读成：PTX 操作码=`tcgen05.mma.ws.sp`，限定符 1=`.cta_group::1`，限定符 2=`.kind::f16`，限定符 3=`.collector::b2::fill`。核心结果是 `UTCHMMA.WS`，B 操作数带 `.B_KEEP.BUFFER2`。

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

这些确定性规则已经在 expanded 集合的 52,736 条目标 SASS 出现位置上检查，当前样本中反例数为 0。出现位置（occurrence）指 PTX 中一条实际出现的目标指令。

## 修饰符如何影响 SASS 指令集合

| PTX 维度 | 核心 SASS 选择 | 可能改变的外围指令集合 |
|---|---|---|
| 非分块 kind | `UTCHMMA/UTCQMMA/UTCIMMA` | 无 |
| CTA group 2 | `UTC*MMA.2CTA`；completion 选 `UTCBAR.2CTA` | `MOV`、`R2UR`、`UMOV`、`LOP3.LUT` |
| `.sp` | 主操作码不加 `.SP`；metadata 进入 `tmem[...]` 操作数 | `LDCU.128`、`LDCU(.64)`、`UMOV`，或 `LDC`、`IADD3`、`MOV` |
| `.ws` | `UTC*MMA.WS`；选择 B collector | 取消普通 mask 路径中的 `MOV/R2UR/UMOV/LOP3` |
| zero-column-mask descriptor | `UTC*MMA.WS` 增加一个 UR 操作数 | `LDCU.64`，或 `LDC.64` + `MOV` |
| SS | A 选择 `gdesc[UR]` | `LDCU.64`，或 `LDC.64` + `MOV/R2UR` |
| TS | A 选择 `tmem[UR]` | `LDCU`，或 `LDC` + `IADD3` |
| collector | `.A/B_KEEP`、`.A/B_REUSE`、`.BUFFERn` | 无 |
| 启用分块缩放 | 核心增加 `tmem[scale-factor]` 操作数 | `LDCU.64`，或 `LDC` + `IADD3`，必要时 `MOV/R2UR` |
| 分块家族内的 `2X/4X` | `UTCOMMA` 或 `UTCOMMA.4X` | 无 |
| `.ashift` | `UTC*MMA.ASHIFT` | 无独立移位或其他外围指令 |

`UTC*MMA` 是 `UTCHMMA/UTCQMMA/UTCIMMA/UTCOMMA` 的简写。外围集合中的指令可以按作用分组：

- `LDCU`、`LDCU.64`、`LDCU.128`：把 kernel 参数或常量装入统一寄存器（Uniform Register，UR）。
- `LDC`、`LDC.64`：把参数或常量装入普通通用寄存器（General-Purpose Register，GPR）。
- `MOV`、`UMOV`、`R2UR`：在普通寄存器、统一寄存器或立即数之间搬运。
- `IADD3`：为 derived producer 形成地址。
- `LOP3`、`PLOP3`、`ISETP`、`UISETP`、`BRA`：形成 mask、谓词或控制流。
- `UTCBAR`、`UTCBAR.2CTA`：完成或提交相关的张量核心屏障。
- `NOP`：调度填充，不直接实现修饰符语义。

详细配对数量和变化原因写在各维度文档中，联合判断见 [`interactions.md`](interactions.md)。

内存一致性不属于单个 MMA 修饰符的核心操作码映射。它由 commit、mbarrier、tcgen05 fence、LD/ST wait、scope 和资源生命周期共同构成，见 [`memory_consistency.md`](memory_consistency.md)。

descriptor 的内部内容不属于核心 MMA encoding word 本身。`idesc`、SMEM descriptor、metadata、zero-column-mask 和 block-scale 地址的可见寄存器槽位与不透明参数契约必须分层，见 [`descriptor_and_encoding.md`](descriptor_and_encoding.md)。

## 外围上下文规则速览

| PTX/生成上下文 | 核心 MMA 影响 | 外围 SASS 影响 | 详细规则 |
|---|---|---|---|
| 正/负 guard | 352 个双 occurrence 设计仅在首条增加 `@UPn/@!UPn`；其余 800 个设计的核心助记符不变且无前缀谓词 | `ISETP/UISETP/PLOP3/BRA/EXIT`，或 collector 序列首条核心谓词化 | [`guard.md`](guard.md) |
| lane-0 issuer | 规范操作不变；O1–O3 的 168 个精确子集发生纯寄存器重编号 | `S2R SR_LANEID`、谓词比较、分支/提前退出，并改变活跃寄存器 | [`issuer.md`](issuer.md) |
| identity derived producer | 核心助记符和规范操作不变 | O0 增加 `IADD3/LOP3/MOV/R2UR`；O1–O3 完全消除 | [`operand_generation.md`](operand_generation.md) |
| completion | 核心 MMA 不变 | 增加 commit、mbarrier、fence 和 wait 协议 | [`memory_consistency.md`](memory_consistency.md) |

## 证据等级

| 等级 | 含义 |
|---|---|
| 确定性规则 | 当前适用样本中零反例，有单因素或结构性证据 |
| 条件规则 | 只在特定变体、操作数来源或优化级成立 |
| 观察结果 | 数据中稳定出现，但尚不能归因到独立编码字段 |
| 未覆盖 | 当前静态样本尚未封闭枚举的语法、上下文或机器编码字段 |

单因素证据指比较时只改变一个实验维度。描述符是描述数据地址、布局和解释方式的编码值，不是矩阵数据本身。

## 共同术语

- **PTX**：NVIDIA GPU 的虚拟指令集。
- **SASS**：具体 GPU 实际执行的机器指令。
- **MMA**：矩阵乘加（Matrix Multiply-Accumulate）。
- **张量核心（Tensor Core）**：GPU 中执行矩阵运算的专用硬件。
- **TMEM**：张量内存（Tensor Memory），张量核心使用的专用存储空间。
- **SMEM**：共享内存（shared memory），一个 CTA 内共享的片上存储。
- **CTA**：协作线程块（Cooperative Thread Array），即 CUDA thread block。
- **semantic form**：不包含外围上下文的规范指令语义形态。
- **context**：guard、issuer、producer、completion 等外围条件。

各条目会继续解释本页未覆盖的专有名词。

## 数据规模

下表是当前已发布 Thor 结果；v4 最终矩阵增加定向 predicate/idesc microprobe、扩展 producer/issuer 和 30 个 qualifier/操作数契约阴性探针，Thor 重跑后由生成报告统一替换计数。

| 数据层 | 数量 |
|---|---|
| semantic form | 896 |
| syntax 源码实现 | 1,152 |
| expanded 源码实现 | 9,216 |
| expanded 目标出现位置 | 13,184 |
| 四优化级 SASS 归属配对（attribution） | 52,736 |
| 上下文配对比较 | 32,256 |

归属配对指把 PTX 出现位置与对应的核心 SASS 指令一一关联。

## 复现状态

完整集合已经在 NVIDIA Thor 主机上用另一份二进制 SHA-256 的 CUDA 13.0 `ptxas`/`nvdisasm` 重跑。52,736 条核心 attribution、32,256 个上下文差分、全部规则挖掘结果和 196 个协议有序检查均与原完整重跑一致；仅 28 个 O0 文件出现无语义自搬运 `MOV R0, R0`/`MOV R2, R2` 的相邻顺序交换。比较方法、输入摘要和适用边界见 [`reproducibility.md`](reproducibility.md)。
