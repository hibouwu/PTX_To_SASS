# NVIDIA GPU SASS 指令参考文档

> 面向 PTX/编译器工程视角整理的 NVIDIA GPU 汇编（SASS）指令参考。
>
> **主要来源**：`CUDA Binary Utilities`（Release 13.3，NVIDIA 官方文档，Chapter 6 “Instruction Set Reference”）。
> **补充来源**：NVIDIA 开发者论坛、PNF Software JEB SASS 逆向分析、CuAssembler 项目文档等公开资料（用于补充官方文档未展开的控制码 / 编码 / 寄存器模型等背景）。
>
> 说明：SASS（Streaming ASSembler，也叫 Shader ASSembly）是 NVIDIA GPU 的**半公开**原生机器指令集。NVIDIA 官方仅公布各架构的 **opcode 列表 + 一句话描述**，指令的二进制编码、控制码、操作数约束等均未正式文档化。本文档中标注为“补充”的内容属社区逆向结论，供理解与实现参考，可能随架构演进而变化。

---

## 目录

1. [SASS 是什么：编译链路与定位](#1-sass-是什么编译链路与定位)
2. [执行模型与寄存器文件](#2-执行模型与寄存器文件)
3. [指令格式与语法约定](#3-指令格式与语法约定)
4. [控制码与调度信息（Control Codes）](#4-控制码与调度信息control-codes)
5. [指令分类总览](#5-指令分类总览)
6. [跨架构统一指令表（Turing / Ampere+Ada / Hopper / Blackwell）](#6-跨架构统一指令表)
7. [跨架构演进要点](#7-跨架构演进要点)
8. [常用指令详解与示例](#8-常用指令详解与示例)
9. [工具：如何生成与查看 SASS](#9-工具如何生成与查看-sass)
10. [参考资料](#10-参考资料)

---

## 1. SASS 是什么：编译链路与定位

SASS 是 `nvcc` 编译 CUDA C++ 或 `ptxas` 编译 PTX 之后，最终运行在 GPU 上的真实机器码：

```
CUDA C/C++  ──(nvcc 前端)──►  PTX (中间表示, 类 LLVM IR)  ──(ptxas)──►  SASS (架构相关机器码)
```

- **PTX** 是**架构无关**、向前兼容的虚拟 ISA，由 NVIDIA 完整文档化（PTX ISA）。
- **SASS** 是**架构相关**（绑定具体 Compute Capability / SM 版本）的物理 ISA，随每代架构变化，是真正决定性能的层次。
- GPU 代码被封装在 ELF 容器 **cubin**（CUDA binary）中；多个 cubin 可打包为 **fatbin** 嵌入宿主可执行文件。运行时由 CUDA 驱动加载对应架构的 cubin。

各架构与 Compute Capability 对应关系（本文覆盖范围）：

| 架构族 | Compute Capability | 典型 SM 目标 | 代表 GPU |
| --- | --- | --- | --- |
| Turing | 7.5 | `sm_75` | RTX 20 系、T4 |
| Ampere | 8.0 / 8.6 | `sm_80` / `sm_86` | A100、RTX 30 系 |
| Ada Lovelace | 8.9 | `sm_89` | RTX 40 系、L4/L40 |
| Hopper | 9.0 | `sm_90` / `sm_90a` | H100 / H200 |
| Blackwell | 10.0 / 12.0 | `sm_100` / `sm_120` 等 | B100/B200、GB200、RTX 50 系 |

> 官方文档将 Ampere 与 Ada 归为同一张指令表；Blackwell（数据中心 10.x 与消费级 12.x）共用同一张指令表。Volta（`sm_70`）及更早架构未收录于本份 13.3 文档，但编码格式（16 字节定长）与 Turing 同属 Volta+ 体系。

---

## 2. 执行模型与寄存器文件

### 2.1 执行层级

- **Thread**：最小执行单元，拥有私有寄存器。
- **Warp**：32 个线程，锁步（lockstep）执行；分支发散时通过掩码（mask）屏蔽非活跃线程，直到重收敛点。
- **CTA / Thread Block**：由多个 warp 组成，最多 1024 线程；共享片上 Shared Memory。
- **Cluster**（Hopper 起）：多个 CTA 组成的集群，可跨 CTA 访问分布式 Shared Memory（DSMEM）。
- **Grid**：一次 kernel 启动的全部 CTA / Cluster。
- 代码运行在 **SM（Streaming Multiprocessor）** 上。

### 2.2 数据空间

| 空间 | 作用域 | 位置 | 主要访问指令 |
| --- | --- | --- | --- |
| Registers | per-thread | 片上寄存器堆 | 直接寻址 |
| Local Memory | per-thread | DRAM（带缓存） | `LDL` / `STL` |
| Shared Memory | per-CTA | 片上 | `LDS` / `STS` / `LDSM` / `STSM` |
| Global Memory | 全局 | DRAM | `LDG` / `STG` / `LDGSTS` |
| Constant Memory | 全局只读 | DRAM（带缓存），SASS 记为 `c[bank][offset]` | `LDC` / `ULDC` |
| Texture Memory | 全局只读 | DRAM | `TEX` / `TLD` / `TLD4` |
| Tensor Memory | per-CTA（Blackwell 新增） | 片上，记为 `tmem[URx]` | `LDT/LDTM` / `STT/STTM` / `UTCCP` |

### 2.3 寄存器模型（补充）

| 寄存器类 | 记法 | 数量与位宽 | 说明 |
| --- | --- | --- | --- |
| 通用寄存器 | `Rx` | 最多 256 个 32-bit | 64-bit 值用两个连续寄存器表示；`R255` 恒为 0，别名 **RZ** |
| 谓词寄存器 | `Px` | 每线程 8 个布尔 | `P7` 恒为真，别名 **PT** |
| 特殊寄存器 | `SRx` | 256 个只读 | thread/block ID、lane id、clock、性能计数器等；如 `SR0`=lane id 别名 `SR_LANEID` |
| 统一寄存器 | `URx` | Turing~Hopper 64 个 / `sm_100+` 增至 256 个 | warp 内所有线程共享同一值；末位为零寄存器 **URZ** |
| 统一谓词寄存器 | `UPx` | 8 个布尔 | `UP7` 恒为真，别名 **UPT** |

- 统一寄存器（Uniform Register，URx/UPx）自 Turing 引入，用于承载 warp 内所有线程一致的标量值（如地址基址、循环计数），由“Uniform Datapath”流水线处理，可显著降低通用寄存器压力与功耗。
- PTX 中的内建变量与 SASS 特殊寄存器对应，例如 `%tid.x` → `SR_TID.X`，`%ctaid.x` → `SR_CTAID.X`。

---

## 3. 指令格式与语法约定

### 3.1 基本格式

官方给出的指令格式（Turing 起一致）：

```
[@谓词] (指令).修饰符  (目的操作数), (源操作数1), (源操作数2), ...
```

有效的目的 / 源操作数位置：

| 记法 | 含义 | 引入架构 |
| --- | --- | --- |
| `Rx` | 通用寄存器 | 全部 |
| `URx` | 统一寄存器 | 全部（Turing 起） |
| `SRx` | 特殊系统寄存器 | 全部 |
| `Px` | 谓词寄存器 | 全部 |
| `UPx` | 统一谓词寄存器 | Ampere 起 |
| `c[X][Y]` | 常量内存（bank X，偏移 Y） | 全部 |
| `desc[URx][Ry]` | 内存描述符 | Hopper 起 |
| `gdesc[URx]` | 全局内存描述符 | Hopper 起 |
| `tmem[URx]` | Tensor Memory | Blackwell 起 |

### 3.2 关键约定（补充）

- **定长编码**：Volta+（含 Turing/Ampere/Ada/Hopper/Blackwell）所有指令均为 **16 字节（128-bit）定长**。
- **操作数顺序**：目的操作数在前，源操作数在后；SASS **不使用** x86 那种 src+dst 合一的操作数。
- **谓词化（predication）**：几乎所有指令都可加前缀谓词。
  - `@P0 IMAD ...`：当 `P0` 为真时执行。
  - `@!P0 IMAD ...`：当 `P0` 为假时执行。
- **修饰符 / 限定符（modifiers）**：附加在 opcode 或操作数上，细化行为，可堆叠。常见示例：
  - `.64` / `.128`：操作数位宽（寄存器对 / 四联）。如 `STS.128`。
  - `.E`：扩展地址（64-bit 寻址）。如 `LDG.E`。
  - `.SYS` / `.GPU` / `.CTA`：内存作用域（scope）。
  - `.STRONG` / `.WEAK` + `.SC`/`.ACQ`/`.REL`：内存序语义（与 PTX 内存模型对应）。
  - `.reuse` / `.noreuse`：操作数复用缓存标记（见第 4 节）。
  - `.LUT`：`LOP3.LUT` 用查找表实现任意 3 输入位运算。
  - `.WIDE`：`IMAD.WIDE` 产生 64-bit 结果。
- **常量内存 kernel 参数**：kernel 入参映射到常量 bank 0 的固定偏移（补充：`sm_70~sm_89` 起始 `0x160`，`sm_90` 为 `0x210`，`sm_100~sm_12x` 为 `0x380`），SASS 中体现为 `c[0x0][offset]`。

### 3.3 反汇编示例（nvdisasm 风格）

```
@!P0  IMAD R0, R1, R2, R3 ;      // 若 P0=false, R0 = R1*R2 + R3
      LDG.E.SYS R3, [R2+0x4] ;   // 从 global 读取 32-bit 到 R3
      STS.128 [R5], R8 ;          // 向 shared 写 128-bit
      MOV R1, c[0x0][0x28] ;      // 读取常量内存
      EXIT ;
```

---

## 4. 控制码与调度信息（Control Codes）

> 以下为社区逆向结论（补充），官方未公开。SASS 是**软件负责调度**的架构（NISC/VLIW 风格）：编译器在每条指令上编码调度信息以避免数据冒险，而非靠硬件动态记分板全权处理。

自 Volta 起，每条 16 字节指令内含一段**控制码**，一般拆分为如下字段（以 CuAssembler 的文本表示为例：`[R-:B------:R-:W-:Y:S04]`）：

| 字段 | 记法示例 | 含义 |
| --- | --- | --- |
| **Reuse** | `-R--` | 操作数复用缓存标记（4-bit，对应操作数槽位）。命中后可缓解寄存器 bank conflict 并省功耗；文本中对应 `.reuse` 后缀，是唯一在反汇编里可见的控制码。 |
| **Wait Barrier**（等待记分板） | `B------` ~ `B01--4-` | 6 个记分板（scoreboard，编号 0–5），每 bit 表示是否等待对应记分板清零。可等待多个，如 `B01--4-` 等待 0/1/4。 |
| **Read Barrier** | `R-` / `R0`~`R5` | 设置一个记分板保护**源**寄存器内容（多用于内存指令等可变延迟场景，防止源被过早覆盖）。 |
| **Write Barrier** | `W-` / `W0`~`W5` | 设置一个记分板保护**目的**寄存器，直到结果就绪才允许读取。用于变延迟指令：内存 load、双精度、超越函数、`S2R` 等。 |
| **Yield** | `Y` / `-` | 是否让出给同一 SM 上另一个符合条件的 warp（配合双发射 / 隐藏延迟）。 |
| **Stall count** | `S00`~`S15` | 发射后停顿的时钟周期数（0–15），用于满足固定延迟指令的间隔。 |

要点（补充）：
- **固定延迟指令**（如多数 ALU）：靠 **stall count** 或插入无关指令保证下一条相关指令发射前输入就绪。
- **可变延迟指令**（如 `LDG`、`DFMA`、`MUFU`、`S2R`）：靠 **write/read barrier + wait barrier**（记分板）建立依赖，消费方用 wait barrier 等待；也可用 `DEPBAR` 指令显式等待记分板。
- 记分板依赖关系是编译器/汇编器（`ptxas`）正确性的关键：写少了会数据竞争，写多了会损失并行度。这与内存序无关，属指令级依赖调度。

---

## 5. 指令分类总览

官方按功能将 SASS 指令分为以下类别（不同架构类别略有增减）：

- **Floating Point**：FP32 / FP16 / FP64 算术、比较、MMA、超越函数（`MUFU`）。
- **Integer**：整数算术、逻辑、移位、点积、整数 MMA、SIMD 子字整数。
- **Conversion**：浮点↔整数、位宽转换与打包。
- **Movement**：`MOV`、`SHFL`、`PRMT`、矩阵搬运 `MOVM` 等。
- **Predicate**：谓词逻辑与谓词↔寄存器互转。
- **Load/Store**：各内存空间的读写、原子、归约、栅栏、异步拷贝。
- **Uniform Datapath**：统一寄存器上的等价运算（前缀 `U`）。
- **Warpgroup**（Hopper）：跨 warpgroup 的 GMMA 与同步。
- **Tensor Memory Access**（Hopper+）：TMA（Tensor Memory Accelerator）批量 / 张量拷贝。
- **Tensor Core Memory**（Blackwell）：`tcgen05` 相关 Tensor Memory 与 MMA。
- **Texture / Surface**：纹理采样与表面读写。
- **Control**：分支、调用、收敛屏障、退出、休眠等控制流。
- **Miscellaneous**：屏障同步、特殊寄存器搬运、性能监控、`NOP` 等。

---

## 6. 跨架构统一指令表

下表将 Turing、Ampere+Ada、Hopper、Blackwell 四代指令集合并，按功能类别组织。可用性列：
- **T** = Turing (sm_75)
- **A** = Ampere + Ada (sm_80/86/89)
- **H** = Hopper (sm_90)
- **B** = Blackwell (sm_100/120)

标记 `✓` 表示该架构指令表中包含该 opcode。

### 6.1 Floating Point Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| FADD | FP32 加法 | ✓ | ✓ | ✓ | ✓ |
| FADD2 | FP32 加法（成对） | | | | ✓ |
| FADD32I | FP32 加法（立即数） | ✓ | ✓ | ✓ | ✓ |
| FCHK | 浮点范围检查（用于除法） | ✓ | ✓ | ✓ | ✓ |
| FFMA | FP32 融合乘加 | ✓ | ✓ | ✓ | ✓ |
| FFMA32I | FP32 融合乘加（立即数） | ✓ | ✓ | ✓ | ✓ |
| FFMA2 | FP32 融合乘加（成对） | | | | ✓ |
| FHADD | FP32 加法 | | | | ✓ |
| FHFMA | FP32 融合乘加 | | | | ✓ |
| FMNMX | FP32 最小/最大 | ✓ | ✓ | ✓ | ✓ |
| FMNMX3 | 3 输入 FP32 最小/最大 | | | | ✓ |
| FMUL | FP32 乘法 | ✓ | ✓ | ✓ | ✓ |
| FMUL2 | FP32 乘法（成对） | | | | ✓ |
| FMUL32I | FP32 乘法（立即数） | ✓ | ✓ | ✓ | ✓ |
| FSEL | 浮点选择 | ✓ | ✓ | ✓ | ✓ |
| FSET | FP32 比较置值 | ✓ | ✓ | ✓ | ✓ |
| FSETP | FP32 比较置谓词 | ✓ | ✓ | ✓ | ✓ |
| FSWZADD | FP32 Swizzle 加法 | ✓ | ✓ | ✓ | ✓ |
| MUFU | FP32 多功能运算（sin/cos/rcp/rsqrt 等） | ✓ | ✓ | ✓ | ✓ |
| HADD2 | FP16 加法（向量2） | ✓ | ✓ | ✓ | ✓ |
| HADD2_32I | FP16 加法（立即数） | ✓ | ✓ | ✓ | ✓ |
| HFMA2 | FP16 融合乘加 | ✓ | ✓ | ✓ | ✓ |
| HFMA2_32I | FP16 融合乘加（立即数） | ✓ | ✓ | ✓ | ✓ |
| HMMA | 矩阵乘加（FP16/BF16 Tensor Core） | ✓ | ✓ | ✓ | ✓ |
| HMNMX2 | FP16 最小/最大 | | ✓ | ✓ | ✓ |
| HMUL2 | FP16 乘法 | ✓ | ✓ | ✓ | ✓ |
| HMUL2_32I | FP16 乘法（立即数） | ✓ | ✓ | ✓ | ✓ |
| HSET2 | FP16 比较置值 | ✓ | ✓ | ✓ | ✓ |
| HSETP2 | FP16 比较置谓词 | ✓ | ✓ | ✓ | ✓ |
| DADD | FP64 加法 | ✓ | ✓ | ✓ | ✓ |
| DFMA | FP64 融合乘加 | ✓ | ✓ | ✓ | ✓ |
| DMMA | FP64 矩阵乘加（Tensor Core） | | ✓ | ✓ | ✓ |
| DMUL | FP64 乘法 | ✓ | ✓ | ✓ | ✓ |
| DSETP | FP64 比较置谓词 | ✓ | ✓ | ✓ | ✓ |
| OMMA | FP4 矩阵乘加（warp 级） | | | | ✓ |
| QMMA | FP8 矩阵乘加（warp 级） | | | | ✓ |

### 6.2 Integer Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| BMMA | 位矩阵乘加 | ✓ | ✓ | ✓ | |
| BMSK | 位域掩码 | ✓ | ✓ | ✓ | ✓ |
| BREV | 位反转 | ✓ | ✓ | ✓ | ✓ |
| FLO | 查找最高位 1 | ✓ | ✓ | ✓ | ✓ |
| IABS | 整数绝对值 | ✓ | ✓ | ✓ | ✓ |
| IADD | 整数加法 | ✓ | ✓ | ✓ | ✓ |
| IADD3 | 3 输入整数加法 | ✓ | ✓ | ✓ | ✓ |
| IADD32I | 整数加法（立即数） | ✓ | ✓ | ✓ | ✓ |
| IDP | 整数点积并累加 | ✓ | ✓ | ✓ | ✓ |
| IDP4A | 整数点积并累加（4 元） | ✓ | ✓ | ✓ | ✓ |
| IMAD | 整数乘加 | ✓ | ✓ | ✓ | ✓ |
| IMMA | 整数矩阵乘加（Tensor Core） | ✓ | ✓ | ✓ | ✓ |
| IMNMX | 整数最小/最大 | ✓ | ✓ | ✓ | ✓ |
| IMUL | 整数乘法 | ✓ | ✓ | ✓ | ✓ |
| IMUL32I | 整数乘法（立即数） | ✓ | ✓ | ✓ | ✓ |
| ISCADD | 带移位缩放的整数加法 | ✓ | ✓ | ✓ | ✓ |
| ISCADD32I | 带移位缩放的整数加法（立即数） | ✓ | ✓ | ✓ | ✓ |
| ISETP | 整数比较置谓词 | ✓ | ✓ | ✓ | ✓ |
| LEA | 计算有效地址（Load Effective Address） | ✓ | ✓ | ✓ | ✓ |
| LOP | 逻辑运算 | ✓ | ✓ | ✓ | ✓ |
| LOP3 | 3 输入逻辑运算（LUT） | ✓ | ✓ | ✓ | ✓ |
| LOP32I | 逻辑运算（立即数） | ✓ | ✓ | ✓ | ✓ |
| POPC | 位计数（population count） | ✓ | ✓ | ✓ | ✓ |
| SHF | 漏斗移位（funnel shift） | ✓ | ✓ | ✓ | ✓ |
| SHL | 左移 | ✓ | ✓ | ✓ | ✓ |
| SHR | 右移 | ✓ | ✓ | ✓ | ✓ |
| VABSDIFF | 绝对差 | ✓ | ✓ | ✓ | ✓ |
| VABSDIFF4 | 绝对差（4 元） | ✓ | ✓ | ✓ | ✓ |
| VHMNMX | SIMD FP16 3 输入最小/最大 | | | ✓ | ✓ |
| VIADD | SIMD 整数加法 | | | ✓ | ✓ |
| VIADDMNMX | SIMD 整数加法并融合最小/最大 | | | ✓ | ✓ |
| VIMNMX | SIMD 整数最小/最大 | | | ✓ | ✓ |
| VIMNMX3 | SIMD 整数 3 输入最小/最大 | | | ✓ | ✓ |

### 6.3 Conversion Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| F2F | 浮点到浮点转换 | ✓ | ✓ | ✓ | ✓ |
| F2I | 浮点到整数转换 | ✓ | ✓ | ✓ | ✓ |
| I2F | 整数到浮点转换 | ✓ | ✓ | ✓ | ✓ |
| I2I | 整数到整数转换 | ✓ | ✓ | ✓ | ✓ |
| I2IP | 整数到整数转换并打包 | ✓ | ✓ | ✓ | ✓ |
| I2FP | 整数到 FP32 转换并打包 | | ✓ | ✓ | ✓ |
| F2IP | FP32 下转换到整数并打包 | | ✓ | ✓ | ✓ |
| FRND | 舍入到整数 | ✓ | ✓ | ✓ | ✓ |

### 6.4 Movement Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| MOV | 移动 | ✓ | ✓ | ✓ | ✓ |
| MOV32I | 移动（立即数） | ✓ | ✓ | ✓ | ✓ |
| MOVM | 矩阵移动（含转置/扩展） | ✓ | ✓ | ✓ | ✓ |
| PRMT | 寄存器对字节置换 | ✓ | ✓ | ✓ | ✓ |
| SEL | 按谓词选择源 | ✓ | ✓ | ✓ | ✓ |
| SGXT | 符号扩展 | ✓ | ✓ | ✓ | ✓ |
| SHFL | Warp 内寄存器 shuffle | ✓ | ✓ | ✓ | ✓ |

### 6.5 Predicate Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| PLOP3 | 谓词逻辑运算（LUT） | ✓ | ✓ | ✓ | ✓ |
| PSETP | 组合谓词并置谓词 | ✓ | ✓ | ✓ | ✓ |
| P2R | 谓词寄存器搬到通用寄存器 | ✓ | ✓ | ✓ | ✓ |
| R2P | 通用寄存器搬到谓词寄存器 | ✓ | ✓ | ✓ | ✓ |

### 6.6 Load/Store Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| FENCE | Shared/Global 内存可见性栅栏 | | | ✓ | ✓ |
| LD | 从通用（generic）内存 load | ✓ | ✓ | ✓ | ✓ |
| LDC | Load 常量内存 | ✓ | ✓ | ✓ | ✓ |
| LDG | 从 Global 内存 load | ✓ | ✓ | ✓ | ✓ |
| LDGDEPBAR | Global load 依赖屏障 | | ✓ | ✓ | ✓ |
| LDGMC | 归约式 load（reducing load） | | | ✓ | ✓ |
| LDGSTS | Global→Shared 异步拷贝（cp.async） | | ✓ | ✓ | ✓ |
| LDL | 从 Local 窗口 load | ✓ | ✓ | ✓ | ✓ |
| LDS | 从 Shared 窗口 load | ✓ | ✓ | ✓ | ✓ |
| LDSM | 从 Shared load 矩阵（元素扩展） | ✓ | ✓ | ✓ | ✓ |
| STSM | 向 Shared store 矩阵 | | | ✓ | ✓ |
| ST | store 到通用内存 | ✓ | ✓ | ✓ | ✓ |
| STG | store 到 Global | ✓ | ✓ | ✓ | ✓ |
| STL | store 到 Local | ✓ | ✓ | ✓ | ✓ |
| STS | store 到 Shared | ✓ | ✓ | ✓ | ✓ |
| STAS | 异步 store 到分布式 Shared（显式同步） | | | ✓ | ✓ |
| SYNCS | Sync 单元 | | | ✓ | ✓ |
| MATCH | 跨线程组匹配寄存器值 | ✓ | ✓ | ✓ | ✓ |
| QSPC | 查询地址空间（Query Space） | ✓ | ✓ | ✓ | ✓ |
| ATOM | 通用内存原子操作 | ✓ | ✓ | ✓ | ✓ |
| ATOMS | Shared 内存原子操作 | ✓ | ✓ | ✓ | ✓ |
| ATOMG | Global 内存原子操作 | ✓ | ✓ | ✓ | ✓ |
| RED | 通用内存归约 | ✓ | ✓ | | |
| REDG | 通用内存归约 | | | ✓ | ✓ |
| REDAS | 异步归约到分布式 Shared（显式同步） | | | ✓ | ✓ |
| CCTL | 缓存控制 | ✓ | ✓ | ✓ | ✓ |
| CCTLL | 缓存控制（Local） | ✓ | ✓ | ✓ | ✓ |
| CCTLT | 纹理缓存控制 | ✓ | ✓ | ✓ | ✓ |
| ERRBAR | 错误屏障 | ✓ | ✓ | ✓ | ✓ |
| MEMBAR | 内存屏障 | ✓ | ✓ | ✓ | ✓ |

### 6.7 Uniform Datapath Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| CREDUX | 耦合归约：向量寄存器→统一寄存器 | | | | ✓ |
| CS2UR | 常量内存 load 到统一寄存器 | | | | ✓ |
| LDCU | 常量内存 load 到统一寄存器 | | | | ✓ |
| R2UR | 向量寄存器→统一寄存器 | ✓ | ✓ | ✓ | ✓ |
| REDUX | 向量寄存器归约到统一寄存器 | | ✓ | ✓ | ✓ |
| S2UR | 特殊寄存器→统一寄存器 | ✓ | ✓ | ✓ | ✓ |
| UBMSK | 统一位域掩码 | ✓ | ✓ | ✓ | ✓ |
| UBREV | 统一位反转 | ✓ | ✓ | ✓ | ✓ |
| UCGABAR_ARV | CGA 屏障同步（arrive） | | | ✓ | ✓ |
| UCGABAR_WAIT | CGA 屏障同步（wait） | | | ✓ | ✓ |
| UCLEA | 常量的有效地址计算 | ✓ | ✓ | ✓ | ✓ |
| UFADD | 统一 FP32 加法 | | | | ✓ |
| UF2F | 统一 浮点↔浮点转换 | | | | ✓ |
| UF2FP | 统一 FP32 下转换并打包 | | ✓ | ✓ | ✓ |
| UF2I | 统一 浮点→整数转换 | | | | ✓ |
| UF2IP | 统一 FP32 下转换到整数并打包 | | | | ✓ |
| UFFMA | 统一 FP32 融合乘加 | | | | ✓ |
| UFLO | 统一查找最高位 1 | ✓ | ✓ | ✓ | ✓ |
| UFMNMX | 统一浮点最小/最大 | | | | ✓ |
| UFMUL | 统一 FP32 乘法 | | | | ✓ |
| UFRND | 统一舍入到整数 | | | | ✓ |
| UFSEL | 统一浮点选择 | | | | ✓ |
| UFSET | 统一浮点比较置值 | | | | ✓ |
| UFSETP | 统一浮点比较置谓词 | | | | ✓ |
| UI2F | 统一整数→浮点转换 | | | | ✓ |
| UI2FP | 统一整数→FP32 转换并打包 | | | | ✓ |
| UI2I | 统一饱和整数→整数转换 | | | | ✓ |
| UI2IP | 统一双饱和整数→整数转换并打包 | | | | ✓ |
| UIABS | 统一整数绝对值 | | | | ✓ |
| UIMNMX | 统一整数最小/最大 | | | | ✓ |
| UIADD3 | 统一整数加法 | ✓ | ✓ | ✓ | ✓ |
| UIADD3.64 | 统一整数加法（64-bit） | ✓ | ✓ | ✓ | ✓ |
| UIMAD | 统一整数乘法 | ✓ | ✓ | ✓ | ✓ |
| UISETP | 统一整数比较置统一谓词 | ✓ | ✓ | ✓ | ✓ |
| ULDC | 常量内存 load 到统一寄存器 | ✓ | ✓ | ✓ | ✓ |
| ULEA | 统一有效地址计算 | ✓ | ✓ | ✓ | ✓ |
| ULEPC | 统一 load 有效 PC | | | ✓ | ✓ |
| ULOP | 统一逻辑运算 | ✓ | ✓ | ✓ | ✓ |
| ULOP3 | 统一 3 输入逻辑运算 | ✓ | ✓ | ✓ | ✓ |
| ULOP32I | 统一逻辑运算（立即数） | ✓ | ✓ | ✓ | ✓ |
| UMOV | 统一移动 | ✓ | ✓ | ✓ | ✓ |
| UP2UR | 统一谓词→统一寄存器 | ✓ | ✓ | ✓ | ✓ |
| UPLOP3 | 统一谓词逻辑运算 | ✓ | ✓ | ✓ | ✓ |
| UPOPC | 统一位计数 | ✓ | ✓ | ✓ | ✓ |
| UPRMT | 统一字节置换 | ✓ | ✓ | ✓ | ✓ |
| UPSETP | 统一谓词逻辑运算 | ✓ | ✓ | ✓ | ✓ |
| UR2UP | 统一寄存器→统一谓词 | ✓ | ✓ | ✓ | ✓ |
| USEL | 统一选择 | ✓ | ✓ | ✓ | ✓ |
| USETMAXREG | 释放/回收/分配寄存器（register 动态分配） | | | ✓ | ✓ |
| USGXT | 统一符号扩展 | ✓ | ✓ | ✓ | ✓ |
| USHF | 统一漏斗移位 | ✓ | ✓ | ✓ | ✓ |
| USHL | 统一左移 | ✓ | ✓ | ✓ | ✓ |
| USHR | 统一右移 | ✓ | ✓ | ✓ | ✓ |
| UGETNEXTWORKID | 统一获取下一 Work ID | | | | ✓ |
| UMEMSETS | 初始化 Shared 内存 | | | | ✓ |
| UREDGR | 统一 Global 内存归约（带 release） | | | | ✓ |
| USTGR | 统一 store 到 Global（带 release） | | | | ✓ |
| UVIADD | 统一 SIMD 整数加法 | | | | ✓ |
| UVIMNMX | 统一 SIMD 整数最小/最大 | | | | ✓ |
| UVIRTCOUNT | 虚拟资源管理 | | | | ✓ |
| VOTEU | SIMD 线程组投票，结果写统一寄存器 | ✓ | ✓ | ✓ | ✓ |

### 6.8 Warpgroup Instructions（Hopper 专属）

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| BGMMA | 跨 warp 位矩阵乘加 | | | ✓ | |
| HGMMA | 跨 warpgroup 矩阵乘加（FP16/BF16） | | | ✓ | |
| IGMMA | 跨 warpgroup 整数矩阵乘加 | | | ✓ | |
| QGMMA | 跨 warpgroup FP8 矩阵乘加 | | | ✓ | |
| WARPGROUP | Warpgroup 同步 | | | ✓ | |
| WARPGROUPSET | 设置 warpgroup 计数器 | | | ✓ | |

> Blackwell 用 `tcgen05` 系列（见 6.10 Tensor Core Memory）取代 Hopper 的 `wgmma` 体系。

### 6.9 Tensor Memory Access Instructions（TMA，Hopper+）

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| UBLKCP | 批量数据拷贝 | | | ✓ | ✓ |
| UBLKPF | 批量数据预取 | | | ✓ | ✓ |
| UBLKRED | 从 Shared 批量拷贝并归约 | | | ✓ | ✓ |
| UTMACCTL | TMA 缓存控制 | | | ✓ | ✓ |
| UTMACMDFLUSH | TMA 命令 flush | | | ✓ | ✓ |
| UTMALDG | 张量 load：Global→Shared | | | ✓ | ✓ |
| UTMAPF | 张量预取 | | | ✓ | ✓ |
| UTMAREDG | 张量 store：Shared→Global（带归约） | | | ✓ | ✓ |
| UTMASTG | 张量 store：Shared→Global | | | ✓ | ✓ |

### 6.10 Tensor Core Memory Instructions（tcgen05，Blackwell 专属）

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| LDT | 从 Tensor Memory load 矩阵到寄存器堆 | | | | ✓ |
| LDTM | 从 Tensor Memory load 矩阵到寄存器堆 | | | | ✓ |
| STT | 从寄存器堆 store 矩阵到 Tensor Memory | | | | ✓ |
| STTM | 从寄存器堆 store 矩阵到 Tensor Memory | | | | ✓ |
| UTCATOMSWS | 对 SW 状态寄存器执行原子操作 | | | | ✓ |
| UTCBAR | Tensor Core 屏障 | | | | ✓ |
| UTCCP | Shared→Tensor Memory 异步拷贝 | | | | ✓ |
| UTCHMMA | 统一矩阵乘加（FP16/BF16） | | | | ✓ |
| UTCIMMA | 统一矩阵乘加（整数） | | | | ✓ |
| UTCOMMA | 统一矩阵乘加（FP4/OCP 格式） | | | | ✓ |
| UTCQMMA | 统一矩阵乘加（FP8） | | | | ✓ |
| UTCSHIFT | 移动 Tensor Memory 中的元素 | | | | ✓ |

### 6.11 Texture Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| TEX | 纹理采样 | ✓ | ✓ | ✓ | ✓ |
| TLD | 纹理 load | ✓ | ✓ | ✓ | ✓ |
| TLD4 | 纹理 load 4（gather） | ✓ | ✓ | ✓ | ✓ |
| TMML | 纹理 MipMap 层级 | ✓ | ✓ | ✓ | ✓ |
| TXD | 带导数的纹理采样 | ✓ | ✓ | ✓ | ✓ |
| TXQ | 纹理查询 | ✓ | ✓ | ✓ | ✓ |

### 6.12 Surface Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| SUATOM | 表面内存原子操作 | ✓ | ✓ | ✓ | ✓ |
| SULD | 表面 load | ✓ | ✓ | ✓ | ✓ |
| SURED | 表面内存归约 | ✓ | ✓ | ✓ | ✓ |
| SUST | 表面 store | ✓ | ✓ | ✓ | ✓ |

### 6.13 Control Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| ACQBULK | 等待 Bulk release 状态（warp 状态） | | | ✓ | ✓ |
| ACQSHMINIT | 等待 Shared 内存初始化 release 状态 | | | | ✓ |
| BMOV | 移动收敛屏障状态 | ✓ | ✓ | ✓ | ✓ |
| BPT | 断点/陷阱 | ✓ | ✓ | ✓ | ✓ |
| BRA | 相对分支 | ✓ | ✓ | ✓ | ✓ |
| BREAK | 跳出指定收敛屏障 | ✓ | ✓ | ✓ | ✓ |
| BRX | 相对间接分支 | ✓ | ✓ | ✓ | ✓ |
| BRXU | 基于统一寄存器偏移的相对分支 | ✓ | ✓ | ✓ | ✓ |
| BSSY | 设置收敛同步点（barrier set） | ✓ | ✓ | ✓ | ✓ |
| BSYNC | 在收敛屏障上同步线程 | ✓ | ✓ | ✓ | ✓ |
| CALL | 调用函数 | ✓ | ✓ | ✓ | ✓ |
| CGAERRBAR | CGA 错误屏障 | | | ✓ | ✓ |
| ELECT | 选举一个 leader 线程 | | | ✓ | ✓ |
| ENDCOLLECTIVE | 重置 MCOLLECTIVE 掩码 | | | ✓ | ✓ |
| EXIT | 退出程序 | ✓ | ✓ | ✓ | ✓ |
| JMP | 绝对跳转 | ✓ | ✓ | ✓ | ✓ |
| JMX | 绝对间接跳转 | ✓ | ✓ | ✓ | ✓ |
| JMXU | 基于统一寄存器偏移的绝对跳转 | ✓ | ✓ | ✓ | ✓ |
| KILL | 终止线程 | ✓ | ✓ | ✓ | ✓ |
| NANOSLEEP | 挂起执行（纳秒级休眠） | ✓ | ✓ | ✓ | ✓ |
| PREEXIT | 依赖任务启动提示 | | | ✓ | ✓ |
| RET | 从子程序返回 | ✓ | ✓ | ✓ | ✓ |
| RPCMOV | PC 寄存器移动 | ✓ | ✓ | ✓ | ✓ |
| RTT | 从陷阱返回（Return From Trap） | ✓ | | | |
| WARPSYNC | 在 warp 内同步线程 | ✓ | ✓ | ✓ | ✓ |
| YIELD | 让出控制 | ✓ | ✓ | ✓ | ✓ |

### 6.14 Miscellaneous Instructions

| Opcode | 描述 | T | A | H | B |
| --- | --- | :-: | :-: | :-: | :-: |
| B2R | 屏障搬到寄存器 | ✓ | ✓ | ✓ | ✓ |
| BAR | 屏障同步（`__syncthreads`） | ✓ | ✓ | ✓ | ✓ |
| CS2R | 特殊寄存器搬到寄存器（常量延迟） | ✓ | ✓ | ✓ | ✓ |
| DEPBAR | 依赖屏障（等待记分板） | ✓ | ✓ | ✓ | ✓ |
| GETLMEMBASE | 获取 Local 内存基址 | ✓ | ✓ | ✓ | ✓ |
| LEPC | Load 有效 PC | ✓ | ✓ | ✓ | ✓ |
| NOP | 空操作 | ✓ | ✓ | ✓ | ✓ |
| PMTRIG | 性能监视触发 | ✓ | ✓ | ✓ | ✓ |
| R2B | 寄存器搬到屏障 | ✓ | | | |
| S2R | 特殊寄存器搬到寄存器（变延迟） | ✓ | ✓ | ✓ | ✓ |
| SETCTAID | 设置 CTA ID | ✓ | ✓ | ✓ | ✓ |
| SETLMEMBASE | 设置 Local 内存基址 | ✓ | ✓ | ✓ | ✓ |
| VOTE | SIMT 线程组投票 | ✓ | ✓ | ✓ | ✓ |

---

## 7. 跨架构演进要点

从编译器/算子实现角度，各代最关键的指令级变化：

### Turing (sm_75)
- 确立 Volta+ 的 16 字节定长编码 + 显式控制码调度模型。
- 引入 **Uniform Datapath**（URx / `UIADD3` / `ULDC` 等），标量运算下沉到独立流水线。
- Tensor Core：`HMMA` / `IMMA` / `BMMA`（FP16 / INT / 1-bit）。
- 独有：`RTT`（从陷阱返回）、`R2B`（寄存器→屏障）。

### Ampere + Ada (sm_80/86/89)
- 新增 **`LDGSTS`**：Global→Shared **异步拷贝**（对应 PTX `cp.async`），无需经过寄存器堆，是软件流水（software pipelining）的基础。
- 配套 `LDGDEPBAR`（异步拷贝依赖屏障）。
- 新增 **`DMMA`**（FP64 Tensor Core）、`HMNMX2`。
- 新增 `REDUX`（warp 内向量寄存器归约到统一寄存器）、`UF2FP`、`I2FP`/`F2IP` 打包转换。
- 增加统一谓词寄存器 `UPx`。

### Hopper (sm_90)
- **Warpgroup MMA（wgmma）**：`HGMMA` / `IGMMA` / `QGMMA`（FP8）/ `BGMMA`，跨 warpgroup（128 线程）协同的大矩阵乘加；配 `WARPGROUP` / `WARPGROUPSET` 同步。
- **TMA（Tensor Memory Accelerator）**：`UTMALDG` / `UTMASTG` / `UTMAREDG` / `UTMAPF` 及 `UBLKCP` 等，硬件驱动的张量/批量异步拷贝，支持多维 tensor 与 descriptor（`desc[URx]` / `gdesc[URx]`）。
- **Cluster / CGA**：`UCGABAR_ARV` / `UCGABAR_WAIT` / `CGAERRBAR`，跨 CTA 集群同步与分布式 Shared（`STAS` / `REDAS`）。
- 新增 `FENCE`（内存可见性栅栏）、`LDGMC`（归约式 load）、`LDSM`/`STSM` 矩阵搬运、`ELECT`（选 leader）、`USETMAXREG`（寄存器动态分配）、SIMD 子字整数 `VIADD`/`VIMNMX` 等。

### Blackwell (sm_100/120)
- **第五代 Tensor Core（tcgen05）**：引入独立的 **Tensor Memory（`tmem[URx]`）**；MMA 改用 `UTCHMMA` / `UTCIMMA` / `UTCQMMA`（FP8）/ `UTCOMMA`（FP4），配 `UTCCP`（Shared→Tensor Memory 拷贝）、`UTCBAR`、`UTCSHIFT`、`LDT/LDTM`、`STT/STTM`。
- 新增 **`OMMA`（FP4）/ `QMMA`（FP8）** warp 级 MMA；`FADD2`/`FMUL2`/`FFMA2` 等成对 FP32、`FMNMX3` 3 输入 min/max。
- **统一浮点数据通路大扩展**：`UFADD`/`UFMUL`/`UFFMA`/`UFMNMX`/`UFSETP`/`UF2F`/`UI2F` 等，标量浮点全面下沉到 Uniform Datapath。
- 新增 `UGETNEXTWORKID`（持久化 kernel 取工作）、`UMEMSETS`、`UVIRTCOUNT`（虚拟资源管理）、`USTGR`/`UREDGR`（带 release 的统一 store/归约）、`ACQSHMINIT`。
- 注意：Blackwell 指令表**不再列出** `BMMA`（1-bit MMA）与 `RED`（改为 `REDG`）。

---

## 8. 常用指令详解与示例

> 以下选取高频指令做说明，示例采用 nvdisasm 反汇编风格。

### 8.1 IMAD —— 整数乘加（最高频指令之一）
`ptxas` 大量用 `IMAD` 做地址计算与整数运算，甚至用 `IMAD.MOV`/`IMAD R, R, 0x1, R` 模拟加法/移动以填满整数流水线。
```
IMAD R0, R1, R2, R3          // R0 = R1*R2 + R3
IMAD.WIDE R2, R4, R5, R6     // 64-bit 结果写入 R2:R3（常用于指针运算）
IMAD.MOV.U32 R0, RZ, RZ, R5  // 等价 MOV R0, R5
```

### 8.2 IADD3 —— 3 输入整数加法
```
IADD3 R0, R1, R2, R3         // R0 = R1 + R2 + R3
IADD3 R0, P0, R1, R2, RZ     // 同时把进位写入谓词 P0（用于扩展精度）
```

### 8.3 LOP3 —— 任意 3 输入位运算（LUT）
`LOP3.LUT` 用 8-bit 立即数作真值表，一条指令实现任意三输入布尔函数。
```
LOP3.LUT R0, R1, R2, R3, 0xE8, !PT   // 立即数 0xE8 = majority(a,b,c) 的真值表
```

### 8.4 LEA —— 有效地址计算
```
LEA R0, R1, R2, 0x2          // R0 = (R1 << 2) + R2，常用于数组索引
LEA.HI R3, R1, R2, R4, 0x4   // 处理 64-bit 地址高位
```

### 8.5 LDG / STG —— 全局内存读写
```
LDG.E.SYS R3, [R2+0x4]       // .E 扩展寻址, .SYS 系统级作用域
LDG.E.128 R4, [R2]           // 一次读 128-bit（向量化访存）
STG.E [R6], R4               // 写回 global
```
- 常见修饰符：`.E`（64-bit 地址）、`.CI`/`.CG`/`.CA`（缓存策略）、`.STRONG.SYS`/`.WEAK`（内存序与作用域）。

### 8.6 LDGSTS —— 异步拷贝（Ampere+）
```
LDGSTS.E.BYPASS.128 [R5], [R2]   // Global→Shared 直达, 不占寄存器
// ... 计算 ...
LDGDEPBAR                        // 等待异步拷贝组完成
```

### 8.7 S2R / CS2R —— 读取特殊寄存器
```
S2R R0, SR_TID.X             // 读 threadIdx.x（变延迟，需 write barrier）
S2R R1, SR_CTAID.X           // 读 blockIdx.x
CS2R R2, SRZ                 // 常量延迟版本
```

### 8.8 分支与收敛（BSSY / BSYNC / BRA）
Volta+ 采用显式收敛屏障管理线程发散：
```
      BSSY B0, `(.L_reconverge)   // 设置收敛点
@P0   BRA  `(.L_else)             // 条件分支
      ...
.L_reconverge:
      BSYNC B0                    // 在收敛点重新同步 warp
```

### 8.9 HMMA / wgmma —— Tensor Core 矩阵乘加
```
HMMA.16816.F32 R0, R8, R12, R0   // 16x8x16 FP16→FP32 MMA（warp 级）
// Hopper warpgroup MMA:
HGMMA.64x128x16.F32 ...          // 跨 warpgroup 的大 tile MMA
```

### 8.10 BAR / WARPSYNC —— 同步
```
BAR.SYNC 0x0                 // __syncthreads()：CTA 内全线程屏障
WARPSYNC 0xffffffff          // __syncwarp()：warp 内同步（指定 mask）
```

---

## 9. 工具：如何生成与查看 SASS

CUDA Binary Utilities 提供两个反汇编工具：

### 9.1 cuobjdump
- 接受 **cubin 与宿主二进制**（可执行文件、目标文件、静态库、fatbin）。
- 可从宿主程序中抽取并反汇编 SASS、抽取 PTX。
```powershell
# 反汇编可执行/cubin 中的 SASS
cuobjdump -sass a.exe
# 抽取 PTX
cuobjdump -ptx a.exe
# 列出 ELF/段信息
cuobjdump -elf a.cubin
```

### 9.2 nvdisasm
- 只接受 **cubin**，但输出更丰富：支持控制流分析、CFG 可视化、行号映射等高级显示。
```powershell
# 反汇编 cubin
nvdisasm a.cubin
# 生成控制流图（DOT，可用 Graphviz 渲染）
nvdisasm -cfg a.cubin > cfg.dot
# 显示源码行号映射
nvdisasm -g a.cubin
```

### 9.3 从源码直接编译产出 SASS
```powershell
# 编译到 cubin
nvcc -cubin -arch=sm_90 kernel.cu -o kernel.cubin
# 直接输出 PTX 与 SASS
nvcc -ptx  -arch=sm_90 kernel.cu -o kernel.ptx
nvcc -arch=sm_90 -Xptxas -v --cubin kernel.cu   # -Xptxas -v 打印寄存器/共享内存占用
```

> 两工具对比：`cuobjdump` 输入面更广（含宿主二进制），`nvdisasm` 输出面更强（控制流分析、高级显示）。

---

## 10. 参考资料

1. **NVIDIA CUDA Binary Utilities, Release 13.3** —— Chapter 6 “Instruction Set Reference”（Turing / Ampere+Ada / Hopper / Blackwell 指令表，本文档主数据来源）。本仓库文件：`CUDA_Binary_Utilities.pdf`。
2. NVIDIA CUDA Binary Utilities 在线文档：<https://docs.nvidia.com/cuda/cuda-binary-utilities/index.html>
3. PNF Software, “Reversing Nvidia GPU’s SASS code – JEB in Action”：寄存器模型、编码格式、指令分类与调度信息（补充来源）。<https://www.pnfsoftware.com/blog/reversing-nvidia-cuda-sass-code/>
4. CuAssembler UserGuide：控制码（stall / yield / reuse / scoreboard barrier）字段拆解（补充来源）。<https://github.com/cloudcores/CuAssembler>
5. NVIDIA 开发者论坛关于 SASS 控制码 `{ }` 与谓词/双发射的讨论（补充来源）。

---

> **免责声明**：SASS 为 NVIDIA 未完整公开的私有 ISA。第 4 节控制码、第 3 节编码细节、第 8 节部分修饰符语义等标注为“补充”的内容来自社区逆向工程，可能与真实硬件行为存在偏差，且随驱动/架构版本变化。功能类别与 opcode 列表（第 6 节）以官方 CUDA Binary Utilities 13.3 为准。
