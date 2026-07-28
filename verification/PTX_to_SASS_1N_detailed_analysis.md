# B200 PTX→SASS 旧 1:N 候选逐条重新归因

## 1. 口径与结论强度

本文覆盖 `results/mapping_report.csv` 中当前 `verdict == 1:N` 的全部 **75 条历史候选记录**。
主判据是 B200 / `sm_100a`、CUDA 12.8、`ptxas -O0 -lineinfo` 的
`audited_sass_sequence_O0`。参数加载、结果 sink、尾部 `EXIT/NOP` 以及已经证明无效的
恒等搬移不计入；每条记录的完整原始序列仍以 CSV 和 `sass_dumps/` 为准。

只查看 A/C 类 PTX 与 O0/O3 SASS mnemonic 的逐行对应关系，可直接阅读
[`PTX_to_SASS_1N_mapping_table.md`](PTX_to_SASS_1N_mapping_table.md)。

本轮按照“只映射目标 PTX 的核心硬件动作”的第一性原理重新定口径：

- **核心映射**只统计完成目标动作的核心 SASS opcode；
- `R2UR/MOV` 等操作数布置不计入核心映射；
- `ELECT/PLOP3/BRA` 等编译器插入的 single-thread issue 协议不计入核心映射；
- `WARPSYNC/ENDCOLLECTIVE` 等同步包络与核心 opcode 分列记录，不因落在同一个 PTX
  `.loc` 下就自动算作核心 1:N；
- 只有位宽拆分、软件算法展开或确实由多个硬件动作共同完成的 PTX，才保留为严格
  1:N 候选。

因此，下文标题中的 `完整 N` 只是当前 O0 编译所得的完整 lowering 条数，**不是核心
映射的 N**。现有 CSV 的 `verdict` 尚未按这个新口径重算，不能继续把 75 当成严格
1:N 的数量。

### XP6 读法

本文保留 `R2UR`、`S2UR`、`ELECT`、`WARPSYNC` 等名称，是为了如实记录 B200 的原始
lowering。XP6 不设 `UR`：R→UR 路由、只服务于 `UR/UP` 的准备链和纯 warp-SIMT 发射
协议都不进入 XP6 的 1:N；但 descriptor、地址、CTA/cluster context、barrier state 与
async 依赖仍须以 XP6 的方式表达。`S2R/MOV/LEA/IMAD`、普通谓词和分支只能按 def-use
链判断，不能按名称一并删掉。XP6 统计表见
[`PTX to SASS mapping.md`](PTX%20to%20SASS%20mapping.md#xp6-统计口径)。

旧“1:N”候选在本文中分为以下五种处理状态：

| 标记 | 含义 | 能否直接证明 L0 必须生成多条语义 SASS |
|------|------|------------------------------------------|
| **A** | 算术宽度拆分或软件算法展开 | 能，证据最强 |
| **P** | 核心 opcode 只有一条，但还存在同步、R↔UR 路由或选举协议 | **核心映射按 1:1；协议另存，不算核心 1:N** |
| **C** | 一条 PTX 由多个不同硬件机制共同实现 | 通常能，但应结合目标运行语义复核 |
| **R** | 当前审计仍保留可疑自拷贝/准备指令 | 不能，必须重新审查 |
| **V** | 动态输入 A/B 已证明 O0 附加指令不是核心语义 | **核心映射按 1:1；从 R 类移除** |

表中的 `完整 N` 是当前逐族审计后的 O0 lowering 条数，不是 line-100 原始条数。
“主指令”指最接近
PTX 核心动作的 SASS；“额外指令”说明其余指令为什么出现。

## 2. tcgen05（14 条）

### T01 `tcgen05.mma.cta_group::1.kind::tf32` — 完整 N=18；核心 1:1，P

- PTX 含义：由单个 CTA 发起稠密 TF32 Tensor Core 矩阵乘加，累加器位于 Tensor Memory（TMEM）。
- 主指令：`UTCHMMA` ×1。
- 额外指令：`R2UR` ×11，把 A/B descriptor、TMEM 地址、idesc 和四个 lane mask
  转入 uniform registers；`VOTEU` ×1 把输入 D 谓词统一化；`PLOP3` ×3、`ELECT` ×1、
  `BRA.U.ANY` ×1 构成 single-thread issue 的选举/重试协议。
- 核心映射：`tcgen05.mma → UTCHMMA`，严格按 **1:1** 记录。其余 17 条分别归入
  `operand_materialization` 和 `compiler_issue_protocol`，不得写入核心 1:N 展开规则。
- `ELECT` 归因：原生 `nvdisasm -gp` 行号证据把 PTX 第 28 行的 `setp.ne` 映射到
  `ISETP/UISETP`，而把 `ELECT` 与 `UTCHMMA` 一起归到第 33 行的 `tcgen05.mma`；所以
  `ELECT` 不是前面 `setp` 的结果，而是编译器为 MMA 的 single-thread issue 插入的协议。
- 动态语义：不能解释为“一个 kernel 只给第一个 MMA 选举一次”。每次动态 MMA 发射
  都必须满足 single-thread issue；编译器可以对每条 MMA 插入协议，也可能在证明安全时
  提取或复用控制流，但那是优化，不能作为 PTX→SASS 的固定核心映射。NVIDIA 的
  [PTX ISA 8.7](https://docs.nvidia.com/cuda/archive/12.8.0/parallel-thread-execution/index.html)
  定义 single-thread 发射语义；CUTLASS 文档也明确要求用户以 warp-uniform 方式发出
  `tcgen05.mma`，由编译器处理 `elect_one()`，见
  [tcgen05 execution model](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/cute_dsl_api/cute_nvgpu_tcgen05.html)。

### T02 `tcgen05.mma.cta_group::2.kind::tf32` — 完整 N=22；核心 1:1，P

- PTX 含义：由一对协作 CTA 发起稠密 TF32 Tensor Core 矩阵乘加，共同访问同一组 TMEM 累加器。
- 主指令：`UTCHMMA` ×1。
- 额外指令：`R2UR` ×15，另有 `VOTEU` ×1、`PLOP3` ×3、`ELECT` ×1、`BRA` ×1。
- 判断：与 T01 相同，但 CTA group 2 有八个 disable-output-lane mask，因此比 T01 多
  四条 `R2UR`。核心仍只有一条 MMA，另外 21 条负责双 CTA 操作数与发射协议。

### T03 `tcgen05.mma.sp.cta_group::1.kind::tf32` — 完整 N=18；核心 1:1，P

- PTX 含义：执行带稀疏 metadata 的 TF32 Tensor Core 矩阵乘加，并把结果累加到 TMEM。
- 主指令：`UTCHMMA` ×1，底层编码同时携带 sparse metadata。
- 额外指令：`R2UR` ×11、`VOTEU` ×1、`PLOP3` ×3、`ELECT` ×1、`BRA` ×1。
- 判断：稀疏 metadata 改变了底层操作数，但未增加第二条 MMA；17 条额外指令仍是
  uniform 路由和 single-thread issue 协议。

### T04 `tcgen05.cp.cta_group::1.128x256b` — 完整 N=9；核心 1:1，P

- PTX 含义：按 shared-memory matrix descriptor 描述的布局，把一个 `128x256b` tile 从 shared memory 异步复制到当前 CTA 的 TMEM。
- 主指令：`UTCCP` ×1，执行 Tensor Memory copy。
- 额外指令：`R2UR` ×3 路由源 descriptor/目标 TMEM 操作数；`PLOP3` ×3、
  `ELECT` ×1、`BRA` ×1完成单线程选举发射。
- 判断：核心 copy 是一条，另外八条是操作数和发射协议。

### T05 `tcgen05.ld.sync.aligned.16x64b.x1.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：由整个 warp 协同把一个 `16x64b` TMEM tile 异步加载到各线程的一个 32-bit 寄存器。
- 主指令：`LDTM.16dp64bit` ×1。
- 额外指令：`WARPSYNC.ALL` ×1实现 `.sync.aligned`；`R2UR` ×1把 TMEM 地址从普通
  `R` 寄存器送入 `UR`。
- 判断：核心 load 为 1:1；完整 lowering 是 `WARPSYNC + R2UR + LDTM`。

### T06 `tcgen05.ld.sync.aligned.16x128b.x4.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：由整个 warp 协同把一个 `16x128b.x4` TMEM tile 异步加载到各线程的八个 32-bit 寄存器。
- 主指令：宽向量 `LDTM` ×1，一条指令产生八个 32-bit 输出寄存器。
- 额外指令：`WARPSYNC.ALL` ×1、`R2UR` ×1。
- 判断：输出数量增加并未拆成多个 `LDTM`；与 T05 一样，多出的只是同步和地址路由。

### T07 `tcgen05.st.sync.aligned.16x64b.x1.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：由整个 warp 协同把各线程寄存器中的数据异步写入一个 `16x64b` TMEM tile。
- 主指令：`STTM` ×1。
- 额外指令：`WARPSYNC.ALL` ×1满足同步语义；`R2UR` ×1路由 TMEM 地址。
- 判断：核心 store 一条，完整发射三条。

### T08 `tcgen05.alloc.cta_group::1.sync.aligned` — N=56，C

- PTX 含义：为当前 CTA 分配指定列数的 TMEM，并把分配得到的 TMEM 地址写入 CTA shared memory。
- 主机制：`UTCATOMSWS.FIND_AND_SET.ALIGN` 执行 TMEM 分配位图的 uniform atomic
  find/set；`ATOMS.OR` 更新 CTA/cluster 侧共享状态；`STS` ×2写回成功地址或失败值。
- 额外指令：`WARPSYNC` ×3、`ELECT` ×2、`ENDCOLLECTIVE` ×1和八条 `PLOP3`
  建立 collective/选举协议；`S2R/LEA/LDS` 读取 CTA rank 与 guardrail 状态；
  `SHF/PRMT/LOP3/IADD3` 构造位图；`DEPBAR` 约束 atomic 依赖；失败时通过
  `NANOSLEEP` 重试，非法 phase 走内部 trap `CALL`。
- 判断：这不是“一条硬件 alloc opcode”。PTX alloc 被展开成位图原子分配器、同步、
  重试、结果写回和 guardrail 检查，是明确的复合 lowering。

### T09 `tcgen05.dealloc.cta_group::1.sync.aligned` — N=110，C

- PTX 含义：释放当前 CTA 先前分配的一段 TMEM 列范围。
- 主机制：`UTCATOMSWS.AND` 和 `ATOMS.AND` 清除 TMEM 分配位图。
- 额外指令：`SHF` ×16、`LOP3` ×10、`POPC` ×4、`PRMT` ×2、`SGXT` ×4以及
  `IADD3/ISETP/SEL` 构造并搜索待释放列的 mask；`WARPSYNC/ELECT/ENDCOLLECTIVE`、
  `BSSY/BSYNC` 维持 collective 和重汇合；两个内部 `CALL` 分别检查“释放未分配列”
  和“列并非由 alloc 返回”等 guardrail 错误。
- 判断：dealloc 是当前 75 条中最大的展开之一，110 条主要来自位图验证、层级
  popcount/search、原子清位和错误路径，不是 110 次 TMEM 释放。

### T10 `tcgen05.commit...mbarrier::arrive::one` — 完整 N=7；核心 1:1，P

- PTX 含义：提交此前异步发出的 tcgen05 操作，并以一次 arrive 通知指定的 cluster shared-memory mbarrier。
- 主指令：`UTCBAR` ×1，执行 tcgen05 commit/mbarrier arrive。
- 额外指令：`R2UR` ×1路由 barrier 地址；`PLOP3` ×3、`ELECT` ×1、`BRA` ×1
  构成选举发射。
- 判断：核心 barrier opcode 一条，另外六条是地址与 single-thread issue 协议。

### T12 `tcgen05.mma...kind::f16` — 完整 N=18；核心 1:1，P

- PTX 含义：执行以 FP16 为输入类型的稠密 Tensor Core 矩阵乘加，并把结果累加到 TMEM。
- 主指令：`UTCHMMA` ×1。
- 额外指令：`R2UR` ×11、`VOTEU` ×1、`PLOP3` ×3、`ELECT` ×1、`BRA` ×1。
- 判断：与 T01 的 TF32 lowering 同构，数据类型变化未改变发射协议。

### T13 `tcgen05.mma...kind::f16`（BF16 descriptor）— 完整 N=18；核心 1:1，P

- PTX 含义：执行由 BF16 descriptor 描述输入的 Tensor Core 矩阵乘加，并把结果累加到 TMEM。
- 主指令：`UTCHMMA` ×1；BF16 的精确输入类型由 idesc 编码。
- 额外指令：同 T12，为 11 条 `R2UR` 加六条 vote/选举/分支协议。
- 判断：底层核心仍是一条 `UTCHMMA`，BF16 不额外引入第二条计算指令。

### T14 `tcgen05.mma...kind::f8f6f4` — 完整 N=18；核心 1:1，P

- PTX 含义：执行 FP8/FP6/FP4 低精度输入的量化 Tensor Core 矩阵乘加，并把结果累加到 TMEM。
- 主指令：`UTCQMMA` ×1，执行低精度量化 MMA。
- 额外指令：`R2UR` ×11、`VOTEU` ×1、`PLOP3` ×3、`ELECT` ×1、`BRA` ×1。
- 判断：计算 opcode 从 `UTCHMMA` 变为 `UTCQMMA`，但另外 17 条仍是同类发射协议。

### T15 `tcgen05.mma...kind::i8` — 完整 N=18；核心 1:1，P

- PTX 含义：执行 INT8 整数 Tensor Core 矩阵乘加，并把结果累加到 TMEM。
- 主指令：`UTCIMMA` ×1，执行整数 MMA。
- 额外指令：`R2UR` ×11、`VOTEU` ×1、`PLOP3` ×3、`ELECT` ×1、`BRA` ×1。
- 判断：整数 MMA 核心一条，另外 17 条是 uniform 操作数和选举协议。

## 3. TMA 与异步拷贝（8 条）

### M01 2D TMA load — 完整 N=12；核心 1:1，P

- PTX 含义：通过 TMA 将 global memory 中的二维 tensor tile 异步加载到 CTA shared memory，并在完成时更新 mbarrier。
- 主指令：`UTMALDG` ×1。
- 额外指令：`R2UR` ×6路由 tensor descriptor、两个坐标、SMEM 目标和 mbarrier；
  `PLOP3` ×3、`ELECT` ×1、`BRA` ×1执行统一选举发射。
- 判断：核心 TMA load 一条，另外 11 条是参数路由和发射协议。

### M02 3D TMA load — 完整 N=13；核心 1:1，P

- PTX 含义：通过 TMA 将 global memory 中的三维 tensor tile 异步加载到 CTA shared memory，并在完成时更新 mbarrier。
- 主指令：`UTMALDG` ×1。
- 额外指令：比 M01 多一个坐标，因此 `R2UR` 从六条增至七条；选举协议仍为五条。
- 判断：第三维只增加一条 uniform 路由，没有增加第二条 TMA load。

### M03 2D multicast TMA load — 完整 N=13；核心 1:1，P

- PTX 含义：通过 TMA multicast 将二维 global tensor tile 异步发送到 cluster 内多个 CTA 的 shared memory。
- 主指令：`UTMALDG` ×1。
- 额外指令：`R2UR` ×7，其中新增项承载 multicast CTA mask；另有三条 `PLOP3`、
  一条 `ELECT` 和一条 `BRA`。
- 判断：multicast 仍由一条 TMA opcode 完成，多出来的是 mask 路由。

### M04 2D TMA store — 完整 N=6；核心 1:1，P

- PTX 含义：通过 TMA 将 CTA shared memory 中的二维 tile 异步存回 global memory，并归入 bulk group。
- 主指令：`UTMASTG` ×1。
- 额外指令：`R2UR` ×5路由 tensor descriptor、坐标和 SMEM 源地址。
- 判断：没有选举循环；完整 lowering 的 1:6 主要来自普通寄存器到 UR 的转换。

### M05 2D TMA reduce-add — 完整 N=11；核心 1:1，P

- PTX 含义：通过 TMA 对 shared-memory tile 和 global tensor 执行逐元素 reduce-add，并异步写回 global memory。
- 主指令：`UTMAREDG` ×1。
- 额外指令：`R2UR` ×5；`PLOP3` ×3、`ELECT` ×1、`BRA` ×1。
- 判断：reduce-add 在 TMA opcode 内完成，并未拆成独立 load/add/store；额外十条是
  参数和选举协议。

### M06 2D TMA prefetch — 完整 N=5；核心 1:1，P

- PTX 含义：根据 tensor descriptor 和二维坐标，把目标 global tensor tile 预取到 L2 cache。
- 主指令：`UTMAPF` ×1。
- 额外指令：`R2UR` ×4路由 descriptor 和两个坐标等操作数。
- 判断：核心 prefetch 一条，没有选举协议。

### M08 `cp.async.ca.shared.global` — 完整 N=3；核心 1:1，P

- PTX 含义：异步复制 4 字节 global memory 数据到 shared memory，采用 `.ca` 缓存策略。
- 主指令：`LDGSTS` ×1，把 global 数据直接送入 shared memory。
- 额外指令：`R2UR` ×2路由 64-bit global 地址/descriptor。
- 判断：数据搬运本身是一条；1:3 来自地址进入 uniform descriptor 通路。

### M09 `cp.async.cg.shared.global` — 完整 N=3；核心 1:1，P

- PTX 含义：异步复制 16 字节 global memory 数据到 shared memory，采用 `.cg` 缓存策略。
- 主指令：`LDGSTS` ×1。
- 额外指令：`R2UR` ×2。
- 判断：与 M08 同构，cache policy 体现在 `LDGSTS` 编码/修饰中，没有新增第二次拷贝。

## 4. Fence 与 barrier（8 条）

### F01 `fence.proxy.async.shared::cta` — N=2，C

- PTX 含义：在 CTA scope 建立 shared memory 的 generic proxy 与 async proxy 之间的访问顺序和可见性。
- 序列：`MEMBAR.ALL.CTA` + `FENCE.VIEW.ASYNC.S`。
- 说明：第一条建立 CTA scope 的内存顺序，第二条完成 generic/async proxy view
  之间的可见性转换。两条承担不同职责，属于真正的双步骤 fence lowering。

### F02 `fence.proxy.async.shared::cluster` — N=2，C

- PTX 含义：在 cluster scope 建立 shared memory 的 generic proxy 与 async proxy 之间的访问顺序和可见性。
- 序列：`MEMBAR.ALL.GPU` + `FENCE.VIEW.ASYNC.S`。
- 说明：与 F01 相同，但内存屏障提升为 GPU scope，以覆盖 cluster 所需可见性。

### F03 `fence.proxy.async` — N=2，C

- PTX 含义：在该指令默认作用域建立 generic proxy 与 async proxy 之间的访问顺序和可见性。
- 序列：`MEMBAR.ALL.GPU` + `FENCE.VIEW.ASYNC.S`。
- 说明：generic 形式在该目标上与 F02 降为相同的两步序列。

### F04 `fence.proxy.tensormap::generic.release.cta` — N=3，C

- PTX 含义：以 release 语义发布 generic 地址空间中的 tensor-map 更新，使其对 tensormap proxy 可见。
- 序列：`MEMBAR.ALL.GPU` + `ERRBAR` + `CGAERRBAR`。
- 说明：除 release 内存顺序外，还刷新/同步错误与 cluster 错误状态；三条都不是
  参数准备，因此当前证据支持 1:3。

### F06 `barrier.cluster.arrive` — N=14，C

- PTX 含义：通知当前 CTA 已到达 cluster barrier；arrive 本身不等待其他 CTA。
- 主指令：`UCGABAR_ARV` ×1。
- 额外指令：读取 cluster 配置的 `LDC/ISETP/BRA` 选择单 CTA/多 CTA 路径；
  `WARPSYNC` ×2和 `ENDCOLLECTIVE` ×2包围 collective；`MEMBAR + ERRBAR + CGAERRBAR`
  建立到达前的内存/错误顺序；其余 `MOV/BRA` 负责 mask 和路径汇合。
- 判断：核心 arrive 一条，但 barrier 的 scope 分派和前置一致性协议构成真实复合序列。

### F07 `barrier.cluster.wait` — N=18，C

- PTX 含义：等待 cluster 中参与的 CTA 全部到达 cluster barrier 后再继续执行。
- 主指令：`UCGABAR_WAIT` ×1；备用路径使用 `BAR.SYNC.DEFER_BLOCKING` ×1。
- 额外指令：`LDC/ISETP/BRA` 选择 cluster 形态；两组 `WARPSYNC/ENDCOLLECTIVE`
  执行 collective；`CCTL.IVALL` 使相关缓存状态失效；`SHF/LOP3` 构造备用 barrier
  参数。
- 判断：wait 包含硬件 wait、缓存可见性和不同 cluster 配置的回退路径，不能缩成
  一条无条件 SASS。

### F09 `bar.arrive 0, 32` — 完整 N=2；核心 1:1，P

- PTX 含义：向编号 0 的 CTA barrier 报告到达，该 barrier 的预期参与线程数为 32；本指令不等待完成。
- 序列：`WARPSYNC.ALL` + `BAR.ARV 0x0, 0x20`。
- 说明：`BAR.ARV` 是核心到达操作，`WARPSYNC` 保证参与 warp 对齐；核心 1:1，完整
  同步协议 1:2。

### F10 `bar.sync 0, 32` — 完整 N=2；核心 1:1，P

- PTX 含义：在编号 0 的 CTA barrier 上等待，直到其 32 个预期参与线程全部到达。
- 序列：`WARPSYNC.ALL` + `BAR.SYNC.DEFER_BLOCKING 0x0, 0x20`。
- 说明：第二条是核心 blocking barrier，第一条是参与线程同步准备。

## 5. 整数与 64-bit 操作（13 条）

### I02 `add.s64` — N=2，A

- PTX 含义：对两个有符号 64-bit 整数执行加法，产生 64-bit 结果。
- 序列：低半 `IADD3` 产生 carry predicate；高半 `IADD3.X` 加入 carry。
- 说明：64-bit 值以两个 32-bit 寄存器保存，两条共同构成精确 64-bit 加法。这是
  最明确的宽度拆分 1:2。

### I03 `sub.s64` — N=2，A

- PTX 含义：对两个有符号 64-bit 整数执行减法，产生 64-bit 结果。
- 序列：低半 `IADD3` 对低位减数取负并产生 borrow/carry；高半 `IADD3.X` 使用
  `~high` 和低位进位完成高 32 位减法。
- 说明：与 I02 同样是不可删除的 64-bit 两半展开。

### I07 `mul.lo.s64` — N=18，A

- PTX 含义：计算两个有符号 64-bit 整数乘积的低 64 位。
- 算术核心：`IMAD.WIDE` ×4计算 32×32 partial products，`IADD3/IADD3.X` ×2合并
  交叉项和进位。
- 额外路由：当前审计还保留 12 条 `MOV`，用于在寄存器对之间排列 partial products。
- 说明：低 64 位乘积确实需要多条乘加；但 N=18 中有大量寄存器路由，若只统计
  算术核心，更接近 1:6 而不是 1:18。

### I09 `mad.wide.u32` — N=5，A

- PTX 含义：把两个 32-bit 无符号整数相乘得到 64-bit 乘积，再加上一个 64-bit 累加数。
- 序列：`IMAD.U32` 计算乘积低半，`IMAD.HI.U32` 计算高半；一条 `MOV` 排列结果；
  `IADD3 + IADD3.X` 把原 64-bit 累加数加到乘积并传播进位。
- 说明：32×32→64 再加 64-bit accumulator，没有单条 SASS 覆盖完整语义。

### I10 `div.s32` — N=32，A

- PTX 含义：计算两个有符号 32-bit 整数的商。
- 倒数估计：`IABS` 取绝对值，`I2F → MUFU.RCP → F2I` 生成整数倒数近似。
- 商与误差：四条 `IMAD/IMAD.HI` 配合八条 `IADD3` 求商估计和余数。
- 精确修正：四条 `ISETP` 与四条 `SEL` 修复倒数近似造成的 off-by-one。
- 有符号/边界处理：`LOP3/PLOP3/BRA`、取负 `IADD3` 和有效 `MOV` 恢复商符号并
  处理特殊输入。
- 说明：不存在一条整数 `IDIV`；这是“浮点倒数估计 + 整数乘法 + 精确修正”的
  典型软件除法。

### I11 `div.u32` — N=24，A

- PTX 含义：计算两个无符号 32-bit 整数的商。
- 与 I10 共享 `I2F → MUFU.RCP → F2I`、四条 `IMAD` 和两轮比较/选择修正。
- 因为无符号输入不需要 `IABS`、符号 XOR、条件取负和符号分支，所以比 I10 少八条。
- 最后 `ISETP/LOP3/PLOP3/SEL` 处理除数有效性和最终选择。

### I12 `rem.s32` — N=29，A

- PTX 含义：计算两个有符号 32-bit 整数相除后的余数。
- 前半仍以倒数估计和四条 `IMAD` 得到近似商积。
- 中段用 `IADD3/ISETP/SEL` 两次修正余数，使其落入合法范围。
- 后段根据被除数符号条件取负，并处理特殊输入。
- 说明：与 `div.s32` 共用算法，但最终保留修正后的 remainder 而非 quotient。

### I13 `rem.u32` — N=23，A

- PTX 含义：计算两个无符号 32-bit 整数相除后的余数。
- 使用 `I2F/MUFU.RCP/F2I` 建立倒数，四条 `IMAD` 计算商积。
- 六条 `IADD3`、三条 `ISETP`、三条 `SEL` 完成两轮余数修正。
- 无有符号绝对值和符号恢复，因此比 I12 少六条。

### I15 `shl.b64` — N=2，A

- PTX 含义：把一个 64-bit 位串左移指定的位数。
- `SHF.L.U64.HI` 生成高 32 位，同时吸收低半移出的 bit；`SHF.L.U32` 生成低半。
- 说明：两条分别产生 64-bit 结果的高低两半，是确定的宽度拆分。

### I16 `shr.s64` — N=2，A

- PTX 含义：对一个有符号 64-bit 整数执行算术右移，左侧补符号位。
- `SHF.R.S64` 生成低半并从高半补位；`SHF.R.S32.HI` 对高半执行算术右移和符号扩展。
- 说明：两条共同维持 64-bit 有符号右移语义。

### I18A `and.b64` — N=2，A

- PTX 含义：对两个 64-bit 位串逐位执行 AND。
- 两条 `LOP3.LUT` 分别对低 32 位和高 32 位执行 AND。
- 说明：逻辑函数相同，但每条 SASS 只处理一个 32-bit half。

### I18B `or.b64` — N=2，A

- PTX 含义：对两个 64-bit 位串逐位执行 OR。
- 两条 `LOP3.LUT` 分别对低半和高半执行 OR。
- 说明：与 I18A 同样是寄存器宽度导致的确定 1:2。

### I21B `mov.b64` — N=2，R

- PTX 含义：把一个 64-bit 位串从源 PTX 寄存器复制到目标 PTX 寄存器。
- 当前序列只有 `MOV R2, R2` 和 `MOV R3, R3`，两条都是物理寄存器自拷贝。
- 说明：从机器状态看它们不改变任何 bit；这只能说明 PTX 64-bit move 经寄存器分配后
  退化为两个同址 half，并不能证明存在两条语义操作。
- 结论：当前 `1:N` verdict 可疑，应重新分类为零成本别名/格式映射候选，不能据此要求
  L0 生成两条 `MOV`。

## 6. 浮点转换与特殊函数（7 条）

### C05 `cvt.s64.s32` — N=3，A

- PTX 含义：把一个有符号 32-bit 整数符号扩展为有符号 64-bit 整数。
- `SHF.R.S32.HI` 从输入符号位生成全 0 或全 1 的高 32 位。
- 两条 `MOV` 把原 32-bit 值和符号扩展高半放入 64-bit 输出寄存器对。
- 说明：核心语义是 sign extension；若把物理寄存器路由单独排除，真正变换只有一条
  `SHF`，当前 N=3 包含两条结果布置。

### FP09 `ex2.approx.f32` — N=8，C

- PTX 含义：计算单精度输入的近似 `2^x`。
- 主指令：`MUFU.EX2` ×1。
- 额外指令：`FSETP/FSEL` 检测极小输入；两条 `FMUL` 对该范围缩放输入并补偿输出；
  两条 `MOV` 装入阈值/缩放常量。
- 说明：普通范围核心是一个 MUFU，但为保持 PTX 对非正规/极值输入的行为增加七条
  范围处理指令。

### FP10 `lg2.approx.f32` — N=10，C

- PTX 含义：计算单精度输入的近似 `log2(x)`。
- 主指令：`MUFU.LG2` ×1。
- 额外指令：`FADD` 取绝对值/补偿，`FSETP/FSEL` 检查 subnormal，两条常量 `MOV`
  和 `FMUL` 把极小输入缩放到 MUFU 可处理范围，之后减去指数补偿并选择结果。
- 说明：九条额外指令主要是 subnormal range reduction，不是九次对数计算。

### FP11 `rcp.approx.f32` — N=9，C

- PTX 含义：计算单精度输入的近似倒数 `1/x`。
- 主指令：`MUFU.RCP` ×1。
- 额外指令：两条 `FSETP` 检测过小/过大幅值；两条 `FSEL` 选择缩放因子；两条
  `FMUL` 在 MUFU 前后缩放；`FADD/MOV` 准备绝对值和常量。
- 说明：额外八条用于避免 reciprocal 在极端指数范围溢出/下溢。

### FP12 `rsqrt.approx.f32` — N=10，C

- PTX 含义：计算单精度输入的近似倒平方根 `1/sqrt(x)`。
- 主指令：`MUFU.RSQ` ×1。
- 额外指令：`FSETP/FSEL` 检测 subnormal；两条 `FMUL` 进行输入缩放和输出补偿；
  `FADD` 与三条 `MOV` 准备幅值、阈值和补偿常量。
- 说明：普通输入是一条 RSQ，额外九条维护小数值范围行为。

### FP13 `rcp.rn.f64` — N=27，A

- PTX 含义：按 round-to-nearest 模式计算双精度倒数 `1/x`。
- 初值：`MUFU.RCP64H` ×1只产生双精度倒数的高精度初始近似。
- 精化：`DFMA` ×5和 `DADD` ×1执行 Newton/残差修正；`FADD/FSETP/BRA` 判断快速
  路径是否适用。
- 特殊路径：大量 `MOV`、两条 `LOP3`、两条 `IADD3` 调整指数/尾数；极端输入调用
  内部 `__cuda_sm20_dblrcp_rn_slowpath_v3`。
- 说明：精确 round-to-nearest 双精度倒数必须由近似硬件加多轮软件精化完成。

### FP14 `sqrt.rn.f64` — N=49，A

- PTX 含义：按 round-to-nearest 模式计算双精度平方根 `sqrt(x)`。
- 初值：`MUFU.RSQ64H` ×1生成倒平方根近似。
- 精化：`DMUL` ×3、`DFMA` ×5、`DADD` ×2计算残差并细化，再乘回输入得到平方根。
- 路径选择：`ISETP/BRA` 检查指数范围；32 条 `MOV` 大量用于双寄存器对和内部调用
  ABI 的值路由；异常/中间范围调用 `__cuda_sm20_dsqrt_rn_f64_mediumpath_v1`。
- 说明：这是确定的软件算法展开；但 49 中相当部分是调用 ABI/寄存器路由，算术核心
  约为 11 条特殊函数和双精度运算。

## 7. Warp collective（13 条）

### W01 `shfl.sync.bfly.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：在给定 member mask 内执行 warp butterfly shuffle，从 lane-id 与偏移量异或得到的源 lane 取值。
- 序列：`WARPSYNC` + `SHFL.BFLY` + `ENDCOLLECTIVE`。
- 说明：`SHFL` 是核心交换，前后两条建立并关闭 PTX `.sync` collective 区域。

### W02 `shfl.sync.up.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：在给定 member mask 内执行 warp up shuffle，从当前 lane 之前指定偏移的 lane 取值。
- 序列：`WARPSYNC` + `SHFL.UP` + `ENDCOLLECTIVE`。
- 说明：只有核心 SHFL 模式改变，同步包络与 W01 相同。

### W03 `shfl.sync.down.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：在给定 member mask 内执行 warp down shuffle，从当前 lane 之后指定偏移的 lane 取值。
- 序列：`WARPSYNC` + `SHFL.DOWN` + `ENDCOLLECTIVE`。
- 说明：核心一条，另外两条是 collective 生命周期。

### W04 `shfl.sync.idx.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：在给定 member mask 内执行 warp indexed shuffle，从显式指定的源 lane 取值。
- 序列：`WARPSYNC` + `SHFL.IDX` + `ENDCOLLECTIVE`。
- 说明：索引模式仍由单条 SHFL 完成。

### W05 `redux.sync.add.s32` — 完整 N=4；核心 1:1，P

- PTX 含义：对 member mask 内各 lane 的有符号 32-bit 值执行加法归约，并把结果返回给参与线程。
- 主指令：`REDUX` ×1。
- 额外指令：`WARPSYNC` 和 `ENDCOLLECTIVE` 包围 collective；一条 `MOV` 路由归约结果。
- 判断：整数加法归约核心一条，完整 PTX 同步语义四条。

### W06 `redux.sync.max.s32` — 完整 N=4；核心 1:1，P

- PTX 含义：对 member mask 内各 lane 的有符号 32-bit 值执行最大值归约。
- 主指令：`CREDUX` ×1；另有 `WARPSYNC + MOV + ENDCOLLECTIVE`。
- 说明：max 类型选择了 CREDUX 编码，但协议与 W05 相同。

### W08 `redux.sync.max.f32` — 完整 N=4；核心 1:1，P

- PTX 含义：对 member mask 内各 lane 的单精度值执行最大值归约。
- 主指令：浮点 `CREDUX` ×1；额外为 `WARPSYNC/MOV/ENDCOLLECTIVE`。
- 说明：没有软件比较树，浮点 max 归约由单条 collective opcode 完成。

### W09 `redux.sync.xor.b32` — 完整 N=4；核心 1:1，P

- PTX 含义：对 member mask 内各 lane 的 32-bit 值执行按位 XOR 归约。
- 主指令：`REDUX` ×1；额外为 `WARPSYNC/MOV/ENDCOLLECTIVE`。
- 说明：XOR 运算在 REDUX 内完成，并未展开为多轮 shuffle/XOR。

### W10 `vote.sync.all.pred` — 完整 N=3；核心 1:1，P

- PTX 含义：判断 member mask 内所有参与 lane 的输入谓词是否都为真。
- 序列：`WARPSYNC + VOTE.ALL + ENDCOLLECTIVE`。
- 说明：核心 vote 一条，前后两条实现显式 sync collective。

### W11 `vote.sync.any.pred` — 完整 N=3；核心 1:1，P

- PTX 含义：判断 member mask 内是否至少有一个参与 lane 的输入谓词为真。
- 序列：`WARPSYNC + VOTE.ANY + ENDCOLLECTIVE`。
- 说明：与 W10 同构。

### W12 `vote.sync.ballot.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：把 member mask 内输入谓词为真的 lane 编码成一个 32-bit ballot mask。
- 序列：`WARPSYNC + VOTE.BALLOT + ENDCOLLECTIVE`。
- 说明：ballot mask 由一条 VOTE 产生，另外两条是 collective 包络。

### W13 `match.sync.any.b32` — 完整 N=3；核心 1:1，P

- PTX 含义：对每个参与 lane 返回一个 mask，标出 member mask 内所有输入值与本 lane 相等的 lane。
- 序列：`WARPSYNC + MATCH.ANY + ENDCOLLECTIVE`。
- 说明：匹配本身一条，完整同步协议三条。

### W14 `elect.sync` — 完整 N=4；核心 1:1，P

- PTX 含义：在 member mask 内选出一个 leader lane，并返回选举结果谓词及所选 lane 信息。
- 主指令：`ELECT` ×1。
- 额外指令：`WARPSYNC` 和 `ENDCOLLECTIVE` 包围选举；一条 `MOV` 把选中 lane/rank
  结果送至 PTX 输出。
- 判断：选举核心一条，结果路由和同步使完整 lowering 为四条。

## 8. 位操作（7 条）

### BT04 `bfe.u32` — N=8，C

- PTX 含义：从 32-bit 输入的指定起始位置提取指定宽度的无符号 bit-field，并零扩展结果。
- `MOV/SHF/LOP3/PRMT` 共六条把 PTX 的 position/width 编码成底层 shift/extract 控制。
- `SHF.R.U32.HI` 执行右移，`SGXT.U32` 按 width 截断/零扩展。
- 说明：没有直接 BFE opcode；提取由控制构造、shift 和 width extension 合成。

### BT05 `bfe.s32` — N=8，C

- PTX 含义：从 32-bit 输入的指定起始位置提取指定宽度的有符号 bit-field，并符号扩展结果。
- 控制构造与 BT04 相同。
- 最后使用有符号 `SHF.R.S32.HI` 和 `SGXT`，把被提取字段做符号扩展。
- 说明：与无符号版本的差异集中在最后两条。

### BT06 `bfi.b32` — N=9，C

- PTX 含义：把一个指定宽度的 bit-field 插入目标 32-bit 值的指定位置，其余位保持原值。
- 六条 `MOV/SHF/LOP3/PRMT` 构造 position/width；`BMSK` 生成字段 mask；
  `SHF.L` 对插入值定位；最后 `LOP3` 合并原值、移位值和 mask。
- 说明：bit-field insert 被明确合成为 mask + shift + ternary logic。

### BT07 `popc.b32` — O0 N=3；核心 1:1，V

- PTX 含义：统计一个 32-bit 值中置位 bit 的数量。
- 主指令：`POPC` ×1。
- O0 附加指令：第一条 `LOP3` 构造全 1 mask，第二条把输入与该 mask 组合；两条合起来
  只是把原输入送入 `POPC`，不是软件 popcount 的组成步骤。
- B200 A/B：在 CUDA 12.8.93 上把常量输入改为 kernel 参数后，O0 仍为
  `LOP3.LUT → LOP3.LUT → POPC`，O3 则只生成 `POPC R5, UR6`。同构 `mov.b32`
  baseline 在 O0 的目标位置只有一条恒等 `MOV`，说明两条 `LOP3` 是 O0 输入规范化
  模板，而不是 `popc.b32` 的必要语义。
- 结论：严格核心映射为 `popc.b32 → POPC`，即 **1:1**；旧 1:3 只描述 O0 lowering。

### BT08 `clz.b32` — N=2，A

- PTX 含义：统计一个 32-bit 值最高有效位之前的前导零数量。
- `FLO.U32` 返回最高置位 bit 的位置；`IADD3` 计算 `31 - position`，得到 leading-zero
  count。
- 说明：两条分别完成 find-leading-one 和索引变换，是明确的 1:2 合成。

### BT09 `brev.b32` — O0 N=3；核心 1:1，V

- PTX 含义：反转一个 32-bit 值中的 bit 顺序。
- 主指令：`BREV` ×1。
- O0 附加指令：`SHF.R.U32.HI + SGXT.U32` 对 `BREV` 结果执行 32-bit lane/宽度
  规范化；它们不执行第二段 bit reverse。
- B200 A/B：动态参数输入下，O0 仍为 `BREV → SHF.R.U32.HI → SGXT.U32`，O3 只生成
  `BREV R5, R5`，并直接把结果送给 `STG`。相同结论在独立 PTX 文件和三内核同模块
  两种布局中都复现。
- 结论：严格核心映射为 `brev.b32 → BREV`，即 **1:1**；`SHF/SGXT` 是 O0 结果
  规范化，不是 `brev.b32` 的必要语义展开。

### BT10 `fns.b32` — N=70，A

- PTX 含义：从给定起始 bit 位置和方向查找第 n 个置位 bit，并返回其位置。
- 边界分支：`ISETP/PLOP3/BRA` 处理 n=0、方向和找不到结果等情况。
- 主算法：先用 `BREV` 统一搜索方向，再构造起始 bit mask。
- 层级选择：四条 `POPC` 分别统计 32/16/8/4-bit 分块；大量 `SHF/PRMT/SGXT` 提取
  子块，`ISETP/SEL/IADD3` 根据剩余 ordinal 逐层选择 16、8、4、2、1-bit 范围。
- 最后把局部位置转换为 bit index，并在未找到时选择 `0xffffffff`。
- 说明：这是一个完整的“第 n 个置位 bit”软件搜索树，不存在单条 FNS SASS。

## 9. Cluster 地址转换（1 条）

### CL03 `cvta.shared::cta.u64` — N=7，C

- PTX 含义：把 CTA shared-memory 地址转换成可用于 generic addressing 的 64-bit 地址。
- 主变换：`S2R R0, SR_SWINHI` 读取当前 CTA shared-memory window 的高地址信息。
- 额外指令：六条 `MOV` 把 32-bit shared offset 与 `SR_SWINHI` 组合到 64-bit generic
  地址寄存器对。
- 说明：地址空间转换确实需要 special-register 信息；但 N=7 中多数是物理寄存器
  路由，核心转换接近 `S2R + 64-bit pair assembly`。

## 10. Megakernel 控制（1 条）

### MK01 `bar.warp.sync 0xffffffff` — 完整 N=2；协议型，P

- PTX 含义：让给定 member mask 中的 warp lane 在该位置同步后再继续执行。
- 序列：`WARPSYNC` + `ENDCOLLECTIVE`。
- 说明：该 PTX 本身就是同步协议，没有额外计算 opcode；前者进入/执行 warp sync，
  后者结束 collective 区域。若手写 SASS 需要保持相同 collective 状态，两条都应保留。

## 11. Packed 激活函数（3 条）

### ACT02 `tanh.approx.f16x2` — N=3，A

- PTX 含义：分别对 packed `f16x2` 中的两个 FP16 元素计算近似双曲正切。
- 两条 `MUFU.TANH` 分别处理 packed 寄存器中的低、高清半精度元素。
- `PRMT` 把两个标量结果重新打包为一个 `f16x2`。
- 说明：这是清晰的“两个 lane 各算一次 + repack” 1:3。

### ACT04 `tanh.approx.bf16x2` — N=3，A

- PTX 含义：分别对 packed `bf16x2` 中的两个 BF16 元素计算近似双曲正切。
- 两条 `MUFU.TANH` 分别处理两个 BF16 lane，`PRMT` 重组 packed BF16x2。
- 说明：与 ACT02 同构，仅输入/输出格式不同。

### ACT06 `ex2.approx.f16x2` — N=3，A

- PTX 含义：分别对 packed `f16x2` 中的两个 FP16 元素计算近似 `2^x`。
- 两条 `MUFU.EX2` 分别计算低、高清 lane；`PRMT` 将两个结果重新打包。
- 说明：packed PTX 并未对应 packed MUFU，因此确定展开为两个标量特殊函数加一次打包。

## 12. 汇总结论

按新口径，当前 75 条只是旧 CSV 的候选集合，不能被等价地理解为“75 条严格 1:N”：

| 类别 | 条数 | 新口径下的处理 |
|------|-----:|----------------|
| P：核心 opcode + 编译器协议/路由 | 36 | 核心 opcode 通常记为 1:1；协议和操作数布置分列保存 |
| A：宽度拆分/软件算法 | 20 | 保留为严格 1:N 候选 |
| C：多个硬件机制共同完成 | 16 | 保留为严格 1:N 候选，但仍需逐条确认语义边界 |
| R：证据可疑 | 1 | I21B 不进入 1:N 规则，仍需 A/B baseline |
| V：A/B 已验证核心 1:1 | 2 | BT07、BT09 从旧 R 类移除；O0 附加 lowering 不计入核心映射 |

这个分类表不等于新的最终 verdict：A/C 合计 36 条是严格 1:N **候选**，不是已经证明的
最终数量；P 类也要保留完整 lowering 证据，只是不再污染核心 opcode 映射。

1. **确定必须展开的算术/算法类**包括 64-bit add/sub/shift/logic、宽乘加、整数
   div/rem、精确 FP64 reciprocal/sqrt、`clz`、`fns` 和 packed 激活函数。这些即使忽略
   发射协议，也需要多条 SASS。
2. **核心 opcode 为一条、但完整协议为多条**的主要是 tcgen05、TMA、warp collective
   和普通 barrier。核心映射不统计 `R2UR/WARPSYNC/ELECT/PLOP/BRA`；如后续模块需要
   生成可执行机器码，应从独立的 operand/protocol 字段读取，不能把它们伪装成核心
   PTX→SASS 1:N。
3. **当前仍需重审**的是 I21B `mov.b64`。BT07 `popc.b32` 和 BT09 `brev.b32` 已在
   B200 上通过动态输入、O0/O3 和独立模块 A/B 复核，严格核心均为 1:1；完整证据见
   [`experiments/BT07_BT09/README.md`](experiments/BT07_BT09/README.md)。
4. **`tcgen05.mma` 的结论已经明确**：T01/T02/T03/T12–T15 的计算核心分别是一条
   `UTCHMMA/UTCQMMA/UTCIMMA`，因此核心映射是 1:1。`ELECT` 属于编译器发射协议；
   它与每次动态 MMA 的 single-thread issue 要求相关，不是“仅第一个 MMA 执行一次后
   永久选出 leader”。是否被提取/合并由编译器和控制流决定。

因此，这份清单现在是“旧 75 条候选的拆解索引”，而不是 L0 的 75 条展开规则。下一步
应让分析器分别输出 `core_opcode_sequence`、`operand_materialization_sequence` 和
`compiler_protocol_sequence`，再重新生成严格核心口径的 verdict。

## 13. 旧 1:N 候选的 O0/O3 指令数总表

下表直接取自 `results/mapping_report.csv`。各计数的含义：

- **原始**：目标 PTX 源行下的全部 SASS（已经排除函数外区域，但仍含 NOP、恒等搬移和协议）；
- **清洗**：通用规则去除 NOP、恒等自拷贝、重复同步等之后的条数；
- **O0 逐族**：再按指令族排除已经识别的参数、地址和谓词准备，仍可能包含发射协议；
- O3 尚未做与 O0 等价的逐族人工审计，因此不能把“O3 清洗”直接叫作严格核心 opcode 数；
- **O3 参考\***：该用例存在源位置交错，O3 数字只用于观察优化结果，不能单独用于归因。
- O3 为 `0` 表示目标操作在当前最小用例中被优化消除或无法由该源行单独归因，不表示
  该 PTX 在架构上没有对应的 SASS；核心映射仍以 O0 和逐条 A/B 审计为主。

| ID | 目标 PTX | O0 原始 | O0 清洗 | O0 逐族 | O3 原始 | O3 清洗 | 严格核心结论 |
|----|----------|--------:|--------:|--------:|--------:|--------:|----------------|
| T01 | `tcgen05.mma.cta_group::1.kind::tf32 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;` | 43 | 30 | 18 | 11 | 11 | 1:1（P） |
| T02 | `tcgen05.mma.cta_group::2.kind::tf32 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3, %mask4, %mask5, %mask6, %mask7}, %enable;` | 56 | 30 | 22 | 11 | 11 | 1:1（P） |
| T03 | `tcgen05.mma.sp.cta_group::1.kind::tf32 [%taddr], %desc_a, %desc_b, [%meta], %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;` | 45 | 31 | 18 | 12 | 12 | 1:1（P） |
| T04 | `tcgen05.cp.cta_group::1.128x256b [%taddr], %desc;` | 17 | 9 | 9 | 9 | 8 | 1:1（P） |
| T05 | `tcgen05.ld.sync.aligned.16x64b.x1.b32 {%dst0}, [%taddr];` | 9 | 3 | 3 | 3* | 3* | 1:1（P） |
| T06 | `tcgen05.ld.sync.aligned.16x128b.x4.b32 {%dst0, %dst1, %dst2, %dst3, %dst4, %dst5, %dst6, %dst7}, [%taddr];` | 16 | 3 | 3 | 3* | 3* | 1:1（P） |
| T07 | `tcgen05.st.sync.aligned.16x64b.x1.b32 [%taddr], {%src0};` | 8 | 3 | 3 | 2 | 2 | 1:1（P） |
| T08 | `tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [smem_result], %ncols;` | 93 | 66 | 56 | 50 | 48 | 1:N 候选（C） |
| T09 | `tcgen05.dealloc.cta_group::1.sync.aligned.b32 %taddr, %ncols;` | 134 | 114 | 110 | 46* | 44* | 1:N 候选（C） |
| T10 | `tcgen05.commit.cta_group::1.mbarrier::arrive::one.shared::cluster.b64 [smem_mbar];` | 24 | 16 | 7 | 9 | 9 | 1:1（P） |
| T12 | `tcgen05.mma.cta_group::1.kind::f16 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;` | 43 | 30 | 18 | 11 | 11 | 1:1（P） |
| T13 | `tcgen05.mma.cta_group::1.kind::f16 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;` | 43 | 30 | 18 | 11 | 11 | 1:1（P） |
| T14 | `tcgen05.mma.cta_group::1.kind::f8f6f4 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;` | 43 | 30 | 18 | 11 | 11 | 1:1（P） |
| T15 | `tcgen05.mma.cta_group::1.kind::i8 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;` | 43 | 30 | 18 | 11 | 11 | 1:1（P） |
| M01 | `cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes [smem_buf], [%desc, {%c0, %c1}], [smem_mbar];` | 26 | 21 | 12 | 14 | 14 | 1:1（P） |
| M02 | `cp.async.bulk.tensor.3d.shared::cta.global.mbarrier::complete_tx::bytes [smem_buf], [%desc, {%c0, %c1, %c2}], [smem_mbar];` | 27 | 22 | 13 | 15 | 15 | 1:1（P） |
| M03 | `cp.async.bulk.tensor.2d.shared::cluster.global.mbarrier::complete_tx::bytes.multicast::cluster [smem_buf], [%desc, {%c0, %c1}], [smem_mbar], %mask;` | 28 | 24 | 13 | 16 | 16 | 1:1（P） |
| M04 | `cp.async.bulk.tensor.2d.global.shared::cta.bulk_group [%desc, {%c0, %c1}], [smem_buf];` | 15 | 11 | 6 | 7 | 7 | 1:1（P） |
| M05 | `cp.reduce.async.bulk.tensor.2d.global.shared::cta.add.bulk_group [%desc, {%c0, %c1}], [smem_buf];` | 20 | 16 | 11 | 12 | 12 | 1:1（P） |
| M06 | `cp.async.bulk.prefetch.tensor.2d.L2.global [%desc, {%c0, %c1}];` | 9 | 5 | 5 | 4 | 4 | 1:1（P） |
| M08 | `cp.async.ca.shared.global [smem_data], [%gaddr], 4;` | 15 | 11 | 3 | 9 | 9 | 1:1（P） |
| M09 | `cp.async.cg.shared.global [smem_data16], [%gaddr], 16;` | 15 | 11 | 3 | 9 | 9 | 1:1（P） |
| F01 | `fence.proxy.async.shared::cta;` | 2 | 2 | 2 | 2 | 2 | 1:N 候选（C） |
| F02 | `fence.proxy.async.shared::cluster;` | 2 | 2 | 2 | 2 | 2 | 1:N 候选（C） |
| F03 | `fence.proxy.async;` | 2 | 2 | 2 | 2 | 2 | 1:N 候选（C） |
| F04 | `fence.proxy.tensormap::generic.release.cta;` | 3 | 3 | 3 | 3 | 3 | 1:N 候选（C） |
| F06 | `barrier.cluster.arrive;` | 15 | 14 | 14 | 9 | 8 | 1:N 候选（C） |
| F07 | `barrier.cluster.wait;` | 18 | 18 | 18 | 7 | 7 | 1:N 候选（C） |
| F09 | `bar.arrive 0, 32;` | 3 | 2 | 2 | 1 | 1 | 1:1（P） |
| F10 | `bar.sync 0, 32;` | 3 | 2 | 2 | 1 | 1 | 1:1（P） |
| I02 | `add.s64 %rd2, %rd0, %rd1;` | 2 | 2 | 2 | 0 | 0 | 1:N（A） |
| I03 | `sub.s64 %rd2, %rd0, %rd1;` | 2 | 2 | 2 | 0 | 0 | 1:N（A） |
| I07 | `mul.lo.s64 %rd2, %rd0, %rd1;` | 26 | 18 | 18 | 0 | 0 | 1:N（A） |
| I09 | `mad.wide.u32 %rd0, %r0, %r1, %rd0;` | 6 | 5 | 5 | 0 | 0 | 1:N（A） |
| I10 | `div.s32 %r2, %r0, %r1;` | 55 | 32 | 32 | 16* | 16* | 1:N（A） |
| I11 | `div.u32 %r2, %r0, %r1;` | 39 | 24 | 24 | 16* | 16* | 1:N（A） |
| I12 | `rem.s32 %r2, %r0, %r1;` | 52 | 29 | 29 | 15* | 15* | 1:N（A） |
| I13 | `rem.u32 %r2, %r0, %r1;` | 37 | 23 | 23 | 15* | 15* | 1:N（A） |
| I15 | `shl.b64 %rd1, %rd0, 4;` | 2 | 2 | 2 | 0 | 0 | 1:N（A） |
| I16 | `shr.s64 %rd1, %rd0, 4;` | 2 | 2 | 2 | 0 | 0 | 1:N（A） |
| I18A | `and.b64 %rd2, %rd0, %rd1;` | 2 | 2 | 2 | 0 | 0 | 1:N（A） |
| I18B | `or.b64 %rd2, %rd0, %rd1;` | 2 | 2 | 2 | 0 | 0 | 1:N（A） |
| I21B | `mov.b64 %rd1, %rd0;` | 4 | 2 | 2 | 0 | 0 | 待审（R） |
| C05 | `cvt.s64.s32 %rd0, %r0;` | 4 | 3 | 3 | 0 | 0 | 1:N（A） |
| FP09 | `ex2.approx.f32 %f1, %f0;` | 15 | 8 | 8 | 0 | 0 | 1:N 候选（C） |
| FP10 | `lg2.approx.f32 %f1, %f0;` | 18 | 10 | 10 | 0 | 0 | 1:N 候选（C） |
| FP11 | `rcp.approx.f32 %f1, %f0;` | 15 | 9 | 9 | 0 | 0 | 1:N 候选（C） |
| FP12 | `rsqrt.approx.f32 %f1, %f0;` | 18 | 10 | 10 | 0 | 0 | 1:N 候选（C） |
| FP13 | `rcp.rn.f64 %fd1, %fd0;` | 55 | 27 | 27 | 9* | 9* | 1:N（A） |
| FP14 | `sqrt.rn.f64 %fd1, %fd0;` | 89 | 49 | 49 | 14* | 14* | 1:N（A） |
| W01 | `shfl.sync.bfly.b32 %r1, %r0, 1, 0x1f, 0xFFFFFFFF;` | 9 | 7 | 3 | 1* | 1* | 1:1（P） |
| W02 | `shfl.sync.up.b32 %r1, %r0, 1, 0, 0xFFFFFFFF;` | 9 | 7 | 3 | 1* | 1* | 1:1（P） |
| W03 | `shfl.sync.down.b32 %r1, %r0, 1, 0x1f, 0xFFFFFFFF;` | 9 | 7 | 3 | 1* | 1* | 1:1（P） |
| W04 | `shfl.sync.idx.b32 %r1, %r0, 0, 0x1f, 0xFFFFFFFF;` | 9 | 7 | 3 | 1* | 1* | 1:1（P） |
| W05 | `redux.sync.add.s32 %r1, %r0, 0xFFFFFFFF;` | 8 | 6 | 4 | 3* | 3* | 1:1（P） |
| W06 | `redux.sync.max.s32 %r1, %r0, 0xFFFFFFFF;` | 8 | 6 | 4 | 2* | 2* | 1:1（P） |
| W08 | `redux.sync.max.f32 %f1, %f0, 0xFFFFFFFF;` | 8 | 6 | 4 | 4* | 4* | 1:1（P） |
| W09 | `redux.sync.xor.b32 %r1, %r0, 0xFFFFFFFF;` | 8 | 6 | 4 | 2* | 2* | 1:1（P） |
| W10 | `vote.sync.all.pred %p1, %p0, 0xFFFFFFFF;` | 7 | 7 | 3 | 1 | 1 | 1:1（P） |
| W11 | `vote.sync.any.pred %p1, %p0, 0xFFFFFFFF;` | 7 | 7 | 3 | 1 | 1 | 1:1（P） |
| W12 | `vote.sync.ballot.b32 %r0, %p0, 0xFFFFFFFF;` | 7 | 5 | 3 | 1* | 1* | 1:1（P） |
| W13 | `match.sync.any.b32 %r1, %r0, 0xFFFFFFFF;` | 7 | 5 | 3 | 1* | 1* | 1:1（P） |
| W14 | `elect.sync %r0\|%p0, 0xFFFFFFFF;` | 7 | 6 | 4 | 2* | 2* | 1:1（P） |
| BT04 | `bfe.u32 %r1, %r0, 8, 4;` | 8 | 8 | 8 | 0 | 0 | 1:N 候选（C） |
| BT05 | `bfe.s32 %r1, %r0, 8, 4;` | 8 | 8 | 8 | 0 | 0 | 1:N 候选（C） |
| BT06 | `bfi.b32 %r2, %r0, %r1, 8, 4;` | 9 | 9 | 9 | 0 | 0 | 1:N 候选（C） |
| BT07 | `popc.b32 %r1, %r0;` | 3 | 3 | 3 | 0 | 0 | 1:1（V，动态 O3 A/B） |
| BT08 | `clz.b32 %r1, %r0;` | 2 | 2 | 2 | 0 | 0 | 1:N（A） |
| BT09 | `brev.b32 %r1, %r0;` | 3 | 3 | 3 | 0 | 0 | 1:1（V，动态 O3 A/B） |
| BT10 | `fns.b32 %r2, %r0, 0, %r1;` | 77 | 70 | 70 | 0 | 0 | 1:N（A） |
| CL03 | `cvta.shared::cta.u64 %gen_addr, smem_data;` | 14 | 10 | 7 | 6* | 6* | 1:N 候选（C） |
| MK01 | `bar.warp.sync 0xFFFFFFFF;` | 4 | 3 | 2 | 1 | 0 | 协议分列 |
| ACT02 | `tanh.approx.f16x2 %v1, %v0;` | 7 | 3 | 3 | 3* | 3* | 1:N（A） |
| ACT04 | `tanh.approx.bf16x2 %v1, %v0;` | 7 | 3 | 3 | 3* | 3* | 1:N（A） |
| ACT06 | `ex2.approx.f16x2 %v1, %v0;` | 7 | 3 | 3 | 3* | 3* | 1:N（A） |
