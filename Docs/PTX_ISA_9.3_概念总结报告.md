# PTX ISA 9.3 概念总结报告


---

## 1 Introduction（引言）

### 1.1 Scalable Data-Parallel Computing using GPUs（使用 GPU 的可扩展数据并行计算）

**是什么？**  
PTX（Parallel Thread Execution）是 NVIDIA 定义的一种低级并行线程执行虚拟机和指令集架构（ISA）。它将 GPU 暴露为数据并行计算设备。

**为什么需要？**  
GPU 凭借高度并行、多线程、众核的架构，拥有极高的计算吞吐和显存带宽。数据并行计算模型（同一程序在大量数据上并行执行）完美契合 GPU 架构特点——大量算术运算可隐藏内存延迟，对复杂控制流的需求较低。

**如何使用？**  
PTX 程序在安装时（install time）由 PTX-to-GPU 编译器翻译为目标硬件原生指令。开发者通过 CUDA 或 C/C++ 编写高层代码，编译器将其编译为 PTX，再由驱动翻译执行。

**注意点：**
- PTX 是一层中间表示（IR），不是直接在硬件上执行的机器码。
- 理解 PTX 有助于深度性能调优，但日常开发通常不需手写 PTX。

---

### 1.2 Goals of PTX（PTX 的设计目标）

**核心目标：**
1. **稳定的 ISA**：跨越多代 GPU，保持向前兼容。
2. **性能**：编译后的应用性能接近原生 GPU 性能。
3. **机器无关性**：为 C/C++/CUDA 编译器提供统一目标。
4. **代码分发 ISA**：应用和中间件厂商可以分发 PTX 代码而非绑定特定 GPU。
5. **可扩展性**：从单 SM 到多 SM 均可运行。

**注意点（学术/工业）：**
- PTX 的"稳定性"意味着旧版本 PTX 代码可在新硬件上运行（向前兼容），但新 PTX 特性可能不被旧硬件支持。
- 分发 PTX 比分发 SASS（原生机器码）更具可移植性，但会有一次额外的 JIT 编译开销。

---

### 1.3 PTX ISA Version 9.3（版本 9.3 新特性）

**主要新增：**
- `mma_throughput` pragma（矩阵运算吞吐量提示）
- `clmad` 指令（无进位乘加）
- `mbarrier` 增强：`.phase_type`、`reportPredicate`/`reportValue`、`.layout` 限定符、`check_layout` 指令
- `multimem.st.async` 和 `multimem.red.async` 指令
- `cp.async.bulk`/`cp.reduce.async.bulk` 新增 `.sem` 和 `.scope` 限定符
- **Fabric 指令族**：`fabric.try_get`、`fabric.try_put`、`fabric.try_red`、`fabric.try_pullred`、`fabric.wait`、`fabric.submit`
- `fence.proxy.to_proxykind::from_proxykind_fabric` 
- `.language` 指令

**注意点：**
- 9.3 版本重点强化了**异步数据搬运**与**跨节点 fabric 通信**能力，反映了 NVIDIA 在大规模分布式 AI 训练中的架构演进。
- 新增的 fabric 指令直接面向多 GPU 互联场景（NVLink/NVSwitch），是学术研究大规模并行算法时需关注的底层能力。

---

### 1.4 Document Structure（文档结构）

文档按以下逻辑组织：Programming Model → Machine Model → Syntax → State Spaces/Types/Variables → Instruction Operands → ABI → Instruction Set → Special Registers → Directives → Release Notes。

---

## 2 Programming Model（编程模型）

### 2.1 A Highly Multithreaded Coprocessor（高度多线程的协处理器）

**是什么？**  
GPU 被视为 CPU 的协处理器（coprocessor）。应用中可并行的、计算密集的部分被卸载到 GPU 上执行。

**为什么？**  
将数据并行的计算密集任务卸载到 GPU，可利用其数千个核心的并行能力获得显著加速。

**如何使用？**  
将可独立执行的函数编译为 **kernel（核函数）**，GPU 以大量线程并行执行同一个 kernel。

---

### 2.2 Thread Hierarchy（线程层次结构）

#### 2.2.1 Cooperative Thread Arrays（CTA，协作线程数组）

**是什么？**  
CTA 是一组可以相互协作的线程集合，在同一 SM（流多处理器）上并发执行。CTA 内线程可通过共享内存通信并使用 barrier 同步。

**关键特性：**
- CTA 是 1D/2D/3D 的线程网格
- 每个线程通过 `%tid`（线程 ID）标识
- CTA 内线程通过 `bar` 指令进行同步

**注意点：**
- CTA 就是 CUDA 中的 thread block。
- CTA 大小直接影响 SM 占用率（occupancy），过大可能寄存器/shared memory 不足。
- Cooperative thread arrays (CTAs) implement CUDA thread blocks
- Clusters implement CUDA thread block clusters

#### 2.2.2 Cluster of Cooperative Thread Arrays（CTA 集群）

**是什么？**  
Cluster 是多个 CTA 的组合，集群内的 CTA 可以跨 SM 通过分布式共享内存（Distributed Shared Memory）通信。

**为什么需要？**  
传统模型中不同 CTA 之间只能通过 global memory 通信，延迟很高。Cluster 允许相邻 CTA 直接访问彼此的 shared memory。

**注意点（sm_90+）：**
- Cluster 是 Hopper（sm_90）架构引入的新概念。
- 需要 `.reqnctapercluster` 或 `.explicitcluster` 指令显式指定集群大小。
- 用 `mapa` 和 `getctarank` 指令进行跨 CTA 地址映射。

#### 2.2.3 Grid of Clusters（集群网格）

**是什么？**  
执行一个 kernel 的全部线程构成一个 Grid。Grid 由 Cluster 组成，Cluster 由 CTA 组成。

**层次关系：**  
`Thread → Warp → CTA (Block) → Cluster → Grid`

---

### 2.3 Memory Hierarchy（内存层次结构）

**是什么？**  
PTX 定义了多层内存层次，从快到慢：

| 层级 | 作用域 | 特点 |
|------|--------|------|
| Register | 单线程 | 最快，每个线程私有 |
| Shared Memory | CTA 内 | 低延迟，CTA 内线程可共享 |
| Distributed Shared | Cluster 内 | Cluster 内 CTA 间可访问 |
| L1/L2 Cache | 自动管理 | 对 global/local 加速 |
| Local Memory | 单线程 | 寄存器溢出到显存 |
| Global Memory | 所有线程 | 最大但延迟高 |
| Constant Memory | 所有线程 | 只读，有缓存 |
| Texture Memory | 所有线程 | 只读，专用缓存和硬件过滤 |

**注意点：**
- Shared memory 和 L1 cache 在物理上共享同一块 SRAM，可通过配置调整分配比例。
- 寄存器压力过大会导致 spill 到 local memory（实际存储在 global memory），性能急剧下降。

---

## 3 PTX Machine Model（PTX 机器模型）

### 3.1 A Set of SIMT Multiprocessors（一组 SIMT 多处理器）

**是什么？**  
GPU 由多个 SIMT（Single-Instruction, Multiple-Thread）多处理器组成。每个多处理器将线程映射到标量处理核心，以 **warp**（32个线程为一组）为单位调度执行。

**SIMT 与 SIMD 的区别：**
- SIMD：软件显式操作向量宽度，分支需手动管理
- SIMT：每个线程独立编程，分支由硬件自动管理（divergence 时串行执行各分支路径）

**注意点：**
- Warp 内线程 divergence（分支发散）会导致串行执行，严重影响性能。
- 设计 kernel 时应尽量保证 warp 内线程走相同执行路径。
- 不同 warp 之间是完全独立的，无论代码路径是否相同。

---

### 3.2 Independent Thread Scheduling（独立线程调度）

**是什么？**  
从 Volta（sm_70）架构开始，GPU 为每个线程维护独立的程序计数器和调用栈，允许 warp 内线程在子 warp 粒度上 diverge 和 reconverge。

**为什么需要？**  
旧架构中 warp 共享一个 PC，导致 warp-synchronous 代码（如无同步的 intra-warp reduction）容易产生隐式依赖甚至死锁。

**注意点：**
- **所有依赖 warp-synchronous 假设的代码必须审查**（Volta 之后不再保证 warp 内 lockstep 执行）。
- 使用 `__syncwarp()` 或 PTX 的 `bar.warp.sync` 显式同步 warp 内线程。
- 这一变化对细粒度锁/互斥算法的正确性影响巨大。

---

### 3.3 Scoreboard 与 Warp 调度器（指令发射与依赖跟踪）

**是什么？**
Scoreboard（记分板）是一种硬件数据结构，用于跟踪寄存器/资源的依赖关系，判断一条指令是否可以安全发射。它最早由 CDC 6600（1964，Seymour Cray 设计）引入，是乱序执行处理器中解决数据冒险的核心机制。

**GPU 中的 Scoreboard：Warp 调度器**

GPU 的每个 SM 内部有一个 **Warp Scoreboard**，它是传统 Scoreboard 的大规模并行变体：

```
┌─────────────────────────────────────────────────────────────┐
│  SM Warp Scoreboard（以 Hopper SM 为例，最多 64 warps）  │
│                                                             │
│  Warp 0:  ready   ← 所有源寄存器就绪，可发射               │
│  Warp 1:  stall   ← 等待 global memory 响应（~200 周期）  │
│  Warp 2:  ready   ← 所有源寄存器就绪                      │
│  Warp 3:  stall   ← 等待 shared memory bank conflict 解除 │
│  Warp 4:  ready   ← 可发射                                 │
│  ...                                                        │
│  Warp 47: stall   ← 等待 bar.sync（其他 warp 未到达）      │
│                                                             │
│  调度器每周期：从 ready warps 中选取 1-4 个发射           │
└─────────────────────────────────────────────────────────────┘
```

**Scoreboard 解决的三种数据冒险：**

| 冒险类型 | 含义 | GPU 中的处理方式 |
|---------|------|----------------|
| **RAW**（Read After Write） | 指令 B 读寄存器 R，但指令 A 还没写完 R | B 所在的 warp 进入 stall，等 A 写回 R 后唤醒 |
| **WAR**（Write After Read） | 指令 B 写寄存器 R，但指令 A 还没读完 R | GPU 通过寄存器重命名（每线程独立寄存器）天然消除 |
| **WAW**（Write After Write） | 两条指令都写同一寄存器 | GPU 通过寄存器重命名天然消除 |

> **关键差异**：CPU 需要复杂的 Tomasulo 算法做寄存器重命名来消除 WAR/WAW；GPU 因为每个线程有独立寄存器文件（寄存器不被不同线程共享），天然不存在跨线程的 WAR/WAW，因此 GPU 的 Scoreboard 比 CPU 简单得多。

**Warp Scoreboard 的发射算法：**

```
每周期：
  for each warp in scoreboard:
    1. 检查该 warp 的下一条指令的源寄存器是否全部就绪
       → 若有未就绪：该 warp 继续 stall
       → 若全部就绪：该 warp 进入 ready 队列

  2. 从 ready 队列中选取 warp（调度策略：轮转/优先级/LRU）
  3. 发射该 warp 的指令到执行管线
  4. 记录该指令的目标寄存器，标记为"正在被写入"

  5. 当执行结果写回时：
     → 清除目标寄存器的"正在写入"标记
     → 唤醒所有等待该寄存器的 warp
```

**这就是 GPU 隐藏内存延迟的核心机制**：当某个 warp 因 global memory 访问而 stall（~200 周期）时，调度器无缝切换到另一个 ready warp 执行——通过大量 warp 的并行来掩盖单次内存访问的高延迟。

**Occupancy 与 Scoreboard 的关系：**

| 概念 | 与 Scoreboard 的联系 |
|------|---------------------|
| **Occupancy（占用率）** | 每 SM 上活跃的 warp 数。warp 越多，ready 队列越满，调度器越容易找到可发射的 warp |
| **寄存器压力** | 每线程寄存器越多 → 每 SM 可容纳的 warp 越少 → Scoreboard 中 ready warp 不足 → 延迟无法隐藏 |
| **ILP（指令级并行）** | 单 warp 内多条独立指令可连续发射，减少 stall |

**Scoreboard 的历史演进与业界现状：**

| 时代 | 方案 | 代表 |
|------|------|------|
| 1964 | 原始 Scoreboard（集中式，无重命名） | CDC 6600 |
| 1967 | Tomasulo 算法（+ 寄存器重命名） | IBM System/360 Model 91 |
| 1990s | Reservation Station + 重命名 | Intel P6 (Pentium Pro) |
| 2000s | 分布式发射队列 | Intel Core / AMD K8 |
| 2006+ | GPU Warp Scoreboard | NVIDIA Tesla (G80) |
| 2017+ | 独立线程 Scoreboard | NVIDIA Volta+ (每线程 PC + 调度) |
| 现在 | 超宽统一调度器 | Apple M 系列 (8+ 宽发射) |

- **嵌入式 CPU**（ARM Cortex-M、RISC-V 简单核）：仍直接使用传统 Scoreboard，因为面积小、功耗低
- **高性能 CPU**（Intel/AMD/Apple）：使用 Tomasulo 变体（Reservation Station + 寄存器重命名）
- **GPU**：Warp Scoreboard 是 GPU 性能的核心支撑，也是理解 occupancy、latency hiding 的关键
- **学术界**：Patterson & Hennessy《计算机组成与设计》中的标配内容，所有计算机体系结构课程的基础

**注意点：**
- GPU 的 Scoreboard 是**per-SM**的——不同 SM 上的 warp 互不影响。
- Warp stall 的原因不仅包括寄存器依赖，还包括 memory 未就绪、barrier 等待、shared memory bank conflict 等。
- 高 occupancy 不一定等于高性能——如果所有 warp 都在等同一个 global memory 地址（如原子操作热点），ready 队列也会空。
- **设计启示**：设计 kernel 时，保证每 SM 上有足够多的活跃 warp（通常建议 ≥ 4-8 个）是隐藏延迟的前提条件。

---

### 3.4 On-chip Shared Memory（片上共享内存）

**是什么？**  
每个多处理器包含四种片上内存：
1. 每个处理核心一组 32 位寄存器
2. 并行数据缓存（Shared Memory）
3. 只读常量缓存（Constant Cache）
4. 只读纹理缓存（Texture Cache）

**注意点：**
- 一个 SM 能处理多少 block 取决于每线程寄存器数和每 block shared memory 大小。
- 如果寄存器或 shared memory 不够处理至少一个 block，kernel 启动会失败。

---

## 4 Syntax（语法）

### 4.1 Source Format（源码格式）

PTX 源码是 ASCII 文本，以 `\n` 分行，大小写敏感，关键字用小写。每个模块必须以 `.version` 和 `.target` 指令开头。

### 4.2 Comments（注释）

使用 C/C++ 风格：`/* ... */` 和 `// ...`。

### 4.3 Statements（语句）

#### 4.3.1 Directive Statements（伪指令语句）

以点号（`.`）开头，如 `.reg`、`.global`、`.shared`、`.entry`、`.func` 等。用于声明变量、函数和控制编译行为。

#### 4.3.2 Instruction Statements（指令语句）

格式：`@predicate opcode.type dest, src1, src2, ...;`

**关键特性：**
- 可选的前卫谓词（guard predicate）`@p` 控制条件执行
- 目标操作数在前，源操作数在后
- 所有语句以分号结尾

### 4.4 Identifiers（标识符）

遵循扩展 C++ 规则，支持 `%` 前缀（用于避免用户定义名与编译器生成名冲突）。预定义标识符如 `%tid`、`%ntid`、`%ctaid` 等。

### 4.5 Constants（常量）

#### 4.5.1 Integer Constants
支持十进制、十六进制（`0x`前缀）、八进制（`0`前缀）、二进制（`0b`前缀），可带 `U` 后缀表示无符号。

#### 4.5.2 Floating-Point Constants
遵循 C/C++ 规则，支持十六进制浮点表示（`0f`/`0d`前缀后跟 IEEE 754 hex 编码）。

#### 4.5.3 Predicate Constants
`True`(1) 和 `False`(0)。

#### 4.5.4 Constant Expressions
支持编译时求值的常量表达式，可用于数组大小等。

#### 4.5.5-4.5.6 表达式求值规则
运算符优先级和类型提升规则与 C 语言类似。

---

## 5 State Spaces, Types, and Variables（状态空间、类型和变量）

### 5.1 State Spaces（状态空间）

**是什么？**  
PTX 将所有存储抽象为"状态空间"，每个空间有不同的访问特性、作用域和性能特征。

| 状态空间 | PTX 名称 | 说明 |
|----------|---------|------|
| Register | `.reg` | 快速，线程私有，数量有限 |
| Special Register | `.sreg` | 预定义只读寄存器（如 %tid） |
| Constant | `.const` | 只读，有缓存 |
| Global | `.global` | 所有线程可访问的显存 |
| Local | `.local` | 线程私有，实际在显存上 |
| Parameter | `.param` | 函数参数传递 |
| Shared | `.shared` | CTA 内共享的片上内存 |
| Texture | `.tex` | 纹理内存（已弃用） |

#### 5.1.1 Register State Space

- 速度最快，虚拟寄存器可声明任意数量（编译器分配物理寄存器）
- 不可取地址（不可用指针指向）
- 溢出到 local memory 会极大降低性能

#### 5.1.2 Special Register State Space

- 只读，包含线程/CTA/Grid 的标识信息、时钟等
- 如 `%tid.x`、`%ctaid.x`、`%clock` 等

#### 5.1.3 Constant State Space

- 由 host 初始化，kernel 执行期间只读
- 通过专用缓存访问，访问模式均匀时性能极高
- Banked constant（已弃用）

#### 5.1.4 Global State Space

- 所有线程可读写的显存
- 延迟最高（>100 时钟周期），但容量最大
- 支持原子操作

#### 5.1.5 Local State Space

- 每线程私有，物理上在显存
- 用于寄存器溢出和大型局部数组
- 延迟与 global 相当

#### 5.1.6 Parameter State Space

- 用于 kernel 入口参数和设备函数参数传递
- Kernel parameters 通过 `.param` 空间传入，支持 `.ptr` 属性标注指针参数

##### 5.1.6.1-5.1.6.4 Kernel/Device Function Parameters
- Kernel 参数由 host 设置，kernel 内只读
- Device function 参数用于函数调用的值传递

#### 5.1.7 Shared State Space

- CTA 内所有线程共享的快速片上内存
- 用于线程间数据共享和协作
- 支持 `.shared::cta` 和 `.shared::cluster`

#### 5.1.8 Texture State Space (deprecated)

已被统一内存访问模型取代。

---

### 5.2 Types（类型）

#### 5.2.1 Fundamental Types

| 类型类别 | 具体类型 |
|----------|---------|
| 有符号整数 | `.s8, .s16, .s32, .s64` |
| 无符号整数 | `.u8, .u16, .u32, .u64` |
| 浮点 | `.f16, .f32, .f64` |
| Bits | `.b8, .b16, .b32, .b64, .b128` |
| 谓词 | `.pred` |

#### 5.2.2 Restricted Use of Sub-Word Sizes

`.b8`、`.u8`、`.s8` 和 16 位类型在寄存器中受限使用——寄存器最小为 32 位宽，sub-word 值在寄存器中存放时零/符号扩展到 32 位。

#### 5.2.3 Alternate Floating-Point Data Formats

**是什么？**  
除标准 IEEE 754 外，PTX 支持多种 AI/ML 优化的浮点格式：

| 格式 | 说明 | 典型用途 |
|------|------|---------|
| `.bf16` | Brain Float 16 (1+8+7) | AI 训练/推理 |
| `.tf32` | TensorFloat-32 (1+8+10) | Tensor Core 运算 |
| `.e4m3` | FP8 (1+4+3) | 推理加速 |
| `.e5m2` | FP8 (1+5+2) | 训练梯度 |
| `.e2m3` | MX FP6 | 极低精度推理 |
| `.e3m2` | MX FP6 | 极低精度推理 |
| `.e2m1` | MX FP4 | 极低精度推理 |

**注意点：**
- 这些格式是当前 AI 硬件加速的核心，不同格式在精度和范围间做权衡。
- FP8/FP6/FP4 格式主要用于 Tensor Core 矩阵运算，不能独立做标量算术。
- 学术优化中选择数据格式直接影响模型精度和吞吐量。

#### 5.2.4 Fixed-point Data Format

定点数格式，用于特定计算场景。

#### 5.2.5 Packed Data Types

将多个小数据打包到一个寄存器中并行处理（如 `.f16x2`、`.u8x4`）。

---

### 5.3 Texture Sampler and Surface Types

纹理/采样器/Surface 的 opaque 类型声明及属性配置（主要用于图形管线，AI 计算较少涉及）。

---

### 5.4 Variables（变量）

- 支持对齐声明（`.align`）
- 支持数组和向量
- 支持参数化变量名（如 `.reg .b32 %r<100>` 声明 100 个寄存器）
- 支持 `.managed`（统一内存）和 `.unified`（统一地址）属性

---

### 5.5 Tensors（张量）

**是什么？**  
PTX 将多维矩阵结构抽象为 Tensor，定义了维度数、各维大小、元素类型和步长。

**如何使用？**  
- 通过 Tensor Copy 指令在 global/shared memory 间搬运
- 通过 `wmma.mma`、`mma`、`wgmma.mma_async`、`tcgen05.mma` 等指令进行矩阵运算

#### 5.5.1 Tensor Dimension, Size and Format

支持 1D-5D 张量，元素可以是整数、浮点或子字节类型（`.b4x16`等）。

#### 5.5.2 Tensor Access Modes

- **Tiled 模式**：保持源张量的多维布局
- **Im2col 模式**：将卷积的输入区域重排为列（经典 CNN 优化）

#### 5.5.3 Tiled Mode

- **Bounding Box**：定义访问的子区域
- **Traversal Stride**：指定遍历步长
- **Out of Boundary Access**：零填充或 OOB-NaN 填充
- **scatter4/gather4**：多行非连续访问模式

#### 5.5.4 Im2col Mode

- 将卷积窗口展开为列向量
- 支持 `im2col::w` 模式（权重方向的 im2col）

**注意点：**
- Tensor 抽象和 TMA（Tensor Memory Accelerator）是 Hopper+ 架构的核心性能优化路径。
- 使用 tensor descriptor（`tensormap`）描述张量布局，硬件自动处理地址计算和越界检查。
- Im2col 模式可在硬件层面完成传统需要 CPU 预处理的数据重排。

---

## 6 Instruction Operands（指令操作数）

### 6.1-6.3 操作数基本规则

- 所有操作数必须类型和大小匹配（除非指令本身涉及类型转换）
- 支持寄存器、常量、地址表达式和标签

### 6.4 Using Addresses, Arrays, and Vectors

#### 6.4.1 Addresses as Operands

- 支持 Generic Address（通用地址）：统一的地址空间，运行时映射到具体状态空间
- 各状态空间是 generic address space 中的"窗口"

#### 6.4.2 Arrays as Operands

- 支持字节地址或方括号索引访问

#### 6.4.3 Vectors as Operands

- 向量可用 `.x/.y/.z/.w` 或 `.r/.g/.b/.a` 提取元素
- 花括号列表 `{a,b,c,d}` 用于 pack/unpack

### 6.5 Type Conversion（类型转换）

- `cvt` 指令完成所有显式类型转换
- 支持整数↔浮点、不同宽度整数间、不同浮点格式间的转换
- 浮点转换涉及舍入模式选择

#### 6.5.2 Rounding Modifiers（舍入修饰符）

| 修饰符 | 含义 |
|--------|------|
| `.rn` | 四舍五入到最近偶数 |
| `.rna` | 四舍五入，平局远离零 |
| `.rz` | 向零舍入 |
| `.rm` | 向负无穷舍入 |
| `.rp` | 向正无穷舍入 |
| `.rs` | 随机舍入 |

**注意点：**
- `.rn` 是最常用的默认舍入模式。
- `.rs`（随机舍入）是 9.x 版本新增的，用于低精度训练中减少舍入偏差——这是当前学术研究热点之一。
- 数值精度敏感的应用中，舍入模式选择直接影响结果正确性。

### 6.6 Operand Costs（操作数访问代价）

| 空间 | 延迟 |
|------|------|
| Register | 0 |
| Shared | 0 |
| Constant | 0（均摊低，首次高）|
| Local/Global/Texture/Surface | >100 时钟 |

**注意点：**
- 隐藏内存延迟的两种策略：多线程切换 + 指令预发射。
- 合理利用 shared memory 和寄存器是 CUDA kernel 优化的核心。

---

## 7 Abstracting the ABI（ABI 抽象）

### 7.1 Function Declarations and Definitions（函数声明与定义）

**是什么？**  
PTX 用 `.func` 指令声明和定义函数，隐藏了具体 ABI（调用约定、栈布局）的细节。

**关键特性：**
- 支持多返回值
- 参数通过 `.param` 空间传递
- 支持直接调用（`call`）和间接调用（通过函数指针）

### 7.2 Stack-based Allocation（栈分配）

- `alloca` 指令支持在栈上动态分配内存
- `stacksave`/`stackrestore` 指令保存和恢复栈指针

### 7.3 CUDA Dynamic Parallelism

**是什么？**  
Dynamic Parallelism 允许 GPU 端的 kernel（子 kernel）直接启动另一个 kernel，无需返回 CPU。在 PTX 层面，通过 `mov` 指令获取 kernel 函数地址，然后传递给系统调用发起 launch。

**设计背景与演进历史：**

1. **第一性原理**：GPU 传统模型中，所有 kernel 必须由 CPU 端发起。对于递归算法（如自适应网格细化 AMR、八叉树遍历、BVH 构建）和数据依赖的工作负载（如稀疏矩阵的不规则并行），CPU 发起的扁平并行模型效率极低——每次需要 CPU-GPU 往返（~10μs 级延迟）。核心矛盾是：**GPU 计算密度越高，CPU-GPU 通信的相对开销就越大**——这要求 GPU 具备自主决策能力。

2. **Kepler 架构（sm_35, 2012）引入**：首次允许 device 端 kernel launch。PTX ISA 3.1 开始支持 `mov` 取 kernel 入口地址。这标志着 GPU 从"扁平数据并行加速器"向"自治并行处理器"的进化。设计灵感来自传统 CPU 的 `fork()` 语义——子任务继承父任务的执行上下文。

3. **后续演进：从"能力"到"效率"的三代优化**：

| 代际 | 架构 | 机制 | 开销 | 核心改进 |
|------|------|------|------|----------|
| Gen 1 | sm_35-52 (Kepler/Maxwell) | Device Runtime API launch | ~50μs | 从无到有——GPU 自主 launch |
| Gen 2 | sm_70+ (Volta+) | `griddepcontrol` (Programmatic Dependent Launch) | ~1-5μs | 消除 runtime API 开销——Grid 间直接信号 |
| Gen 3 | sm_90+ (Hopper) | `clusterlaunchcontrol` | <1μs | Cluster 级别取消+窃取——全异步 |
| Gen 3+ | sm_100+ (Blackwell) | `clusterlaunchcontrol.try_cancel` + multicast | ~0 (pipelined) | 硬件支持 work stealing |

4. **设计哲学演变**：
   - Gen 1 解决的是"能不能"——让 GPU 有能力创建新工作
   - Gen 2 解决的是"快不快"——避免 launch 的重量级开销
   - Gen 3 解决的是"灵不灵"——允许投机性取消未启动的工作，实现硬件级 work-stealing

**PTX 层面如何使用：**

```ptx
// ═══════════════════════════════════════════════
// 示例 1：基础 Dynamic Parallelism（PTX ISA 3.1+）
// ═══════════════════════════════════════════════
.entry child_kernel (.param .u64 data) { ... }

.func parent {
    .reg .u64 %kernel_addr;
    mov.u64 %kernel_addr, child_kernel;  // 取 kernel 入口地址
    // 将 %kernel_addr 传递给 cudaLaunchDevice 系统调用
}
```

```ptx
// ═══════════════════════════════════════════════
// 示例 2：Programmatic Dependent Launch（sm_90+）
// 核心思想：前驱 Grid 的计算完成前就通知后继 Grid 启动
// ═══════════════════════════════════════════════

// ---- 前驱 Grid (Producer) ----
.entry producer_kernel (...) {
    // ... 主要计算 ...
    st.global.u32 [output], result;       // 写入结果
    fence.release.gpu;                    // 确保写入对后继可见
    griddepcontrol.launch_dependents;     // 通知：后继可以开始了
    // 注意：此 CTA 可能还有收尾工作继续执行
    // launch_dependents 不是 barrier，不会阻塞当前 CTA
}

// ---- 后继 Grid (Consumer) ----
.entry consumer_kernel (...) {
    griddepcontrol.wait;                  // 等待所有前驱完成
    // 此时保证前驱的所有内存操作对本 Grid 可见
    ld.global.u32 %r0, [output];          // 安全读取前驱的结果
}
```

```ptx
// ═══════════════════════════════════════════════
// 示例 3：Cluster-level Work Stealing（sm_100+）
// 场景：Grid 中有 N 个 Cluster 要处理，当前 Cluster 处理完后
//       尝试"取消"（窃取）一个还未启动的 Cluster 的工作
// ═══════════════════════════════════════════════

mov.b32 xctaid, %ctaid.x;                 // 当前要处理的 cluster
barrier.cluster.arrive;
barrier.cluster.wait;                      // 初始同步

processCluster:
    // 选举 leader 线程
    mov.u32 %r0, %tid.x;
    setp.u32.eq p0, %r0, 0x0;
    @!p0 bra processCurrentCluster;

    // Leader: 在 mbarrier 上注册期望的 16B 响应
    mbarrier.arrive.expect_tx.cluster.relaxed.shared::cta.b64 state, [mbar], 16;

    // 第一个 CTA 尝试取消一个未启动的 cluster
    mov.u32 %r0, %cluster_ctaid.x;
    setp.u32.eq p0, %r0, 0x0;
    @p0 clusterlaunchcontrol.try_cancel.async.mbarrier::complete_tx::bytes
        .multicast::cluster::all.b128 [addr], [mbar];

processCurrentCluster:
    // ... 处理当前 cluster 的工作 ...

    // 等待取消请求完成
    waitLoop:
        mbarrier.try_wait.cluster.acquire.shared::cta.b64 complete, [mbar], state;
        @!complete bra waitLoop;

    // 读取取消响应
    ld.shared.b128 handle, [addr];
    clusterlaunchcontrol.query_cancel.is_canceled.pred.b128 p, handle;
    @!p ret;                              // 取消失败 → 无更多工作，退出

    // 取消成功：获取被取消 cluster 的 CTA ID，继续处理
    @p clusterlaunchcontrol.query_cancel.get_first_ctaid.v4.b32.b128
        {xctaid, _, _, _}, handle;

    // Proxy fence：释放本次读 → 为下次异步写做准备
    fence.proxy.async::generic.release.sync_restrict::shared::cta.cluster;
    barrier.cluster.arrive.relaxed;
    barrier.cluster.wait;
    fence.proxy.async::generic.acquire.sync_restrict::shared::cluster.cluster;
    bra processCluster;
```

**`griddepcontrol` 语义细节：**
- `.launch_dependents`：当 Grid 中**所有 CTA** 都执行了此指令（或已退出）后，runtime 指定的依赖 Grid 可被调度。但不保证依赖 Grid 一定在当前 Grid 结束前启动。
- `.wait`：阻塞当前线程直到所有前驱 Grid 完成，且前驱的所有内存操作对当前 Grid 可见。
- **内存同步规则**：`fence.release.gpu` + `griddepcontrol.launch_dependents` 可与依赖 Grid 的启动建立 synchronize-with 关系（前提是同一 memory synchronization domain + gpu scope，或 sys scope）。

**注意点（学术/工业实践）：**
- **性能开销对比**：
  - Device Runtime API launch: ~50μs（包含参数序列化、runtime 调度）
  - `griddepcontrol`: ~1-5μs（纯硬件信号，无 runtime 参与）
  - `clusterlaunchcontrol`: pipelined，可与计算重叠
- **内存可见性陷阱**：`griddepcontrol.launch_dependents` **不自带 fence**！必须在它之前显式放置 `fence.release.gpu`（或更强），否则依赖 Grid 可能看到过时数据。
- **嵌套深度限制**：传统 Dynamic Parallelism 硬件嵌套上限通常 24 层，超过 launch 失败。`griddepcontrol` 和 `clusterlaunchcontrol` 不受此限制（它们不创建嵌套）。
- **替代方案决策树**：
  - 需要递归分治且递归深度有限（<10）→ Dynamic Parallelism
  - 需要 Pipeline 多个 Grid 且已知依赖关系 → `griddepcontrol`
  - 需要动态负载均衡 / work stealing → `clusterlaunchcontrol`
  - 其余情况 → Persistent Thread + work queue
- **与 CUDA Graph 的关系**：`griddepcontrol` 常与 CUDA Graph 配合使用——Graph 定义静态依赖拓扑，`griddepcontrol` 在 kernel 内部触发启动信号，实现"静态拓扑 + 动态触发"。
- PTX 层面不直接暴露具体的寄存器分配策略和调用约定。手写 PTX 时需参考 "PTX Writers Guide to Interoperability" 确保 ABI 兼容。

---

## 8 Memory Consistency Model（内存一致性模型）

**是什么？**  
PTX 定义了一套形式化的内存一致性模型，规范多线程程序中内存操作的可见性和顺序保证。这是 PTX ISA 中最理论化也最关键的部分之一。

**设计背景与第一性原理：**

1. **为什么需要内存一致性模型？**  
   GPU 拥有数千个并发线程，且硬件为了性能会激进地重排内存操作（store buffer、cache hierarchy、write coalescing）。如果没有形式化模型，程序员无法推理多线程程序的正确性。内存模型的作用是：在"硬件自由重排以获得性能"和"程序员需要确定性行为以保证正确性"之间划定精确边界。

2. **一致性模型发展演进史：从混沌到秩序**

   1. **Sequential Consistency (SC) 时代（1970s-1980s）**

   1979 年 Leslie Lamport 定义了 **Sequential Consistency**：
   > "所有处理器的内存操作按照某种全局全序执行，且每个处理器的操作在该全序中保持程序顺序。"

   这是最直觉的模型——程序员想象所有线程在一个共享黑板上轮流读写，跟单线程思维完全一致。

   **问题**：实现 SC 需要硬件付出巨大代价：
   - 每次 store 必须立即对所有核可见（store buffer 不能用）
   - 每次 load 必须等到 cache coherence 完全收敛
   - 编译器不能做任何重排优化

   **结论**：SC 在硬件上太慢，在编译器上太死。

   2. **各家弱序模型混战时代（1990s）**

   RISC 处理器崛起，每家厂商都发明了自己的弱序模型：

   | 厂商 | 模型名称 | 核心思想 |
   |------|---------|----------|
   | DEC Alpha | 最弱序模型 | 几乎允许一切重排，包括"值推测"（读了个假值，后面发现不对再回退） |
   | PowerPC | 弱序模型 | 允许 store-store、load-load 重排，但 load-store 不重排 |
   | SPARC | TSO (Total Store Order) | 只允许 store-load 重排 |
   | x86 | TSO | 同 SPARC，比较接近 SC 但有一个"洞" |

   **问题**：
   - **程序员噩梦**：不同架构行为不同，写出来的并发代码换个 CPU 就可能出 bug
   - **编译器困境**：编译器不知道硬件会怎么重排，只能保守优化，性能上不去
   - **可移植性灾难**：为 x86 写的代码到了 ARM 上完全不对

   > 典型惨案：DEC Alpha 上，`a=1; b=a;` 都可能被重排成先读 b 再写 a。甚至出现过"读到 42 但 flag 还是 0"的诡异行为，因为硬件做了值推测。

   3. **三条路线的竞争**

   核心问题：能不能找到一个**既让硬件/编译器充分优化，又让程序员能写出正确并发代码**的模型？

   **方案 A：硬件强序 + 软件什么都不管（SC 路线）**
   - 优点：程序员最舒服，不用想任何同步
   - 缺点：硬件慢 30-50%，功耗高，多核扩展性差
   - 代表：早期 MIPS、部分 x86 行为

   **方案 B：硬件弱序 + 程序员用全套 fence 指令手动控制**
   - 优点：硬件自由优化
   - 缺点：程序员需要在每对读写之间手动插入 fence，代码极难写对
   - 代表：DEC Alpha + 原始 memory barrier 指令

   **方案 C：硬件弱序 + 给内存操作标注语义标签（Acquire-Release 模型）**
   - 优点：
     - 硬件默认自由重排（`.relaxed` 行为 = 弱序）
     - 程序员只在需要时标注语义（`.acquire`/`.release`）
     - 标注是"声明式"的，硬件根据声明决定哪些重排被禁止
     - 编译器可以看懂这些标注，做精准优化
   - 缺点：概念上比 SC 复杂，需要理解 synchronize-with

   4. **Acquire-Release 模型胜出（2011+）**

   2011 年是关键年份，两个标准同时采纳了 Acquire-Release 模型：

   | 标准 | 采纳方式 |
   |------|----------|
   | **C++11 / C11** | `std::memory_order`（`relaxed`, `acquire`, `release`, `acq_rel`, `seq_cst`） |
   | **PTX ISA** | `.relaxed`, `.acquire`, `.release`, `.acq_rel`, `.sc` 修饰符 |

   **为什么选了方案 C？四个核心原因：**

   **① 性能：默认弱序，按需加强**
   99% 的内存操作是 `.relaxed`（零开销），只在同步点标注 `.acquire`/`.release`（极少量指令有额外开销）。方案 A（SC）下每条 store 都有 fence 开销；方案 C 下只有显式标注的才有。

   **② 可移植性：语义是声明式的，不是命令式的**
   ```ptx
   // 声明式（方案C）：告诉编译器和硬件"我需要什么语义"
   st.release [flag], 1;    // 硬件自己决定用什么 fence/barrier 实现

   // 命令式（方案B）：程序员手动插 fence
   st [flag], 1;
   mfence;                   // 在 x86 上是 mfence，在 ARM 上是 dmb，在 GPU 上是 fence.sc
   ```
   声明式的好处：**同一份代码在所有架构上都对**。硬件/编译器负责把声明翻译成该架构最高效的实现。

   **③ 正确性：synchronize-with 关系可形式化验证**
   Acquire-Release 的核心是一个叫 **synchronize-with** 的形式化关系：
   ```
   release 写入 ────synchronize-with────→ acquire 读取
        │                                      │
        │  所有在此之前的写入                    │  所有在此之后的读取
        │  都对 acquire 侧可见                  │  都能看到 release 侧的写入
   ```
   这个关系有严格的数学定义（基于 happens-before 偏序），可以被模型检测器验证，被编译器当作优化边界。相比之下，手动插 fence 的"对不对"完全靠人脑判断。

   **④ 编译器优化友好**
   ```ptx
   // 编译器看到 .relaxed：可以自由优化这个操作
   atom.relaxed.global.add [counter], 1;   // 可以合并、延迟、推测

   // 编译器看到 .release：之前的操作不能越过它
   st [data], 42;
   st.release [flag], 1;    // data=42 必须在这个 store 之前完成
   // 编译器知道不能把 st [data] 移到 st.release 之后
   ```
   这让编译器既能在 `.relaxed` 路径上激进优化，又能在 `.release` 路径上保守处理——**精准控制优化边界**。

   5. **GPU 上的特殊演化（2017+）**

   GPU 在 Acquire-Release 基础上增加了**独特维度**：

   | 扩展 | 原因 |
   |------|------|
   | **`.scope`（cta/cluster/gpu/sys）** | GPU 有多层并行层次，同一个 acquire 在 CTA 内和在 GPU 全局的代价差 10x |
   | **`fence.proxy.async`** | TMA 异步拷贝走独立的硬件路径，需要显式桥接不同 proxy 之间的可见性 |
   | **`mbarrier` + `.acquire`** | 硬件级异步完成通知，比软件轮询 flag 高效得多 |

   这些扩展说明 Acquire-Release 模型的**核心思想足够灵活**——它的框架是"声明语义 + 声明作用域"，GPU 只需添加新的作用域维度，而不需要推翻整个模型。

   6. **演进路线图总结**

   ```
   Sequential Consistency (1979)
       │
       │  太慢，硬件无法优化
       ▼
   各家弱序模型 (1990s)
       │  Alpha / PowerPC / x86 TSO / SPARC
       │  不可移植，程序员噩梦
       ▼
   "需要一个统一标准"
       │
       ├── 方案A: 硬件强序（SC）     → 太慢
       ├── 方案B: 手动插 fence        → 太难写对
       └── 方案C: Acquire-Release     → 默认快、按需强、可验证、可移植
                 │
                 ▼
           C++11 / PTX ISA (2011+)
                 │
                 ▼
           GPU 扩展：scope + proxy + mbarrier
   ```

   **一句话总结**：Acquire-Release 模型是"让硬件默认跑得快，让程序员只在关键点声明需要什么保证"的最优折中——它赢得了历史和工程实践的双重验证。

   7. **PTX 自身的版本演进时间线**

   | PTX 版本 | 硬件时代 | 关键变化 |
   |-----------|----------|----------|
   | PTX 1.x-5.x | Tesla→Maxwell | 仅有 `membar` 指令，语义模糊，本质是"flush all pending operations"的粗粒度栅栏。只有 `.cta`/`.gl`/`.sys` 三个级别 |
   | PTX 6.0 (sm_70 Volta, 2017) | Volta | 受 C++11/C11 memory model 启发，引入 `.relaxed`/`.acquire`/`.release`/`.acq_rel` 语义和 scope 概念。原因：Volta 的 Independent Thread Scheduling 打破了 warp-synchronous 假设，必须有精确的同步语义 |
   | PTX 7.x-8.x | sm_80 Ampere→sm_90 Hopper | 引入 `.cluster` scope、proxy fence、async 一致性模型。Cluster 和 TMA 引入了新的内存访问路径，需要更丰富的 fence 机制 |
   | PTX 9.x (sm_100 Blackwell) | Blackwell | fabric proxy 纳入一致性模型，多 GPU 通信也有了形式化的排序保证 |

3. **与 C++ 内存模型的关键差异：**
   - PTX 模型**更弱**：允许 Load Buffering（两个线程互相读对方的写，都读到旧值）——C++ 在 SC-DRF 下禁止这种行为。
   - PTX 增加了 **scope** 维度：C++ 只有全局一致性；PTX 根据线程关系分层（CTA→GPU→System），低层级同步更便宜。
   - PTX 增加了 **proxy** 维度：区分不同内存访问路径，这在 CPU 世界中无对应物（CPU 不存在 async copy 或 texture 采样等旁路）。

### 8.1-8.4 基本概念

- **Operation Types**：Read、Write、Atomic RMW（Read-Modify-Write）

### 8.4.1 Strong vs. Weak Operations（强操作 vs. 弱操作）

**是什么？**  
- **Strong operation（强操作）**：带有 `.relaxed`、`.acquire`、`.release`、`.acq_rel`、`.volatile` 或 `.mmio` 修饰符的内存操作，以及 `fence` 指令。它们参与内存一致性模型的所有公理，可以建立跨线程的排序关系。
- **Weak operation（弱操作）**：带有 `.weak` 修饰符的 `ld` 或 `st` 指令。它们**不参与**任何排序保证——编译器和硬件可以任意重排、合并、甚至消除。

**第一性原理——为什么需要这种区分？**

性能与正确性的根本权衡：
- 绝大多数内存访问（如循环体内的数组读写）不参与跨线程通信，为它们加排序约束是纯开销。
- 只有用于同步的少数关键访问（flag、lock）需要排序保证。
- Weak 操作给予硬件最大自由度（可合并、可预取、可乱序），Strong 操作则在需要时精确表达同步意图。

**演进历史：**

| 时代 | 特点 |
|------|------|
| PTX 1.x-5.x (Tesla→Maxwell) | 没有 strong/weak 区分，所有 ld/st 隐式具有某种排序语义（并在硬件层面通过 warp-lockstep 模拟） |
| PTX 6.0 (Volta sm_70) | 引入显式 `.weak` 默认修饰符。原因：Independent Thread Scheduling 打破了 warp lockstep 假设，必须显式区分哪些访问需要排序保证 |
| PTX 7.x+ (Ampere/Hopper) | 强化 scope 和异步语义，但 strong/weak 的基本二分不变 |

**硬件层面 Strong 和 Weak 的区别：**
- **Weak `ld`**：硬件可以从 L1 cache 读取而不检查一致性、可以与其他 load 合并（coalescing）、可以被编译器提前或延迟
- **Strong `.relaxed` `ld`**：硬件保证原子性（读取的字节不会来自两次不同的写），但不强制刷新 cache
- **Strong `.acquire` `ld`**：硬件必须在返回前刷新相关的 cache line，确保看到 release 端发布的所有数据

**完整的操作类型分类表（摘自 PTX ISA Table 20）：**

| 操作类型 | 指令/说明 |
|----------|----------|
| atomic operation | `atom` 或 `red` 指令 |
| read operation | 所有 `ld` 及 `atom`（但**不包括** `red`） |
| write operation | 所有 `st`，以及产生写入的 atomic |
| volatile operation | 带 `.volatile` 限定符的指令 |
| strong operation | memory fence 或带有 `.relaxed/.acquire/.release/.acq_rel/.volatile/.mmio` 的内存操作 |
| weak operation | 带 `.weak` 的 `ld` 或 `st` |
| synchronizing operation | barrier、fence、release 或 acquire 操作 |

**PTX 示例——常见模式与陷阱：**

```ptx
// ═══════════════════════════════════════════════
// 模式 1：典型数据并行——大部分访问都是 weak
// ═══════════════════════════════════════════════
// CUDA C++： output[tid] = input[tid] * 2;
// 编译为 PTX：
ld.weak.global.f32 %f0, [input_addr];    // weak: 不参与同步
fma.rn.f32 %f1, %f0, 2.0, 0.0;
st.weak.global.f32 [output_addr], %f1;   // weak: 硬件可合并多个线程的写入

// ═══════════════════════════════════════════════
// 模式 2：自旋等待标志（必须用 strong）
// ═══════════════════════════════════════════════
// 正确写法：
spinLoop:
    ld.relaxed.gpu.global.u32 %r0, [flag]; // strong: 硬件保证看到更新
    setp.eq.u32 %p, %r0, 0;
    @%p bra spinLoop;
fence.acquire.gpu;                        // 建立 acquire

// 错误写法（永远不会看到更新）：
badLoop:
    ld.weak.global.u32 %r0, [flag];       // ✗ weak: 硬件可能无限期返回缓存值
    setp.eq.u32 %p, %r0, 0;
    @%p bra badLoop;                       // 可能死循环！

// ═══════════════════════════════════════════════
// 模式 3：数据竞争下 weak 的未定义行为
// ═══════════════════════════════════════════════
// T1: st.weak.global.u32 [x], 1;   // weak 写
// T2: ld.weak.global.u32 %r, [x];  // weak 读
// 结果：完全未定义！%r 可能是 0、1 或任何值
// 修复：至少一方使用 strong (.relaxed 即可保证原子性)

// ═══════════════════════════════════════════════
// 模式 4：strong+weak 混合——release 保护 weak 数据
// ═══════════════════════════════════════════════
// Producer:
st.weak.global.f32 [data+0], %f0;     // weak 写数据（快）
st.weak.global.f32 [data+4], %f1;
st.weak.global.f32 [data+8], %f2;
fence.release.gpu;                     // √ release: 确保上面 weak 写入对后续 acquire 可见
st.relaxed.gpu.global.u32 [flag], 1;   // strong 写 flag

// Consumer:
spinWait:
    ld.relaxed.gpu.global.u32 %r0, [flag];
    setp.eq.u32 %p, %r0, 0;
    @%p bra spinWait;
fence.acquire.gpu;                     // √ acquire: 现在可以安全读 weak 数据
ld.weak.global.f32 %f0, [data+0];     // √ 确保看到最新值
ld.weak.global.f32 %f1, [data+4];
ld.weak.global.f32 %f2, [data+8];
```

**注意点：**
- CUDA C++ 中普通的全局内存读写（如 `data[tid] = val`）编译为 PTX 时默认是 `.weak`。
- 只有 `atomicXXX()`、`cuda::atomic<>` 等显式同步操作才编译为 `.relaxed` 或更强的修饰符。
- 对一个地址既有 weak 写又有 strong 读是安全的（但 weak 写可能看不到 strong 写的结果）；weak 操作间的数据竞争行为是 undefined。
- **实践陷阱**：不要对 `.weak` load 的结果做同步判断（如 spin-wait），因为硬件可能无限期缓存旧值。
- **性能影响实测**：在高并发 kernel 中，将所有 load/store 从 weak 升级为 `.relaxed` 可能导致 10-30% 的吐吐量下降（由于禁止了 load coalescing 和 store write-combining 优化）。
- **安全规则**：当且仅当数据访问被 release/acquire fence "bracket" 包围时，weak 操作才能安全地用于跨线程通信。

### 8.4.2 Volatile Operations（volatile 操作）

**是什么？**  
Volatile 操作等价于 `relaxed` 语义 + `system scope`，加上两个额外的实现约束：
1. **指令数量保留**：编译器不得消除 volatile 指令（但硬件可能合并多条 volatile 指令的内存操作）
2. **指令间不重排**：volatile 指令之间保持程序顺序（但底层内存操作仍可能重排）

**设计背景与演进历史：**

1. **历史遗产与滥用现象**：CUDA C++ 从 C/C++ 继承了 `volatile` 关键字。在 Volta 之前的 warp-synchronous 编程时代，`volatile` 常被滥用作线程间通信（利用 warp lockstep 行为）。这种用法在 Volta+ 架构上不再安全。

2. **为什么还存在 volatile？**（第一性原理分析）
   - **编译器降级需要**：CUDA C++ 的 `volatile` 变量必须有对应的 PTX 语义。如果取消 volatile 操作，现有 CUDA C++ 代码将无法正确编译。
   - **调试工具**：防止编译器优化掉看似无用的读写（调试时随时观察内存状态）。
   - **不适合同步**：PTX 规范明确指出 volatile **不适用于**线程间同步（应用 `ld.relaxed.sys`/`st.relaxed.sys`）。
   - **不适合 MMIO**：因为 volatile 不保证内存操作次数（硬件可能合并多次 volatile 访问为一次），应用 `.mmio` 操作。

3. **三种模式对比（关键区别）：**

| 特性 | `.volatile` | `.relaxed.sys` | `.mmio.relaxed.sys` |
|--------|------------|---------------|---------------------|
| 指令数量保留 | √（编译器不消除） | ×（可被消除） | √ |
| 内存操作次数保留 | ×（硬件可合并） | × | √（严格保留） |
| 形成 acquire/release pattern | × | ×（但可配合 fence） | ×（但可配合 fence） |
| 适用场景 | 编译器 lowering、调试 | 线程间同步 | 硬件 IO 寄存器 |
| 性能 | 较差（sys scope） | 灵活（可选 scope） | 最差（无缓存） |

**PTX 示例——三种操作的对比：**

```ptx
// ═══════════════════════════════════════════════
// Volatile: 保证这条指令一定执行（不被编译器消除）
// 但硬件可能将多条 volatile 的实际内存操作合并
// ═══════════════════════════════════════════════
ld.volatile.global.u32 %r0, [addr];       // 编译器保证不消除
st.volatile.global.u32 [addr], %r1;       // 编译器保证不消除
// 以上两条之间不重排，但可能被硬件合并为 1 次内存操作

// ═══════════════════════════════════════════════
// .relaxed.sys: 推荐的线程间通信方式
// ═══════════════════════════════════════════════
ld.relaxed.sys.global.u32 %r0, [flag];    // 可配合 fence 形成 acquire pattern
st.relaxed.sys.global.u32 [flag], 1;      // 可配合 fence 形成 release pattern
// 性能更好（如果只需 gpu scope，可用 .relaxed.gpu 降低开销）

// ═══════════════════════════════════════════════
// .mmio: 用于真正的硬件 IO，严格保证每次访问都产生实际内存操作
// ═══════════════════════════════════════════════
ld.mmio.relaxed.sys.global.u32 %r0, [mmio_reg];  // 不缓存、不合并、不预取
st.mmio.relaxed.sys.global.u32 [mmio_reg], %r1;  // 严格 1:1 写入
```

```ptx
// ═══════════════════════════════════════════════
// 反例：为什么 volatile 不能用来同步
// ═══════════════════════════════════════════════

// T1 (Producer - 写数据 + volatile 写标志)
st.global.u32 [data], 42;             // 写数据
st.volatile.global.u32 [flag], 1;     // volatile 写标志

// T2 (Consumer - volatile 读标志 + 读数据)
spinWait:
    ld.volatile.global.u32 %r0, [flag];
    setp.eq.u32 %p, %r0, 0;
    @%p bra spinWait;
ld.global.u32 %r1, [data];            // ⇐ 不保证看到 42！

// 原因：volatile 不形成 release/acquire pattern，因此
//       data 的写入与 flag 的观测之间没有 happens-before 关系
// 修复：用 st.release.gpu + ld.acquire.gpu 替代 volatile
```

```ptx
// ═══════════════════════════════════════════════
// 调试技巧：用 volatile 观察中间值（volatile 的正确用法）
// ═══════════════════════════════════════════════
.global .u32 debug_slot;  // 仅用于调试观察

// 在计算中间插入 volatile store，确保值被写出（不被优化掉）
// 即使编译器认为这个 store "dead"(后续无读取)，也不会被消除
fma.rn.f32 %f0, %f1, %f2, %f3;
st.volatile.global.f32 [debug_slot], %f0;  // 调试用: 确保可以在 host 端观察到
// ... 更多计算 ...
```

**注意点：**
- **绝对不要用 volatile 做自旋锁或 flag 通信**——虽然可能"碰巧"工作，但不具有形式化的正确性保证。
- volatile 指令数量被保留，但内存操作数量不被保留（硬件可能合并多个 volatile 指令的访问为一次内存事务）。
- 从 Volta 架构开始，NVIDIA 强烈建议用 `relaxed` atomic 替代 volatile 做线程间通信。
- **迁移指南**：将老代码中的 `volatile` 同步模式迁移到现代模式：
  - `ld.volatile` → `ld.relaxed.gpu`（同 GPU 内通信）或 `ld.relaxed.sys`（跨 GPU/CPU）
  - `st.volatile` → `st.relaxed.gpu` 或 `st.relaxed.sys`
  - 并加上适当的 `fence.acquire`/`fence.release`

### 8.5 Scope（作用域）

| 作用域 | 含义 | 典型开销 |
|--------|------|----------|
| `.cta` | 同一 CTA 内的线程 | 最低（L1/shared 层级） |
| `.cluster` | 同一 Cluster 内的线程 | 低（跨 SM 但仍片上） |
| `.gpu` | 同一 GPU 上的所有线程 | 中（需 L2 一致性） |
| `.sys` | 整个系统（包括 CPU 和其他 GPU） | 最高（需跨 PCIe/NVLink） |

**第一性原理——为什么需要分层 scope？**

GPU 缓存层次是 Non-Inclusive、Non-Coherent 的（与 CPU 的 MESI/MOESI 完全不同）：
- L1 缓存是 per-SM 的，默认不参与一致性协议
- 只有 L2 缓存是全 GPU 共享的
- 跨 GPU 通信需要走 NVLink/PCIe

如果所有同步都在 system scope 完成（像 CPU 那样），每次 fence 都要刷穿整个缓存层次——这对 GPU 来说是灾难性的。分层 scope 允许程序员精确指定"这次同步只需要在 CTA 内可见"，硬件就只需同步 shared memory/L1 层级。

**PTX 示例——选择正确的 scope：**

```ptx
// 场景 1：CTA 内的 producer-consumer（最便宜）
st.shared.release.cta.u32 [smem_flag], 1;       // Producer
ld.shared.acquire.cta.u32 %r0, [smem_flag];     // Consumer in same CTA

// 场景 2：Cluster 内跨 CTA 通信（sm_90+）
st.shared::cluster.release.cluster.u32 [remote_smem], val;
ld.shared::cluster.acquire.cluster.u32 %r0, [remote_smem];

// 场景 3：不同 CTA（不在同一 cluster）的全局通信
st.global.release.gpu.u32 [flag], 1;
ld.global.acquire.gpu.u32 %r0, [flag];

// 场景 4：CPU-GPU 通信（最昂贵）
st.global.release.sys.u32 [pinned_mem_flag], 1;  // GPU 写
// CPU 端读取 pinned_mem_flag
```

**注意点：**
- Scope 选择直接影响同步的开销和正确性。
- 过大的 scope（如 `.sys`）开销大但保证强；过小的 scope 开销低但可能无法正确同步。
- Warp 不是一个作用域——CTA 是最小的同步作用域。
- **选择原则**：使用满足正确性要求的最小 scope。如果通信只在 CTA 内发生，用 `.cta`；只在 GPU 内发生，用 `.gpu`。
- **常见错误**：用 `.cta` scope 试图同步不同 CTA 的线程——不会建立 happens-before 关系，导致数据竞争。

### 8.6 Proxies（代理/访问路径）

**是什么？**  
不同的内存访问方式（normal load/store、async copy、texture、fabric）被视为不同的 "proxy"。跨 proxy 的内存操作需要 **proxy fence** 来建立排序关系。

**第一性原理——为什么需要 proxy 概念？**

GPU 不同于 CPU 的关键一点：它有多种独立的内存访问路径，各路径可能走不同的硬件单元：
- 普通 load/store 走 L1→L2 路径
- `cp.async.bulk` 走 TMA (Tensor Memory Accelerator) 旁路
- Texture load 走 texture cache
- Fabric 操作走 NVLink 接口

这些路径各自有独立的缓冲/队列，彼此间不自动保持顺序。`fence.proxy` 的作用是在不同路径之间建立因果关系。

**常见 proxy 类型：**

| Proxy 类型 | 关联指令 | 对应 Fence |
|-----------|----------|----------|
| generic | 普通 ld/st | （默认，无需额外 fence） |
| async | cp.async.bulk, wgmma.mma_async | `fence.proxy.async` |
| alias | 通过不同虚拟地址访问同一物理位置 | `fence.proxy.alias` |
| tensormap | tensormap 描述符访问 | `fence.proxy.tensormap::generic` |
| fabric | fabric.try_get/put/red | `fence.proxy.generic::fabric` |

**PTX 示例：**

```ptx
// 场景 1：异步拷贝后用普通 load 读取结果
// TMA 异步拷贝到 shared memory
cp.async.bulk.shared::cta.global.relaxed.gpu [smem], [gmem], size, [mbar];

// 等待完成
mbarrier.try_wait.acquire.cta.shared::cta.b64 complete, [mbar], state;

// 必须的 proxy fence：将 async proxy 路径的写入对 generic proxy 可见
fence.proxy.async;  // ← 缺少这一步将导致后续 ld.shared 读到旧数据！

// 现在可以安全用普通 load 读取
ld.shared.f32 %f0, [smem];
```

```ptx
// 场景 2：通过不同虚拟地址访问同一物理位置
// data_alias_1 和 data_alias_2 映射到同一物理地址
st.global.u32 [data_alias_1], 1;
fence.proxy.alias;                    // ← 必须！建立 alias 路径间的因果关系
ld.global.u32 %r0, [data_alias_2];    // 保证看到 1
```

```ptx
// 场景 3：Fabric 操作与普通内存之间的同步
fence.proxy.generic::fabric.alias.release.sys;  // generic → fabric
// ... fabric 操作 ...
fence.proxy.fabric::generic.alias.acquire.sys;  // fabric → generic
// 现在普通 load/store 可以看到 fabric 操作的结果
```

**注意点：**
- 使用 `cp.async.bulk` 等异步操作后，必须用 `fence.proxy.async` 保证与普通 load/store 的顺序。这是最常见的遗漏。
- 通过虚拟地址别名访问同一物理位置也需要 `fence.proxy.alias`。
- **遗忘 proxy fence 是导致异步数据搬运 bug 的首要原因**。调试时如果发现异步拷贝数据不正确，首先检查是否缺少 proxy fence。

### 8.7 Morally Strong Operations

两个操作"morally strong"需满足：同一线程或互相在对方 scope 内 + 同一 proxy + 完全重叠。

### 8.8 Release and Acquire Patterns（释放与获取模式）

**是什么？**  
- **Release pattern**：使当前线程先前的操作对其他线程可见
- **Acquire pattern**：使其他线程的操作对当前线程后续操作可见

**第一性原理——为什么需要 Release/Acquire？**

Release/Acquire 是建立跨线程 happens-before 关系的基础机制。它的核心思想是：
- Release 说："我在这之前做的所有写入，现在都“发布”了"
- Acquire 说："我现在“获取”了对方发布的所有内容，后续操作可以安全使用”

这比全局顺序一致性（SC）便宜得多，因为它只约束相关线程间的可见性，不要求全局全序。在 GPU 这种大规模并发系统中，这种"局部性”是性能的关键。

**5 种 Release pattern的形式：**

```ptx
// 形式 1：直接 release 操作
st.release.gpu [M], val;
atom.release.gpu [M], val;
mbarrier.arrive.release [M];

// 形式 2：release 操作 + 后续 strong write
st.release.gpu [M], val;
st.relaxed.gpu [M], val2;  // 这两条一起构成 release pattern

// 形式 3：release fence + strong write
fence.release.gpu;
st.relaxed.gpu [M], val;   // fence + store 构成 release pattern

// 形式 4：release fence + async 写
fence.release.sys;
cp.async.bulk.global.shared.relaxed.sys [M], [smem], size;  // 异步写

// 形式 5：release 异步操作
st.async.release.sys [M], val;
```

**4 种 Acquire pattern 的形式：**

```ptx
// 形式 1：直接 acquire 操作
ld.acquire.gpu [M];
atom.acquire.gpu [M];
mbarrier.test_wait.acquire [M];

// 形式 2：strong read + acquire 操作
ld.relaxed.gpu %r0, [M];
ld.acquire.gpu %r1, [M];   // 两条一起构成 acquire pattern

// 形式 3：strong read + acquire fence
ld.relaxed.gpu %r0, [M];
fence.acquire.gpu;          // read + fence 构成 acquire pattern

// 形式 4：观察 async 操作完成 + acquire fence
mbarrier.try_wait.relaxed p, [barrier];  // 观察完成
@p fence.acquire.gpu;                    // acquire fence
```

**完整的 Message Passing 示例（最重要的同步模式）：**

```ptx
.global .u32 data = 0;
.global .u32 flag = 0;

// Thread T1 (Producer)
st.global.u32 [data], 42;              // W1: 写数据
fence.release.gpu;                      // F1: release fence
st.relaxed.gpu.global.u32 [flag], 1;   // W2: 写标志

// Thread T2 (Consumer)
waitLoop:
    ld.relaxed.gpu.global.u32 %r0, [flag];  // R1: 读标志
    setp.eq.u32 %p, %r0, 0;
    @%p bra waitLoop;
fence.acquire.gpu;                      // F2: acquire fence
ld.global.u32 %r1, [data];             // R2: 读数据
// 保证：如果 R1 看到了 1，则 R2 一定看到 42
```

**注意点：**
- `red`（atomic reduction）的 read 部分**不构成** acquire pattern！这是 PTX 内存模型中最容易踩的坑。
- release 只影响 pattern 中第一条指令之前的操作；acquire 只影响 pattern 中最后一条指令之后的操作。
- `fence.sc`（顺序一致 fence）可以解决 fence.acq_rel 解决不了的 Store Buffering 问题，但开销更大。


```
┌─────────────────────┬──────────┬──────────┬──────────┬──────────┐
│ 指令                │ .acquire │ .release │ .acq_rel │ .relaxed │
├─────────────────────┼──────────┼──────────┼──────────┼──────────┤
│ ld                  │    ✅    │    —     │    —     │    ✅    │
│ st                  │    —     │    ✅    │    —     │    ✅    │
│ atom                │    ✅    │    ✅    │    ✅    │    ✅    │
│ fence               │    ✅    │    ✅    │    ✅    │    —     │
│ mbarrier.try_wait   │    ✅    │    —     │    —     │    —     │
│ fence.proxy         │    ✅    │    ✅    │   视情况  │    —    │
└─────────────────────┴──────────┴──────────┴──────────┴──────────┘
```
核心原则：只有能产生内存可见性效果的指令才能加这些修饰符。纯计算指令（add、mul 等）不涉及内存访问，自然不需要也不支持内存序修饰符。而 red 虽然写内存，但没有返回值（不读），所以不支持 .acquire——这也呼应了之前讨论的"red 不能建立 synchronize-with 关系"。


### 8.9 Ordering of Memory Operations

- **Program order**：单线程内的顺序
- **Causality order**：跨线程的因果关系（通过 synchronize-with 建立）
- **Communication order**：写操作间的全序（coherence order）

**第一性原理——为什么需要三种不同的顺序？**

GPU 的内存模型需要在以下三个维度上分别建模：
1. **单线程内**：程序的书写顺序就是基本的排序参考
2. **跨线程**：必须通过同步操作显式建立因果关系（不同线程的操作默认无序）
3. **写-写关系**：同一地址的所有写必须有全局一致的顺序（coherence）

**因果序（Causality Order）的建立方式（摘自规范 §8.9.5）：**

操作 X 在因果序上先于 Y，当且仅当：
1. X 先于 Y 在 proxy-preserved base causality order 中，或
2. 存在操作 Z 使得 X 先于 Z 在 observation order 中，且 Z 先于 Y 在 proxy-preserved base causality order 中

其中 Base causality order 是传递性关系，满足：
- X 先于 Y 在程序序中，或
- X 与 Y 建立了 synchronize-with 关系，或
- 存在中间操作 Z 使得可以传递

**关键洞察：**因果序是**传递性**的——这意味着 release/acquire 的同步效果可以跨越多个中间线程传递（即"累积性" / cumulativity）。这对于复杂的多级同步场景至关重要。

**异步操作的排序特殊性（§8.9.1.1）：**

cp.async、cp.async.bulk、wgmma.mma_async 等异步指令的操作**不属于**发起线程的 program order。它们提供更弱的保证：
- cp.async 的 load/store 之间有序，但与其他 cp.async 或后续指令之间**无序**
- cp.async.bulk 的隐式 mbarrier complete-tx 仅与同一条异步指令的操作有序，不与发起线程的先前指令传递建立排序
- 因此必须用 mbarrier 的 arrive + wait 机制来显式确认异步操作完成

```ptx
// 示例：异步操作排序的正确模式
st.global.u32 [data], 42;                    // (1) 写数据
fence.release.gpu;                           // (2) release fence
cp.async.bulk.shared::cta.global.relaxed.gpu // (3) 异步拷贝
    [smem], [gmem], size, [mbar];
// 注意：(3) 与 (1)(2) 之间的排序不通过 program order 保证！
// 而是通过 mbarrier 的 arrive/wait 机制间接保证。
```

### 8.10 Axioms（公理）

**是什么？**  
公理是内存一致性模型的核心——它们定义了哪些执行结果是**禁止的**（而非哪些是允许的）。

- **Coherence（一致性）**：对同一地址的写有全局一致的顺序。不可能线程 A 看到写顺序是 X→Y，线程 B 看到是 Y→X。
- **No-Thin-Air（禁止无中生有）**：禁止自实现的循环依赖。例如：如果 A1 读 B2、A2 读 B1，形成循环，则只能读到初始值（不能凭空产生值）。
- **Sequential Consistency Per Location**：每个地址上的 morally strong 操作序列是严格顺序一致的。即：对同一地址的 strong 读写不会出现“时光倒流”。
- **Causality（因果性）**：因果关系不可被通信顺序违反。如果 W 在因果顺序上先于 R，则 R 不能读到比 W 更旧的写入。

**Litmus Test 示例——CoRR（连贯读读）：**

```ptx
.global .u32 x = 0;
// T1: st.global.relaxed.sys.u32 [x], 1;   // W1
// T2: ld.global.relaxed.sys.u32 %r0, [x]; // R1
//     ld.global.relaxed.sys.u32 %r1, [x]; // R2
// 保证：如果 %r0 == 1，则 %r1 == 1（不能“消失”）
```

**Store Buffering Litmus Test（展示 fence.sc 的必要性）：**

```ptx
.global .u32 x = 0;
.global .u32 y = 0;
// T1:                          // T2:
// st.global.u32 [x], 1;       // st.global.u32 [y], 1;
// fence.sc.sys;                // fence.sc.sys;
// ld.global.u32 %r0, [y];     // ld.global.u32 %r1, [x];
// 保证：%r0==1 OR %r1==1（至少一个看到对方的写入）
// 注意：如果用 fence.acq_rel 替换 fence.sc，则不保证这个结果！
```

### 8.11 Special Cases

- `red`（atomic reduction）**不形成 acquire pattern**——这是一个常见陷阱
- 需要 acquire 语义时，使用 `atom` 而非 `red`

**Litmus Test 示例——red 不同步：**

```ptx
.global .u32 x = 0;
.global .u32 flag = 0;

// T1 (Producer):                      // T2 (Consumer - WRONG!):
// st.u32 [x], 42;                     // red.sys.global.add.u32 [flag], 1;  // NOT an acquire!
// st.release.gpu.u32 [flag], 1;       // fence.acquire.gpu;
//                                     // ld.weak.u32 %r1, [x];
// 可能结果：%r1 == 0 且 flag == 2
// 原因：red 不构成 acquire pattern，因此 release 不能与它 synchronize-with
// 修复：用 atom.add 替代 red.add
```

**注意点（学术/工业）：**
- PTX 内存模型比 C++11 模型更弱（允许 Load Buffering），设计无锁算法需格外小心。
- `fence.sc`（顺序一致 fence）是最强的同步原语，但开销也最大。
- 混合大小数据竞争（mixed-size data-race）使一致性模型公理失效——必须避免。
- 实际工程中，优先使用 release/acquire 语义而非 volatile。
- **调试技巧**：当怀疑内存模型问题时，先尝试将所有 fence 升级为 `fence.sc.sys`，如果问题消失，则确认是排序问题，然后逐步降级到最小必要的 scope 和语义。

---








## 9 Instruction Set（指令集）

### 9.1-9.2 Format and Semantics / PTX Instructions

- 指令通常有 0-4 个操作数 + 可选 guard predicate
- 格式：`@p opcode.modifier.type dest, src1, src2, src3;`

### 9.3 Predicated Execution（谓词执行）

**是什么？**  
通过 `@p` 或 `@!p` 前缀条件执行指令，避免分支。

**为什么？**  
- 短的条件代码可以用谓词代替分支，避免 warp divergence
- 比分支更高效（无需跳转）

### 9.4-9.6 Comparisons / Type Information / Divergence

- 比较操作支持 ordered/unordered（处理 NaN）
- 类型检查规则：严格模式 vs 宽松模式
- Divergence 在 warp 内发生时影响性能

### 9.7 Instructions（具体指令）

#### 9.7.1 Integer Arithmetic Instructions（整数算术指令）

包括 `add`、`sub`、`mul`、`mad`、`div`、`rem`、`abs`、`neg`、`min`、`max`、`popc`(popcount)、`clz`(前导零)、`bfind`(最高有效位)、`bfe`(位域提取)、`bfi`(位域插入)、`bmsk`(位掩码)、`dp4a`/`dp2a`(整数点积) 等。

**注意点：**
- `dp4a`/`dp2a` 是 INT8 推理的核心指令（4/2 元素点积累加）。
- `mul.wide` 可生成双倍宽度结果（16×16→32 或 32×32→64）。
- `.sat` 修饰符防止溢出（饱和运算），对信号处理很重要。

#### 9.7.2 Extended-Precision Integer Arithmetic

`addc`（带进位加）、`subc`（带借位减）、`madc`（带进位乘加）——用于实现超过 64 位的大整数运算。

#### 9.7.3 Floating-Point Instructions（浮点指令）

包括 `add`、`sub`、`mul`、`fma`、`div`、`rcp`(倒数)、`sqrt`、`rsqrt`(倒数平方根)、`sin`、`cos`、`lg2`(log2)、`ex2`(2^x)、`tanh` 等。

**注意点：**
- `fma`（Fused Multiply-Add）是 GPU 浮点运算的基石——一次操作完成乘加并只进行一次舍入。
- `.approx` 修饰符表示快速近似计算（精度降低但速度快）。
- 超越函数（sin/cos/lg2/ex2/tanh）通常以近似方式实现。
- `.rn`（round to nearest even）是默认也是最常用的舍入模式。

#### 9.7.4 Half Precision Floating-Point Instructions

`.f16` 和 `.bf16` 类型的 `add`、`sub`、`mul`、`fma`、`min`、`max`、`tanh`、`ex2` 等，通常以 `x2` 打包操作（一次处理两个 fp16 值）。

#### 9.7.5 Mixed Precision Floating-Point Instructions

跨精度运算（如 fp16 输入 fp32 输出的 fma），是混合精度训练的底层支撑。

#### 9.7.6-9.7.7 Comparison and Selection Instructions

`set`、`setp`（设置谓词）、`selp`（根据谓词选择）、`slct`（根据符号选择）。

#### 9.7.8 Logic and Shift Instructions（逻辑和移位指令）

`and`、`or`、`xor`、`not`、`cnot`、`lop3`（3输入任意逻辑运算）、`shf`（funnel shift）、`shl`、`shr`。

**注意点：**
- `lop3` 可以在一条指令中实现任意 3 输入逻辑函数（通过 LUT 编码），对位运算密集的应用很高效。
- `shf`（funnel shift）可实现 64 位跨两个 32 位寄存器的移位，常用于密码学和位操作。

#### 9.7.9 Data Movement and Conversion Instructions（数据搬运与转换指令）

##### Cache Operators（缓存操作符）

| 操作符 | 用于 | 含义 |
|--------|------|------|
| `.ca` | Load | Cache at all levels |
| `.cg` | Load | Cache at L2 only |
| `.cs` | Load | Cache streaming (低优先驻留) |
| `.lu` | Load | Last use |
| `.cv` | Load | Don't cache, volatile |
| `.wb` | Store | Write-back |
| `.cg` | Store | Cache at L2 only, bypass L1 |
| `.cs` | Store | Cache streaming |
| `.wt` | Store | Write-through |

##### 关键指令

- **`ld`/`st`**：加载/存储（支持各种状态空间、缓存策略、向量化、原子性限定符）
- **`mov`**：寄存器间移动、常量加载
- **`shfl.sync`**：Warp 内 shuffle（线程间直接交换寄存器值）
- **`cvt`**：类型转换
- **`cvta`**：地址空间转换（generic ↔ specific）
- **`mapa`**：跨 CTA 地址映射（Cluster 内）
- **`prefetch`**：预取数据到缓存

##### Asynchronous Copy（异步拷贝）

**是什么？**  
`cp.async` 系列指令直接从 global memory 异步拷贝到 shared memory，绕过寄存器文件。

**为什么？**  
- 传统方式：ld.global → reg → st.shared（占用寄存器、串行）
- 异步方式：cp.async（不占寄存器、与计算重叠）

**关键指令：**
- `cp.async.bulk`：大块异步拷贝（TMA 硬件加速）
- `cp.reduce.async.bulk`：异步拷贝 + 归约
- `cp.async.bulk.tensor`：基于 tensor descriptor 的异步拷贝

**注意点：**
- 异步拷贝是 Hopper+ 架构实现高性能 GEMM 的关键——通过 TMA 实现 global→shared 的流水线。
- 需要配合 `mbarrier` 同步机制管理异步操作的完成。

#### 9.7.10 Fabric Instructions（Fabric 通信指令）

**是什么？（9.3 新增）**  
面向多 GPU 互联（NVLink Fabric）的通信原语，支持 put/get/reduce 操作。

**关键概念：**
- **CFT Handle**：Communication Fabric Token，标识一次 fabric 操作
- `fabric.try_get`/`fabric.try_put`：非阻塞的远程数据获取/写入
- `fabric.try_red`：远程归约
- `fabric.wait`：等待 fabric 操作完成
- `fabric.submit`：提交 fabric 操作

**注意点：**
- 这是面向 NVLink 多 GPU 集群的底层通信原语，与 NCCL 等高层库底层实现紧密相关。
- 学术研究中如涉及自定义 collective 通信算法，可直接利用这些指令。

#### 9.7.11-9.7.12 Texture / Surface Instructions

纹理采样（`tex`、`tld4`）和 Surface 读写（`suld`、`sust`、`sured`），主要用于图形渲染，AI 应用较少直接使用。

#### 9.7.13 Control Flow Instructions（控制流指令）

- `bra`：无条件/条件跳转
- `brx.idx`：间接跳转（switch-like）
- `call`/`ret`：函数调用/返回
- `exit`：线程退出

#### 9.7.14 Parallel Synchronization and Communication Instructions（并行同步与通信指令）

**设计背景与演进：**

GPU 同步指令的演进反映了硬件协作粒度的扩大：

| 时代 | 硬件 | 同步粒度 | 关键指令 |
|------|------|----------|----------|
| Tesla/Fermi (sm_1x-2x) | Warp lockstep | Warp 隐式同步 | `bar.sync` |
| Kepler-Pascal (sm_3x-6x) | Warp lockstep | CTA barrier | `bar.sync`, `atom` |
| Volta (sm_70) | Independent threads | Warp explicit sync | `bar.sync`, `shfl.sync`, `vote.sync` |
| Ampere (sm_80) | Async engine | Async pipeline | `cp.async`, `mbarrier` |
| Hopper (sm_90) | Cluster | Cross-CTA + async | `barrier.cluster`, `mbarrier` + TMA |
| Blackwell (sm_100) | Fabric | Multi-GPU | `fabric.*`, `red.async` |

**第一性原理**：每一代新硬件引入新的协作层次或异步能力，相应地需要新的同步原语来管理其正确性。同步指令的演化趋势是：从"全停等待"走向"分离式、异步、非阻塞"。

##### bar / barrier（Barrier 同步）

- `bar.sync`：CTA 内所有线程同步
- `bar.arrive`/`bar.wait`：到达/等待分离（split-phase barrier）
- `barrier.cluster`：Cluster 级别同步

#### membar / fence（内存屏障）

- `membar.cta`/`.gpu`/`.sys`：传统 memory barrier（弃用中）
- `fence.acquire`/`.release`/`.acq_rel`/`.sc`：新式 fence，与作用域配合使用
- `fence.proxy.alias`：虚拟地址别名 fence
- `fence.proxy.async`：异步代理 fence

**Fence 是什么？**

Fence（内存栅栏）是一种同步指令，用于**约束内存操作的可见性顺序**，但不执行任何数据读写本身。它告诉硬件："在这条指令前后的内存操作，不能随意重排"——是一道逻辑上的"栅栏"，将内存操作分成"栅栏前"和"栅栏后"两组，保证特定的可见性顺序。

| 指令 | 语义 | 作用 |
|------|------|------|
| `fence.release.scope` | Release | 保证栅栏**之前**的所有写入对其他线程可见 |
| `fence.acquire.scope` | Acquire | 保证栅栏**之后**的读取能看到其他线程发布的写入 |
| `fence.acq_rel.scope` | 两者兼具 | 同时具有 release + acquire 效果 |
| `fence.sc.scope` | 顺序一致 | 最强保证——所有线程看到相同的 fence 全序 |
| `fence.proxy.async` | 代理栅栏 | 让异步拷贝（TMA）的结果对普通 load/store 可见 |
| `fence.proxy.alias` | 别名栅栏 | 让通过不同虚拟地址访问同一物理地址时顺序正确 |

**为什么需要 Fence？**

GPU 硬件为了性能会激进地重排内存操作（store buffer、cache 写合并等）。没有 fence，线程 A 写入的数据可能被线程 B 以错乱顺序观察到：

```ptx
// 没有 fence 的危险写法：
st.global.u32 [data], 42;                  // 写数据
st.relaxed.gpu.global.u32 [flag], 1;       // 写标志
// ⚠ 硬件可能重排，导致 flag=1 先于 data=42 被其他线程看到！

// 正确写法——用 fence 防止重排：
st.global.u32 [data], 42;                  // 写数据
fence.release.gpu;                          // ← 栅栏：保证 data 写入在 flag 之前可见
st.relaxed.gpu.global.u32 [flag], 1;       // 写标志
```

**Fence vs Barrier 的硬件实现路径区别：**

两者作用于完全不同的硬件单元：

```
┌─────────────────────────────────────────────────────────┐
│                      SM (流多处理器)                      │
│                                                         │
│  ┌──────────┐     ┌──────────────────┐                  │
│  │ Warp     │────▶│  Execution Units │──── ALU/FPU/TC   │
│  │ Scheduler│     │  (计算管线)       │                  │
│  └────┬─────┘     └──────────────────┘                  │
│       │                                                 │
│       │ barrier   ┌──────────────────┐                  │
│       ▼ 作用点    │  Barrier Unit    │  ◀── bar.sync    │
│  ┌────────────┐   │  (计数器/位掩码)  │                  │
│  │ 停止调度    │   └──────────────────┘                  │
│  │ 该 warp    │                                         │
│  └────────────┘                                         │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │            Memory Subsystem                   │       │
│  │  ┌────────────┐  ┌─────┐  ┌─────┐           │       │
│  │  │Store Buffer│─▶│ L1  │─▶│ L2  │─▶ DRAM    │       │
│  │  │(写缓冲区)  │  │Cache│  │Cache│           │       │
│  │  └────────────┘  └─────┘  └─────┘           │       │
│  │       ▲                                      │       │
│  │       │ fence 作用点                          │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

**Fence 的硬件行为（线程不停）：**

当线程执行 `fence.release.gpu` 时：
1. 硬件在 store buffer 中插入一个"排序标记"
2. 标记含义："此标记之前的 entry 必须在之后的 entry 前 drain 到 L2"
3. 线程继续执行后续的 ALU 指令——**不阻塞**
4. 只有后续的 memory 指令会被 hold 住，直到 store buffer 中早期 entry drain 完成

Fence 在不同 scope 下的硬件动作：

| Scope | 硬件动作 |
|-------|----------|
| `.cta` | 确保 store buffer entries 对同 SM 上其他 warp 可见（drain 到 L1） |
| `.gpu` | 确保 writes propagate 到 L2（全 GPU 共享层） |
| `.sys` | 确保 writes 通过 memory controller 到达系统级可见点（PCIe/NVLink 可见） |

类比：fence 像邮局的"先寄先到保证"——你告诉邮局"这批信必须在下一批之前送到"，但你人不需要站在邮局等。

**Barrier 的硬件行为（线程全停）：**

当线程执行 `bar.sync 0` 时：
1. Warp Scheduler 将该 warp 标记为 "blocked on barrier #0"
2. 该 warp 从 ready queue 中移除——**不再被调度，计算单元空转**
3. Barrier Unit 中的 arrived_count++
4. 当 arrived_count == expected_count（CTA 中所有线程到齐），硬件释放所有等待的 warp
5. 所有 warp 重新放入 ready queue，恢复调度

Barrier Unit 硬件结构（每个 SM 有 16 个 barrier 资源）：
```
Barrier #0:  [ expected: 256 | arrived: 0 | waiting_warps: 0b00000000 ]
Barrier #1:  [ expected: 256 | arrived: 0 | waiting_warps: 0b00000000 ]
...
Barrier #15: [ expected: 128 | arrived: 0 | waiting_warps: 0b00000000 ]
```

类比：barrier 像会议签到——所有人到齐才能开始，先到的人只能坐着等。

**核心对比总结：**

| 维度 | Fence | Barrier |
|------|-------|--------|
| 作用硬件 | Memory subsystem（store buffer, cache） | Warp scheduler（调度队列） |
| 线程是否停 | **不停**（继续执行非依赖指令） | **停**（从 ready queue 移除） |
| 约束对象 | 内存操作的全局可见顺序 | 线程的执行进度 |
| 开销来源 | cache flush/invalidate 延迟 | 计算单元空转等待 |
| 可跨 CTA | 可以（通过 scope 控制） | 不可以（仅 CTA 内，除 `barrier.cluster`） |

**两者协作的典型场景：**

```ptx
// 只用 fence（不停线程）——适合跨 CTA 的 flag 通信：
fence.release.gpu;
st.relaxed.gpu.global.u32 [flag], 1;
// 线程继续做其他工作...不等任何人

// 只用 barrier（线程全停）——适合 CTA 内数据交换：
st.shared.u32 [smem + tid*4], result;    // 每个线程写自己的结果
bar.sync 0;                              // 所有人到齐
ld.shared.u32 %r0, [smem + other*4];     // 安全读其他线程的结果

// 两者配合——异步 pipeline：
cp.async.bulk ... [mbar];                // 发起异步拷贝
// 线程继续计算（不停）
mbarrier.try_wait.acquire ... [mbar];    // 等异步完成（类似 barrier）
fence.proxy.async;                       // fence：让异步路径数据对普通 load 可见
ld.shared.f32 %f0, [smem];              // 安全读取
```

##### atom / red（原子操作 / 归约）

- `atom`：原子 RMW（Read-Modify-Write），支持 add/min/max/cas/exch/and/or/xor 等
- `red`：归约（write-only atomic），不返回旧值

**注意点：**
- `red` 不形成 acquire pattern！需要同步时用 `atom` 替代。
- 原子操作支持 scope 限定（`.cta`/`.gpu`/`.sys`），scope 越大开销越大。

##### vote.sync / match.sync / activemask / redux.sync / elect.sync

- `vote.sync`：warp 内投票（`.all`/`.any`/`.uni`/`.ballot`）
- `match.sync`：warp 内值匹配
- `redux.sync`：warp 内归约
- `elect.sync`：选举一个 active 线程

##### mbarrier（异步 Barrier）

**是什么？**  
`mbarrier`（Memory Barrier）是 Ampere/Hopper 架构引入的异步同步机制，用于管理异步数据搬运的完成。

**设计背景与第一性原理：**

传统 `bar.sync` 是"全停等待"模型：所有线程停下来等待彼此。这在异步数据搬运场景中严重低效：
- 数据搬运和计算本应并行
- 线程应该在 arrive 后继续做其他工作，而不是等待
- 异步操作的完成时间不确定，需要更灵活的检测机制

mbarrier 解决这些问题的方式：
- **Split-phase**：arrive 和 wait 分离——到达后可继续工作
- **Async tracking**：可以跟踪异步拷贝操作的完成（tx-count 机制）
- **Phase-based**：自动循环重用，支持多缓冲流水线

**mbarrier 生命周期：**
1. `mbarrier.init` → 初始化（设置期望到达数）
2. `mbarrier.arrive` / `mbarrier.arrive.expect_tx` → 线程到达和/或注册异步传输
3. `mbarrier.test_wait` / `mbarrier.try_wait` → 检测/等待完成
4. 自动重初始化进入下一 phase
5. `mbarrier.inval` → 废弃（当不再使用时）

**PTX 示例——双缓冲 TMA Pipeline（最重要的使用模式）：**

```ptx
// ═══════════════════════════════════════════════
// Double-Buffer TMA Pipeline
// Buffer 0 和 Buffer 1 交替使用，数据搬运和计算重叠
// ═══════════════════════════════════════════════
.shared .align 128 .b8 smem_buf[2][TILE_SIZE];  // 双缓冲
.shared .align 8 .b64 mbar[2];                  // 每个 buffer 一个 mbarrier

// == 初始化（Leader 线程执行） ==
mbarrier.init.shared.b64 [mbar+0], thread_count;
mbarrier.init.shared.b64 [mbar+8], thread_count;

// == Prolog: 发起第一次异步拷贝到 buffer 0 ==
mbarrier.arrive.expect_tx.shared.b64 _, [mbar+0], TILE_SIZE;
cp.async.bulk.shared::cta.global.relaxed.gpu
    [smem_buf+0], [global_src], TILE_SIZE, [mbar+0];

// == 主循环 ==
mainLoop:
    // -- Stage 1: 发起下一个 tile 的拷贝到 buffer 1 --
    mbarrier.arrive.expect_tx.shared.b64 _, [mbar+8], TILE_SIZE;
    cp.async.bulk.shared::cta.global.relaxed.gpu
        [smem_buf+TILE_SIZE], [global_src+TILE_SIZE], TILE_SIZE, [mbar+8];

    // -- Stage 2: 等待 buffer 0 就绪，执行计算 --
    waitBuf0:
        mbarrier.try_wait.acquire.cta.shared::cta.b64 ready, [mbar+0], phase0;
        @!ready bra waitBuf0;

    // Buffer 0 数据已就绪，执行计算
    ld.shared.f32 %f0, [smem_buf+0];   // 读取 buffer 0
    // ... 计算 ...

    // -- Stage 3: 发起再下一个 tile 拷贝到 buffer 0 --
    mbarrier.arrive.expect_tx.shared.b64 _, [mbar+0], TILE_SIZE;
    cp.async.bulk.shared::cta.global.relaxed.gpu
        [smem_buf+0], [global_src+2*TILE_SIZE], TILE_SIZE, [mbar+0];

    // -- Stage 4: 等待 buffer 1，计算 --
    waitBuf1:
        mbarrier.try_wait.acquire.cta.shared::cta.b64 ready, [mbar+8], phase1;
        @!ready bra waitBuf1;

    ld.shared.f32 %f0, [smem_buf+TILE_SIZE];  // 读取 buffer 1
    // ... 计算 ...

    // 更新指针，继续循环
    bra mainLoop;
```

**`mbarrier.arrive.expect_tx` 的关键作用：**
- 告诉 mbarrier："我期望在当前 phase 中还会有 TILE_SIZE 字节的异步传输"
- 当 cp.async.bulk 实际完成传输后，硬件自动减少 tx-count
- 当 tx-count 为 0 且所有线程都 arrive 后，phase 完成

**关键操作总结：**
- `mbarrier.init`：初始化
- `mbarrier.arrive`：通知到达
- `mbarrier.arrive.expect_tx`：到达 + 注册期望传输字节数
- `mbarrier.test_wait`：非阻塞检测完成
- `mbarrier.try_wait`：可能阻塞的等待（带超时）
- `mbarrier.arrive_drop`：到达并减少后续 phase 的期望计数（线程提前退出）

**注意点：**
- mbarrier 是实现 TMA pipeline（双缓冲/多缓冲）的核心机制。
- 在高性能 GEMM 实现中，mbarrier 用于同步 producer（数据搬运）和 consumer（计算）。
- **常见错误**：忘记 `arrive.expect_tx` 导致 mbarrier 永远不会完成（tx-count 不到 0）。
- **Layout v0 vs v1**：v1 支持 conditional phase 和 report 操作（PTX 9.3 新增），用于更复杂的异步控制流。
- **mbarrier vs bar.sync 的选择**：如果只需要简单的 CTA 内线程同步，用 `bar.sync`；如果涉及异步拷贝或需要 split-phase，用 mbarrier。

##### griddepcontrol

**是什么？**  
支持 Grid 级别的依赖控制（用于 Programmatic Dependent Launch）。

**设计背景：**  
传统 CUDA 中，前后相依的 kernel 必须等到前一个完全结束后才启动后一个。但很多场景中，前驱 Grid 的"有效输出"早在它完全退出之前就已就绪。`griddepcontrol` 允许 kernel 内部显式发出"我的输出已就绪"信号，让后续 Grid 提前启动。

**语法与语义：**
```ptx
griddepcontrol.launch_dependents;  // 发出"可以启动依赖者"信号
griddepcontrol.wait;               // 等待所有前驱完成
```

**内存同步保证：**
- 如果前驱使用了 `griddepcontrol.launch_dependents`，则依赖 Grid **必须**使用 `griddepcontrol.wait` 确保正确的内存可见性。
- `fence.release.gpu` + `griddepcontrol.launch_dependents` 可与依赖 Grid 开始建立 synchronize-with 关系。
- PTX ISA 7.8 引入，需要 sm_90+。

##### clusterlaunchcontrol

**是什么？**  
Cluster 启动控制指令（sm_100+），允许已运行的 Cluster 尝试"取消"一个还未启动的 Cluster，从而窃取它的工作。这是 GPU 硬件级 work-stealing 的底层支撑。

**关键指令：**
```ptx
// 异步尝试取消，结果通过 mbarrier 通知
clusterlaunchcontrol.try_cancel.async.mbarrier::complete_tx::bytes
    .multicast::cluster::all.b128 [response_addr], [mbar];

// 查询取消结果
clusterlaunchcontrol.query_cancel.is_canceled.pred.b128 p, handle;

// 获取被取消 cluster 的 CTA ID
clusterlaunchcontrol.query_cancel.get_first_ctaid.v4.b32.b128
    {xdim, ydim, zdim, _}, handle;
```

**工作流程：**
1. 当前 Cluster 完成工作后，发起 `try_cancel`——尝试取消一个还未被硬件调度的 Cluster
2. 通过 mbarrier 等待异步响应
3. `query_cancel.is_canceled` 检查是否成功
4. 如果成功，获取被取消 Cluster 的 CTA ID，当前 Cluster 接管其工作
5. 如果失败（所有 Cluster 都已启动），当前 Cluster 退出

**注意点：**
- 这是实现硬件级动态负载均衡的关键原语，特别适合工作量不均匀的 kernel。
- `try_cancel` 失败后不应再次尝试（行为未定义）。
- 需要 sm_100+，是 Blackwell 架构的标志性特性。
- 完整示例参见 §7.3 CUDA Dynamic Parallelism 中的 "Cluster-level Work Stealing" 代码。

#### 9.7.15 Warp Level Matrix Multiply-Accumulate Instructions（Warp 级矩阵乘累加指令）

**是什么？**  
Tensor Core 指令，执行 D = A × B + C 矩阵运算。

##### Matrix Shape（矩阵形状）
- 不同架构支持不同的 m×n×k 组合
- 如 m16n8k16、m16n8k32 等

##### Matrix Data-types
- 支持 f16、bf16、tf32、f64、整数类型以及各种 FP8/FP6/FP4 格式

##### wmma 指令
- `wmma.load`：从 shared/global memory 加载矩阵 fragment
- `wmma.store`：存储结果 fragment
- `wmma.mma`：执行矩阵乘累加

##### mma 指令
- 比 wmma 更底层、更灵活
- 支持更多数据类型和矩阵形状
- 支持稀疏矩阵（`mma.sp`）

##### Block Scaling（块缩放）
- 支持 MX（Microscaling）格式的块级缩放因子
- 用于 FP8/FP6/FP4 等低精度格式的精度恢复

**注意点：**
- Tensor Core 是 AI 训练/推理吞吐的关键——一条 `mma` 指令可完成 16×8×16 的矩阵乘。
- 不同架构代的 Tensor Core 支持不同的数据类型和矩阵大小。
- 数据布局必须严格匹配硬件期望的 fragment 格式，否则结果错误。
- 稀疏矩阵支持（2:4 结构化稀疏）可将吞吐翻倍。

#### 9.7.16 Asynchronous Warpgroup Level Matrix Multiply-Accumulate (wgmma)

**是什么？**  
Hopper 架构引入的 warp group 级异步矩阵乘累加，支持更大的矩阵 tile。

**关键特性：**
- **Warpgroup**：4 个连续 warp（128 线程）协作
- 操作数 A 可从 shared memory 直接读取（无需加载到寄存器）
- 支持异步执行，与数据搬运重叠

**关键指令：**
- `wgmma.mma_async`：异步矩阵乘累加
- `wgmma.fence`：保证 shared memory 输入的就绪
- `wgmma.commit_group`/`wgmma.wait_group`：管理异步操作组

**注意点：**
- wgmma 是 Hopper 上实现峰值 GEMM 性能的关键指令。
- 必须严格遵循 fence → commit → wait 的同步协议。
- 操作数 A 从 shared memory 读取时，数据布局必须满足 swizzle 要求。

#### 9.7.17 TensorCore 5th Generation Family Instructions (tcgen05)

**是什么？**  
第 5 代 Tensor Core 指令（Blackwell sm_100+ 架构），引入 Tensor Memory 概念。

**关键创新：**
- **Tensor Memory**：专用于矩阵运算的片上内存空间，由硬件管理
- `tcgen05.alloc`/`tcgen05.dealloc`：分配/释放 Tensor Memory
- `tcgen05.ld`/`tcgen05.st`：Tensor Memory 与寄存器间的数据移动
- `tcgen05.cp`：Shared Memory ↔ Tensor Memory 的数据拷贝
- `tcgen05.mma`：使用 Tensor Memory 操作数的矩阵乘累加

**关键概念：**
- **Matrix Descriptors**：描述 Tensor Memory 中矩阵布局的描述符
- **Swizzling**：数据在内存中的交错存储模式（减少 bank conflict）
- **Issue Granularity**：指令发射粒度（`warpgroup`、`.cta_group::1`/`::2`）
- **Block Scaling with MX formats**：支持各种 Microscaling 格式

**注意点：**
- tcgen05 代表了目前最新的 Tensor Core 编程模型。
- Tensor Memory 是独立于 shared memory 和寄存器的第三类片上存储。
- 稀疏矩阵支持和多种低精度格式（FP4/FP6/FP8 + block scaling）是 Blackwell 的标志性特性。
- 在学术研究中，理解 tcgen05 的 descriptor 格式和 swizzle 模式是实现高性能 kernel 的前提。

#### 9.7.18 Stack Manipulation Instructions

`stacksave`/`stackrestore`：保存和恢复栈指针，用于变长栈帧管理。

#### 9.7.19 Video Instructions

标量和 SIMD 视频处理指令（主要用于视频编解码加速）。

#### 9.7.20 Miscellaneous Instructions

- `brkpt`：断点（调试）
- `nanosleep`：线程休眠指定纳秒
- `pmevent`：触发性能监控事件
- `trap`：触发异常
- `setmaxnreg`：动态设置最大寄存器数（运行时 occupancy 调整）

**注意点：**
- `setmaxnreg` 是 sm_90+ 的重要优化手段——可在 kernel 不同阶段动态调整寄存器使用，提升 occupancy。
- `nanosleep` 可用于实现 spin-wait 的退避策略，减少资源竞争。

---

## 10 Special Registers（特殊寄存器）

**是什么？**  
只读的预定义寄存器，提供线程/CTA/Grid/Cluster 的标识和硬件状态信息。

### 关键特殊寄存器

| 寄存器 | 含义 |
|--------|------|
| `%tid` | 线程在 CTA 内的 ID（3D） |
| `%ntid` | CTA 的维度大小 |
| `%laneid` | 线程在 warp 内的 lane ID (0-31) |
| `%warpid` | warp 在 CTA 内的 ID |
| `%ctaid` | CTA 在 Grid 内的 ID（3D） |
| `%nctaid` | Grid 的维度大小 |
| `%smid` | 当前 SM 的 ID |
| `%gridid` | Grid 的 ID |
| `%clusterid` | Cluster 的 ID |
| `%cluster_ctaid` | CTA 在 Cluster 内的 ID |
| `%cluster_ctarank` | CTA 在 Cluster 内的 rank |
| `%lanemask_eq/le/lt/ge/gt` | 基于 lane ID 的掩码 |
| `%clock` / `%clock64` | 周期计数器 |
| `%globaltimer` | 全局纳秒计时器 |
| `%dynamic_smem_size` | 动态 shared memory 大小 |
| `%total_smem_size` | 总 shared memory 大小 |
| `%current_graph_exec` | 当前 CUDA Graph 执行句柄 |

**注意点：**
- `%smid` 可用于诊断调度行为，但不应依赖它做正确性逻辑。
- `%clock` 用于 kernel 内性能计时，但在跨 warp 比较时需注意时钟不同步问题。
- `%lanemask_*` 常用于 warp 内集合操作的掩码计算。

---

## 11 Directives（伪指令/编译指示）

### 11.1 PTX Module Directives（模块指令）

| 指令 | 作用 |
|------|------|
| `.version` | 指定 PTX ISA 版本号 |
| `.target` | 指定目标架构（如 sm_90） |
| `.address_size` | 指定地址位宽（32/64） |

### 11.2 Specifying Kernel Entry Points and Functions

| 指令 | 作用 |
|------|------|
| `.entry` | 声明 kernel 入口函数 |
| `.func` | 声明设备函数 |
| `.alias` | 函数别名 |

### 11.3 Control Flow Directives

- `.branchtargets`：声明间接跳转目标
- `.calltargets`：声明间接调用目标
- `.callprototype`：声明间接调用原型

### 11.4 Performance-Tuning Directives（性能调优指令）

| 指令 | 作用 |
|------|------|
| `.maxnreg` | 限制每线程最大寄存器数 |
| `.maxntid` | 限制每 CTA 最大线程数 |
| `.reqntid` | 要求确切的 CTA 线程数 |
| `.minnctapersm` | 要求每 SM 最少 CTA 数 |
| `.noreturn` | 标记函数不返回 |
| `.pragma` | 编译器提示 |

**注意点：**
- `.maxnreg` + `.minnctapersm` 是控制 occupancy 的关键手段。
- 限制寄存器数会增加 occupancy 但可能引入 spill。
- 需在 occupancy 和指令级并行（ILP）之间平衡。

### 11.5 Debugging Directives

`@@dwarf`、`.section`、`.file`、`.loc`——嵌入 DWARF 调试信息。

### 11.6 Linking Directives

- `.extern`：引用外部符号
- `.visible`：导出符号
- `.weak`：弱符号（链接时可被覆盖）
- `.common`：公共符号

### 11.7 Cluster Dimension Directives

- `.reqnctapercluster`：指定 Cluster 中 CTA 数量
- `.explicitcluster`：要求必须显式指定 Cluster 维度
- `.maxclusterrank`：Cluster 最大 CTA 数

### 11.8 Miscellaneous Directives

- `.blocksareclusters`：声明每个 block 就是一个 cluster
- `.language`：指定源语言（CUDA C++ 等）

---

## 12 Descriptions of .pragma Strings（Pragma 字符串描述）

### 12.1 "nounroll"

禁止编译器展开循环——当循环体过大或展开无益时使用。

### 12.2 "used_bytes_mask"

指定 load/store 实际使用的字节掩码——告知编译器部分字节未使用，允许优化。

### 12.3 "enable_smem_spilling"

允许编译器将寄存器溢出到 shared memory（而非 local memory），在 shared memory 充足时可降低延迟。

### 12.4 "frequency"

标注代码块的执行频率（hot/cold path 提示），指导编译器优化布局。

### 12.5 "mma_throughput"（9.3 新增）

提示矩阵乘累加的吞吐期望，允许编译器在延迟和吞吐之间做不同的调度决策。

**注意点：**
- `enable_smem_spilling` 是一个重要但容易忽视的优化——当 shared memory 使用率低但寄存器压力大时非常有效。
- `mma_throughput` 是新的优化提示，可能在高性能 GEMM kernel 中有用。

---

## 13 Release Notes（发布说明）

### 13.1 Changes in PTX ISA Version 9.3

详见 1.3 节（Fabric 指令、mbarrier 增强、clmad 等）。

### 关键历史版本里程碑

| 版本 | 关键特性 |
|------|---------|
| 9.0-9.3 | Fabric 通信、tcgen05（5th gen TC）、低精度格式扩展 |
| 8.0-8.8 | wgmma（异步 GEMM）、setmaxnreg、Cluster、TMA |
| 7.0-7.8 | mbarrier、cp.async.bulk、Cluster 支持 |
| 6.0-6.5 | wmma（Tensor Core V1）、独立线程调度 |
| 5.0 | Dynamic Parallelism 增强 |
| 4.0 | 统一内存、.managed 属性 |

---

## 全局注意点总结（学术优化与工业实践）

### 性能优化关键

1. **内存层次利用**：Register > Shared > L2 > Global，设计数据流时优先使用快速内存。
2. **异步流水线**：利用 cp.async + mbarrier 实现数据搬运与计算的重叠（double/triple buffering）。
3. **Tensor Core 利用**：选择合适的数据类型和矩阵形状，确保数据布局满足硬件要求。
4. **Occupancy vs ILP（占用率 vs 指令级并行）**

   **是什么？**  
   GPU 性能优化中一对核心的、往往相互矛盾的策略：
   - **Occupancy（占用率）**：SM 上实际活跃的 Warp 数 / SM 硬件支持的最大 Warp 数。高 Occupancy 意味着 GPU 可以在某个 Warp 等待内存访问时切换到其他 Warp 执行，从而隐藏延迟（latency hiding）。
   - **ILP（Instruction-Level Parallelism，指令级并行）**：同一个线程内同时执行多条独立指令的能力。即使没有 Warp 切换，单个 Warp 内也可以有多条指令同时在不同功能单元（FP32、SFU、LD/ST、Branch）上流水执行。

   **为什么是核心矛盾？**  
   两者竞争同一个有限的资源池——**寄存器文件（Register File）**：
   ```
   Registers/thread ↑  →  ILP ↑  →  Occupancy ↓
   Registers/thread ↓  →  ILP ↓  →  Occupancy ↑
   ```
   - 提升 ILP 通常需要更多寄存器（存中间变量、展开循环）
   - 高寄存器使用会减少 SM 上能驻留的 Warp 数，降低 Occupancy

   **Occupancy 的限制因素：**

   | 资源 | 说明 |
   |------|------|
   | Registers/thread | 每个线程使用的寄存器数，是最大瓶颈 |
   | Shared Memory/block | 每个 Block 使用的共享内存量 |
   | Threads/block | Block 大小（必须是 Warp 的倍数） |
   | Blocks/SM | SM 有最大 Block 数上限（如 Hopper 为 32） |

   **Hopper 架构的实际视角（每 SM 65536 个 32-bit 寄存器）：**
   ```
   若每线程用  32 regs → 最多 2048 threads/SM → 64 warps → Occupancy 100%
   若每线程用 128 regs → 最多  512 threads/SM → 16 warps → Occupancy  25%
   若每线程用 255 regs → 最多  256 threads/SM →  8 warps → Occupancy 12.5%
   ```
   但注意：**Occupancy 并非越高越好**。研究表明，在大多数 kernel 中，超过 ~50% Occupancy 后收益递减，而 ILP 带来的计算吞吐提升可能更显著。

   **如何选择？取决于瓶颈类型：**

   | Kernel 瓶颈 | 优先策略 | 原因 |
   |---|---|---|
   | **Memory-bound**（带宽受限） | 高 Occupancy | 需要大量 Warp 隐藏内存延迟（数百周期） |
   | **Compute-bound**（计算受限） | 高 ILP | 计算指令多，需要填满功能单元流水线 |
   | **Latency-bound**（延迟受限） | 两者兼顾 | 既要 Warp 切换，也要指令重叠 |

   **ILP 的实现方式：**
   ```ptx
   // 高 ILP 示例：两条独立乘法链（无数据依赖）
   mul.f32 %f1, %x, %y;     // 链1
   mul.f32 %f2, %x, %z;     // 链2，与链1无依赖
   add.f32 %r1, %f1, 1.0;   // 链1继续
   add.f32 %r2, %f2, 2.0;   // 链2继续
   // GPU 可以并行发射两条乘法到不同的 FP32 管线
   ```
   - 写多条无数据依赖的独立计算
   - 编译器自动展开（`#pragma unroll`）
   - 手动交错（interleave）独立计算链

   **PTX 层面的调控手段：**

   | 手段 | 指令/伪指令 | 效果 |
   |------|-----------|------|
   | 限制寄存器数 | `.maxnreg N` | 降低每线程寄存器 → 提升 Occupancy（但可能引入 spill） |
   | 要求最小 CTA/SM | `.minnctapersm N` | 强制编译器限制资源以满足最小 Occupancy |
   | 运行时动态调整 | `setmaxnreg` (sm_90+) | kernel 不同阶段使用不同寄存器数——数据搬运阶段少用寄存器提升 Occupancy，计算阶段多用寄存器提升 ILP |
   | 循环展开提示 | `#pragma unroll` / `.pragma "nounroll"` | 展开提升 ILP / 不展开节省寄存器 |

   **PTX 示例——运行时动态寄存器调整（sm_90+）：**
   ```ptx
   .entry my_kernel(...) {
       // 阶段 1：数据搬运（Memory-bound）
       // 此时不需要太多计算，降低寄存器数让更多 Warp 驻留
       setmaxnreg.dec.sync.aligned.u32 32;   // 降低到 32 regs/thread
       cp.async.bulk ...;                     // 发起异步拷贝
       // 更多 Warp 可以并行隐藏内存延迟

       // 阶段 2：密集计算（Compute-bound）
       setmaxnreg.inc.sync.aligned.u32 128;  // 提升到 128 regs/thread
       // 更多寄存器 → 更多中间变量 → 更高 ILP
       fma.rn.f32 ...;  // 密集计算
       fma.rn.f32 ...;
   }
   ```

   **实践建议：**
   1. **先用 Nsight Compute 看瓶颈**：`Memory Throughput` 高 → Occupancy 优先；`Compute Throughput` 高 → ILP 优先
   2. **`--maxrregcount=N`**（编译选项）或 `.maxnreg N`（PTX 伪指令）可强制限制寄存器使用来提升 Occupancy，但要验证性能是否真的提升
   3. **`setmaxnreg`**（sm_90+）是更精细的调控——允许同一 kernel 内不同阶段切换
   4. **Warp 内 32 线程共享同一条 PC**（指令流），所以 ILP 是指令流中连续多条独立指令被调度器重叠发射
   5. **不要盲目追求 100% Occupancy**——当寄存器压力导致 spill 到 local memory 时，性能损失远大于 Occupancy 带来的收益

   **一句话总结**：Occupancy 是"靠切换线程来隐藏等待"，ILP 是"靠指令并行来填满流水线"。两者竞争寄存器资源，最优平衡点取决于 kernel 是访存密集还是计算密集。PTX 提供了 `.maxnreg`、`.minnctapersm`、`setmaxnreg` 三层手段来精确控制这个平衡。
5. **Warp divergence 最小化**：保持 warp 内统一控制流。
6. **Bank conflict 避免**：Shared memory 访问时注意 32-bank 的 bank conflict 问题。

   #### Bank Conflict 详解

   **硬件结构**：Shared memory 被划分为 **32 个 bank**，每个 bank 每个时钟周期只能服务一次读写。连续的 4 字节（32-bit）分别映射到 bank 0, 1, 2, ..., 31，然后 bank 0 再次开始（即地址 `addr` 映射到 `bank = (addr / 4) % 32`）。

   **冲突条件**：当一个 warp 中的多个线程**同时**访问**同一个 bank 的不同地址**时，就会产生 bank conflict，这些访问必须被串行化，性能下降为原来的 1/N（N = 冲突数）。

   **注意**：如果多个线程访问**同一 bank 的同一地址**，则触发 **broadcast**（广播），不产生冲突——这是免费的。

   #### 典型冲突场景与解决方案

   | 场景 | 冲突原因 | 解决方案 |
   |------|---------|----------|
   | 列优先访问 32×32 矩阵 | 每列步长 = 32 × 4B = 128B，所有线程落入同一 bank | 添加 padding：每行多加 1 个元素（33 × 32） |
   | 转置操作中对角线访问 | 某些偏移导致多线程式中同一 bank | 使用 XOR 索引打散：`addr = row ^ col` |
   | 步长为 32 的倍数的访问 | 步长是 bank 数的倍数，所有线程命中同一 bank | 调整数据结构布局或引入 padding |

   **核心公式**：
   - 无冲突条件：`bank[i] = (base + i * stride) % 32` 对所有 i ∈ [0, 31] 互不相同
   - 当 `stride` 与 32 互质（如 stride = 1, 3, 5, ...）时，保证无冲突
   - 当 `stride = 32k`（32 的倍数）时，所有线程落入同一 bank → 最严重的 32-way conflict

   #### PTX 示例——无冲突 Shared Memory 访问（带 Padding 的矩阵转置）

   ```ptx
   // ============================================================
   // 矩阵转置：32×32 tile，使用 padding 避免 bank conflict
   // 原始布局：32 × 32 × 4B → 列访问时 stride=32 → 32-way conflict!
   // Padding 布局：32 × 33 × 4B → 列访问时 stride=33 → 无冲突
   // ============================================================

   .version 8.0
   .target sm_90
   .address_size 64

   .visible .entry transpose_bank_free(
       .param .u64 input_ptr,
       .param .u64 output_ptr
   )
   {
       .reg .u32   %r<20>;
       .reg .u64   %rd<10>;
       .reg .pred  %p1;

       // Shared memory: 32 × 33 个 f32（每行 33 列 = padding 1 列）
       .shared .align 4 .f32 tile[1056];  // 32 * 33 = 1056

       // 获取线程 ID
       mov.u32     %r0, %tid.x;          // 线程在 block 内的 x
       mov.u32     %r1, %tid.y;          // 线程在 block 内的 y
       mov.u32     %r2, %ctaid.x;        // block 的 x 索引
       mov.u32     %r3, %ctaid.y;        // block 的 y 索引

       // === 计算输入矩阵的全局地址 ===
       // input_row = blockIdx.y * 32 + threadIdx.y
       // input_col = blockIdx.x * 32 + threadIdx.x
       mad.lo.u32  %r4, %r3, 32, %r1;   // r4 = input_row
       mad.lo.u32  %r5, %r2, 32, %r0;   // r5 = input_col

       // input 偏移 = (input_row * 32 + input_col) * 4
       mad.lo.u32  %r6, %r4, 32, %r5;
       shl.b32     %r6, %r6, 2;          // r6 = byte offset

       ld.param.u64 %rd0, [input_ptr];
       cvt.u64.u32  %rd1, %r6;
       add.u64      %rd2, %rd0, %rd1;

       // === 加载到 shared memory（带 padding）===
       // shared 索引 = threadIdx.y * 33 + threadIdx.x   ← 关键：用 33 而非 32！
       mad.lo.u32  %r7, %r1, 33, %r0;   // r7 = 行 * 33 + 列
       shl.b32     %r7, %r7, 2;          // byte offset in shared

       ld.global.f32  %f0, [%rd2];       // 从 global memory 加载
       cvt.u64.u32    %rd3, %r7;
       st.shared.f32  [tile + %rd3], %f0;  // 存入 shared（33 列 padding）

       // === 同步：确保所有线程完成写入 ===
       bar.sync 0;

       // === 从 shared memory 读取并写入 output（转置后）===
       // 读取时使用转置坐标：读 (threadIdx.x, threadIdx.y) 对应原矩阵的列/行
       // shared 读索引 = threadIdx.x * 33 + threadIdx.y   ← padding 打散 bank
       mad.lo.u32  %r8, %r0, 33, %r1;   // r8 = threadIdx.x * 33 + threadIdx.y
       shl.b32     %r8, %r8, 2;

       cvt.u64.u32    %rd4, %r8;
       ld.shared.f32  %f1, [tile + %rd4];  // 从 shared 读取（无 bank conflict!）

       // output 地址（转置后）
       // output_row = blockIdx.x * 32 + threadIdx.y
       // output_col = blockIdx.y * 32 + threadIdx.x
       mad.lo.u32  %r9,  %r2, 32, %r1;   // output_row
       mad.lo.u32  %r10, %r3, 32, %r0;   // output_col
       mad.lo.u32  %r11, %r9, 32, %r10;
       shl.b32     %r11, %r11, 2;

       ld.param.u64   %rd5, [output_ptr];
       cvt.u64.u32    %rd6, %r11;
       add.u64        %rd7, %rd5, %rd6;
       st.global.f32  [%rd7], %f1;       // 写入转置后的 global memory

       ret;
   }
   ```

   **为什么 padding 有效**：

   ```
   无 padding（stride=32）：
     线程 0 → bank (0*32 + 0) % 32 = bank 0
     线程 1 → bank (1*32 + 0) % 32 = bank 0  ← 冲突！
     线程 2 → bank (2*32 + 0) % 32 = bank 0  ← 冲突！
     ... 全部 32 个线程都在 bank 0 → 32-way conflict

   有 padding（stride=33）：
     线程 0 → bank (0*33 + col) % 32 = bank (col % 32)
     线程 1 → bank (1*33 + col) % 32 = bank (col + 1) % 32
     线程 2 → bank (2*33 + col) % 32 = bank (col + 2) % 32
     ... 每个线程落在不同 bank → 无冲突 ✓
   ```

   #### 无 Padding 替代方案——XOR 索引

   ```ptx
   // 另一种避免 bank conflict 的方法：XOR swizzle
   // 适用于 2D 数据存取，无需额外内存开销
   //
   // 写入：addr = row * 32 + (col ^ row)
   // 读取：addr = col * 32 + (row ^ col)   ← 转置读取
   //
   // XOR 保证：对同一 row 的 32 个 col，地址映射到不同 bank

   .shared .align 4 .f32 tile_xor[1024];  // 32 × 32，无需 padding

   // 写入 shared（XOR swizzle）
   xor.b32     %r_col_xor, %r0, %r1;       // col ^ row
   mad.lo.u32  %r_idx, %r1, 32, %r_col_xor; // row * 32 + (col ^ row)
   shl.b32     %r_idx, %r_idx, 2;
   // ... st.shared.f32 [tile_xor + offset], %f0;

   bar.sync 0;

   // 读取 shared（XOR swizzle 转置）
   xor.b32     %r_row_xor, %r1, %r0;       // row ^ col（对称，结果相同）
   mad.lo.u32  %r_idx2, %r0, 32, %r_row_xor; // col * 32 + (row ^ col)
   shl.b32     %r_idx2, %r_idx2, 2;
   // ... ld.shared.f32 %f1, [tile_xor + offset2];
   ```

   **方案对比**：

   | 方案 | 优点 | 缺点 |
   |------|------|------|
   | Padding（stride=33） | 实现简单，地址计算直观 | 多浪费 3% shared memory |
   | XOR swizzle | 零额外内存开销 | 地址计算多一条 XOR 指令，调试困难 |
   | 调整访问模式 | 从算法层面消除冲突 | 不是所有算法都能调整 |

### 正确性关键

1. **内存一致性模型**：理解 scope、fence 和 release/acquire 模式，不可依赖隐式顺序。
2. **Independent Thread Scheduling**：Volta 以后不可假设 warp-synchronous 执行。
3. **mixed-size data-race**：绝对避免不同大小的并发读写访问同一地址。
4. **Proxy fence**：异步操作（cp.async）后必须使用适当的 fence 保证可见性。
5. **red vs atom**：`red` 不形成 acquire pattern，需要 acquire 语义时必须用 `atom`。

### 架构演进趋势

1. **异步一切**：从 Hopper 到 Blackwell，越来越多操作变为异步（MMA、数据搬运、通信）。
2. **更低精度**：FP8→FP6→FP4，配合 block scaling 保持精度。
3. **更大协作粒度**：Thread→Warp→Warpgroup→Cluster→Grid，协作范围不断扩大。
4. **Fabric/多 GPU**：底层 ISA 开始直接支持跨 GPU 通信，暗示未来编程模型将更深度整合多 GPU。
5. **Tensor Memory**：第 5 代 TC 引入专用片上存储，简化矩阵数据管理。
