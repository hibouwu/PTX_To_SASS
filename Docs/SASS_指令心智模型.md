# SASS 指令心智模型：从反汇编视角"读懂"一条 SASS

> 本文档目标：建立一套**读 SASS 反汇编（nvdisasm 输出）的通用流程**。让你在 `cuda-gdb` / `nsight compute` / `nvdisasm` 看到的每一行 SASS，都能在几秒内理解它在做什么、对应什么硬件资源、编译器为何这么生成。
>
> 本文是 [PTX_指令心智模型.md](file:///root/cuda/cuda_ori_notes/PTX_指令心智模型.md) 的物理层版本：PTX 回答"做什么"，SASS 回答"硬件上怎么做"。

---

## 0 SASS 的本质：它是机器码，不是 IR

三条先入为主的事实，决定了后面所有心智模型的形状：

1. **SASS 是架构绑定的物理指令**——每一条 SASS 直接对应 GPU 硬件执行，不存在 lowering 环节。
2. **SASS 是定长 16 字节 + 软件调度**（NISC/VLIW 风格）——编译器在每条指令里编码了**记分板、stall、yield** 等调度元信息，硬件只做依从执行。
3. **SASS 是显式寄存器 + 显式 predication**——没有 PTX 那层"状态空间"抽象，所有数据的位置、类型、作用域都直接写在指令字段里。

**心智锚点 #0**：读 SASS 时，你不是在"翻译"语义，而是在**逆向读出硬件行为**——每条 SASS 都是一个具体的执行动作。

---

## 1 一条 SASS 的解剖

nvdisasm 输出的典型行：

```
/*0030*/  @!P0  IMAD.WIDE.U32 R4, R12.reuse, R13.reuse, RZ ;
```

从左到右依次有这些"槽位"：

| 槽位 | 内容 | 作用 |
|---|---|---|
| 地址 | `/*0030*/` | 指令的字节偏移（十六进制，16 字节对齐） |
| Guard | `@!P0` | 谓词化执行条件 |
| Opcode | `IMAD` | 主操作 |
| Modifiers | `.WIDE.U32` | 行为细化 |
| Dest | `R4` | 目的寄存器 |
| Sources | `R12.reuse, R13.reuse, RZ` | 源操作数（含复用标记） |

注意：nvdisasm **默认不显示控制码（stall/yield/wait-barrier）**，除非加 `--show-control-codes` 或类似选项。这意味着反汇编看到的是**"指令语义"层**，调度信息被隐藏了。

---

## 2 五个心智切面：读 SASS 的五个问题

看到一行 SASS，按顺序问：

### ① 这是**什么操作**？→ Opcode 族

SASS 的 opcode 数量比 PTX 少得多（约 60 个主 opcode），但变体极多。主要族：

| 族 | 代表 opcode | 典型用途 |
|---|---|---|
| 整数算术 | `IADD3`, `IMAD`, `IMNMX`, `LOP3`, `FLO`, `POPC` | `add.u32`/`mul.wide`/`mad.wide`/`bit ops` |
| 浮点算术 | `FFMA`, `FADD`, `FMNMX`, `DMMA`, `MUFU` | `add.f32`/`fma.f64`/超越函数（rcp/rsqrt/sin/ex2） |
| 半精度 / 张量 | `HFMA2`, `HMMA`, `BMMA`, `WGMMA`, `tcgen05.mma` | fp16 算术、Tensor Core MMA |
| 比较 / 谓词 | `ISETP`, `FSETP`, `SEL`, `SELP`, `PLOP3` | `setp`/`selp`/条件计算 |
| 移动 | `MOV`, `SHFL`, `PRMT`, `MOVM`, `MOVM.TRANS` | 数据搬运、寄存器打包 |
| 统一路径 | `UADD32`, `UIADD3`, `UMOV`, `ULDC`, `UIADD3.RN` | warp-invariant 计算（UR 上） |
| 内存 | `LDC`, `LDG`, `LDS`, `LDL`, `STG`, `STS`, `STL`, `ATOM`, `RED`, `LDGSTS`, `LDSM`, `LDT`, `STT` | 7 类内存空间读写 |
| 控制流 | `BRA`, `CALL`, `RET`, `EXIT`, `JMP`, `JCAL`, `PREEXIT` | 分支/函数/返回 |
| 同步 | `BAR`, `MEMBAR`, `DEPBAR`, `CS2R` | 屏障/内存序 |
| 视频 SIMD | `VMNMX`, `VSET`, `VABSDIFF4`, `VADD` | 子字 SIMD 整数（8/16-bit） |

**查规范的第一原则**：先看主 opcode（第一个 `.` 之前），再根据修饰符查其变体语义。NVIDIA `Binary Utilities` 文档 §6 只给 opcode 列表，详细语义靠逆向。

### ② 数据**住在哪**？→ 操作数形态决定存储位置

SASS 没有"状态空间"这个语法层——**操作数本身的写法就是空间**：

| SASS 记法 | 物理空间 |
|---|---|
| `R5`, `R12:R13`（对） | 通用寄存器堆（GPR） |
| `UR4`, `UR6` | 统一寄存器（warp-invariant） |
| `P0`, `P7(=PT)`, `UP0` | 谓词寄存器 |
| `c[0x0][0x210]` | Constant Bank 0 偏移 0x210（kernel 参数 / 常量） |
| `c[1][0x100]` | Constant Bank 1（用户 `__constant__`） |
| `desc[UR6][R2.64]` | **Memory Descriptor**（Hopper+）：全局内存地址由 UR 描述符 + R 偏移组成 |
| `gdesc[UR4]` | 全局描述符（kernel 参数中传递的指针） |
| `tmem[UR8]` | Tensor Memory（Blackwell） |
| `[R5+0x8]`, `[UR4+R2.64]` | Shared / Local / Generic（具体空间由 base 地址决定） |

**关键心智 #1**：SASS 里**没有 `.global` / `.shared` 这种显式标注**——地址的**来源**（哪个寄存器、带不带描述符）决定了它落在哪个物理空间。

### ③ **多宽、多快、怎么算**？→ Modifier 链

紧跟 opcode 后面的 `.modifier` 串是 SASS 表达力的主要来源：

| Modifier | 含义 | 例子 |
|---|---|---|
| `.64` / `.128` | 宽度（寄存器对/四联） | `STG.64`, `STS.128` |
| `.E` | 64-bit 扩展寻址 | `LDG.E` |
| `.WIDE` | 32×32→64 宽乘 | `IMAD.WIDE.U32` |
| `.U32` / `.S32` / `.U16` | 操作数类型与宽度 | `IMAD.U32`, `ISETP.GT.U32` |
| `.FTZ` | Flush to zero（f32 非正规数归零） | `FADD.FTZ` |
| `.SAT` | 饱和（整数钳位到类型范围） | `IADD3.SAT` |
| `.GT / .LT / .EQ / .NE / .GE / .LE` | 比较条件 | `ISETP.GT.U32` |
| `.AND / .OR / .XOR` | 谓词合并模式 | `ISETP.GT.U32.AND` |
| `.LUT` | LOP3 查找表模式 | `PLOP3.LUT` |
| `.STRONG / .WEAK` + `.SC/.ACQ/.REL` | 内存序语义 | `STG.E.STRONG.GPU` |
| `.CTA / .GPU / .SYS / .CLUSTER` | 内存作用域 | `MEMBAR.GPU` |
| `.NOINC` | CALL 无返回地址递增 | `CALL.REL.NOINC` |
| `.REL` / `.NODEC` | 返回方式（相对/不递减） | `RET.REL.NODEC` |

**关键心智 #2**：modifier 链是**正交的**——`IMAD.WIDE.U32` 是 (主 opcode + 宽度 + 类型) 三个独立维度的组合；`LDG.E.SYS` 是 (寻址扩展 + 作用域) 两个独立维度。读 modifier 时按"主修饰在前、细节在后"的顺序逐段理解。

### ④ **何时执行**？→ Predication（`@P0` / `@!P0` / `@UP0`）

几乎任何指令都可加谓词前缀：

```
@P0   MOV R1, 0x1;        // P0=true 时执行
@!P0  IMAD ... ;          // P0=false 时执行
@UP0  UIADD3 ... ;        // 统一谓词（warp 级）控制
```

SASS 的 predication 直接编码在指令位里（不是条件分支），这是 GPU 实现分支消除（branch elimination）的硬件基础。PTX 的 `@%p1` 就是落到这里。

### ⑤ 操作数**是什么形态**？→ 立即数 / 寄存器对 / 复用标记

| 记法 | 含义 |
|---|---|
| `0x1` / `0xff` | 立即数 |
| `RZ` / `URZ` / `PT` | 零寄存器 / 真谓词（特殊别名） |
| `R4:R5` / `R4.64` | 64-bit 寄存器对 |
| `R12.reuse` | **操作数复用**：同一寄存器在相邻指令被多次读取，命中 Operand Reuse Cache，省功耗且缓解 bank conflict |
| `R12.SIGN` | 符号位提取（PLOP3 专用） |
| `R2.64` | 64-bit 宽度修饰 |

**关键心智 #3**：`.reuse` 是 SASS **独有**的标记——它不是语义，而是**功耗/性能提示**，告诉硬件"这个源操作数在上一条指令已经读过，可以从 Operand Reuse Cache 直接取，不用再访问寄存器堆"。ptxas 会在指令调度阶段自动添加。

---

## 3 实例演练（取自真实 nvdisasm 输出）

### 例 1：`LDC.64 R2, c[0x0][0x218];`

| 槽位 | 内容 |
|---|---|
| opcode | `LDC`（从 constant bank 读） |
| modifier | `.64`（64-bit） |
| dest | `R2`（实际占用 R2:R3 这对寄存器） |
| src | `c[0x0][0x218]`（bank 0 偏移 0x218，正是 PTX 参数区里 `x` 的位置） |

→ 这是 kernel 参数加载：一次性把两个 u32 打包读入寄存器对。

### 例 2：`LDG.E R9, desc[UR6][R2.64];`

| 槽位 | 内容 |
|---|---|
| opcode | `LDG`（global 读） |
| modifier | `.E`（64-bit 扩展） |
| dest | `R9` |
| src | `desc[UR6][R2.64]` |

→ Hopper+ 的"描述符寻址"：`UR6` 是内核参数中传进来的 global buffer 描述符（`ULDC.64 UR6, c[0x0][0x208]` 装载），`R2.64` 是 64-bit 偏移。PTX 侧对应 `ld.global.u32`。

### 例 3：`FADD.FTZ R15, R14, R15;`

| 槽位 | 内容 |
|---|---|
| opcode | `FADD`（f32 加） |
| modifier | `.FTZ`（非正规数归零） |
| dest | `R15` |
| src | `R14`, `R15`（同时是源和目的，三操作数风格） |

→ PTX 侧对应 `add.rn.ftz.f32`。`.rn` 是默认舍入所以省略。

### 例 4：`IMAD.WIDE.U32 R4, R12.reuse, R13.reuse, RZ;`

| 槽位 | 内容 |
|---|---|
| opcode | `IMAD`（整数 MAD） |
| modifier | `.WIDE`（32×32→64）+ `.U32`（无符号 32-bit 源） |
| dest | `R4`（占 R4:R5 这对 64-bit） |
| src | `R12`, `R13`, `RZ`（R12×R13 + RZ = R12×R13，等价于 MUL.WIDE） |
| 复用 | 两个源都带 `.reuse` |

→ PTX 侧 `mul.wide.u32 %rd8, %r1, %r2` 被 lowering 为 `IMAD.WIDE` 并将第三操作数固定为 RZ。**PTX 没有 IMAD，但有 mul 和 mad；SASS 统一为 IMAD**。

### 例 5：`ISETP.GT.U32.AND P0, PT, R12.reuse, R13.reuse, PT;`

| 槽位 | 内容 |
|---|---|
| opcode | `ISETP`（整数比较并写谓词） |
| modifier | `.GT`（大于）+ `.U32`（无符号 32-bit）+ `.AND`（默认合并） |
| dest1 | `P0`（主谓词输出：比较结果） |
| dest2 | `PT`（次谓词输出：这里丢弃） |
| src1 | `R12.reuse` |
| src2 | `R13.reuse` |
| src3 | `PT`（输入谓词：恒真，等价于"无条件比较"） |

→ PTX 侧 `setp.gt.u32 %p1, %r1, %r2`。ISETP 是**三源双目的**指令，PTX 层看不到第三个源（谓词输入）。

### 例 6：`@!P0 IMAD.MOV.U32 R21, RZ, RZ, RZ;`

| 槽位 | 内容 |
|---|---|
| guard | `@!P0`（P0 为假时执行） |
| opcode | `IMAD`（`MOV` 是 `IMAD` 的零操作数别名） |
| modifier | `.MOV.U32`（MOV 变体） |
| dest | `R21` |
| src | `RZ, RZ, RZ`（全是零） |

→ 这是 ptxas 把 `mov.u32 %r7, 0;` 和分支合并后的形式——**一条 MOV 指令**，加 `@!P0` 谓词化。GPU 上条件 mov 是**没有跳转**的。

---

## 4 隐藏层：控制码（Control Codes）

反汇编里**不可见**但物理上存在每个指令字节里的调度元信息（Volta+）：

| 字段 | 作用 | 反汇编可见性 |
|---|---|---|
| `Reuse`（4-bit） | 4 个源操作数的复用标记 | `.reuse` 后缀（唯一可见） |
| `Wait Barrier`（6-bit） | 等待哪些记分板（scoreboard 0–5）清零 | 仅在 `-hex` 原始编码里 |
| `Read Barrier`（3-bit） | 为源寄存器设置哪个记分板 | 仅在 `-hex` 原始编码里 |
| `Write Barrier`（3-bit） | 为目的寄存器设置哪个记分板 | 仅在 `-hex` 原始编码里 |
| `Yield`（1-bit） | 是否让出给其他 warp | 仅在 `-hex` 原始编码里 |
| `Stall Count`（4-bit） | 发射后停顿 0–15 周期 | 仅在 `-hex` 原始编码里 |

> **注意**：nvdisasm **没有** `--show-control-codes` 这种 flag。控制码只以 16 字节 hex 形式随 `--print-instruction-encoding`（`-hex`）输出，NVIDIA 未公开位布局。想看到可读的 Reuse/Yield/Wait/Read/Write/Stall，需用社区工具（如 [CuAssembler](https://github.com/cloudcores/CuAssembler) 的 `CuAsmDisplayer`）解析那 16 字节。

**关键心智 #4**：读 SASS 反汇编看到的"顺序"只是**发射顺序**，真正的数据依赖由控制码的 wait/read/write barrier 表达——这是 SASS 与 PTX 最大的隐性差异。PTX 的依赖由 ptxas 推导并写入 SASS 的控制码位。

---

## 5 与 PTX 的关键差异对照

| 维度 | PTX | SASS |
|---|---|---|
| 抽象层次 | 虚拟 ISA（IR） | 物理机器码 |
| 指令长度 | 变长（文本） | 16 字节定长 |
| 状态空间 | 显式 `.global/.shared/.local/.const/.param` | 隐式（靠操作数形态） |
| 类型 | 强类型，每个指令都带类型 qualifier | 弱类型，类型在 modifier 里 |
| 寄存器 | SSA 虚拟寄存器（无限） | 256 个物理 GPR（+UR+P+SR） |
| 谓词 | `@%p1`（带 `%`） | `@P0`（不带 `%`） |
| 操作数个数 | 严格（opcode 决定） | 可多可少（IMAD 三源但 MUL 退化为 RZ） |
| 控制流 | 结构化（bra/call/ret 配对） | 相对地址 + 返回栈管理 |
| 内存访问 | `ld.global.f32` | `LDG.E` + descriptor/base+offset |
| 调度 | 编译器/ptxas 推导 | **编译器已写入控制码位**（软件调度） |
| 复用 | 无概念 | `.reuse` 显式标记 |

---

## 6 读 SASS 的"四步法"

1. **先看 opcode 族**：第一个 `.` 前的词（`LDG`/`IMAD`/`FADD`...），锁定操作类型。
2. **看 modifier 链**：确定宽度、符号、FTZ、作用域、舍入等细节。
3. **看操作数形态**：是 GPR、UR、predicate、常量 bank、描述符、还是直接地址？→ 反推物理空间。
4. **看 predication 前缀**：是否有 `@P0`/`@!P0` → 判断条件性。
5. （可选）**反查 PTX**：对照 cubin 的 PTX 源码，看这条 SASS 是从哪条 PTX 指令 lowering 来的。

---

## 7 常见误区

1. ❌ "SASS 每条指令和 PTX 一一对应"
   → ptxas 会合并、拆分、重排。`add.u32 + bra + mov + mov + bra` 常被折叠为两条 predicated `IMAD.MOV`。
2. ❌ "SASS 里的寄存器名和 PTX 对应"
   → 物理寄存器分配由 ptxas 做，PTX 的 `%r1` 可能变成 SASS 的 `R12`、`R4:R5`，甚至被消除。
3. ❌ "反汇编里看到的所有指令都会被执行"
   → 很多指令被 predication 条件跳过；还有些是 dead-code 残留（罕见，但存在）。
4. ❌ "操作数顺序和 PTX 一样"
   → SASS 统一采用 **dest, src1, src2, src3** 顺序；PTX 某些指令（`setp`）是三目的，SASS 则是五操作数（`ISETP`）。
5. ❌ "没有 modifier 就是无修饰"
   → 默认舍入 `.rn`、默认谓词合并 `.AND`、默认作用域等通常**不显式写出**但存在。

---

## 8 对 ptx2sass 项目的实战意义

实现自研 ptxas 时，SASS 心智模型直接决定你每个 lowering pass 的输出形态：

1. **操作数 lowering**：把 PTX SSA 寄存器映射到物理 GPR / UR，并决定是否需要 `.reuse` 标记（缓解 bank conflict）。
2. **空间 lowering**：把 PTX `.global/.shared/...` 翻译成对应的 SASS opcode（LDG/LDS/LDL/LDC/STS...）+ descriptor / base+offset 寻址。
3. **类型 lowering**：把 PTX 类型 qualifier 映射到 SASS 的 type modifier（`.U32/.S32/.64`）和 opcode 变体选择。
4. **行为 lowering**：直接映射（`.ftz→FTZ`）、默认省略（`.rn`）、或**软件展开**（`.sat`、`.approx`、复杂舍入）。
5. **控制码生成**：为每条 SASS 填写 Wait/Read/Write Barrier、Yield、Stall Count——这是软件调度的核心。
6. **Predication 翻译**：把 PTX `@%p` 翻译为 SASS `@P`/`@!P`，必要时用 `IMAD.MOV` 代替分支（branch predication）。

---

## 9 一句话总结

> **SASS = Opcode 族 + Modifier 链 + 操作数形态 + Predication + 控制码**。
> 前四项你反汇编看得到，第五项物理上存在但反汇编默认隐藏。
> 每条 SASS 都是一个"已经做完所有调度决策的具体硬件动作"——不像 PTX 那样还留有"选择"的空间。

把这张图刻在脑子里，你在 `nsight compute` 的 Source 视图 / `nvdisasm` 输出里看到的 SASS 就不再是一堆奇怪的缩写，而是**硬件执行的精确快照**——编译器替你做完所有优化和调度之后留下的最终产物。
