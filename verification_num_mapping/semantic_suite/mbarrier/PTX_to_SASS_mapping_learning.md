# test_mbarrier_arrive_wait：全部 PTX 到 SASS mapping（B200）

本表只覆盖 [mbarrier_semantic.ptx](mbarrier_semantic.ptx) 的第 32–99 行，即
`test_mbarrier_arrive_wait` 的完整 kernel body。这里有 **34 条可执行 PTX 指令**，以及第 33--36 行
四条 `.reg` 虚拟寄存器声明。为了让这段源码不留空白，表格也列出四条声明，但明确标为“无直接 SASS”；
注释、标签和函数花括号仍不单列。

## 这段 kernel 整体做什么

`test_mbarrier_arrive_wait` 是一个 **composed runtime semantic test**，不是孤立的 STATIC_MAPPING
样例。它在同一个 32-thread CTA 中建立完整的 mbarrier 生命周期，用可检查的输出验证
`release arrive → acquire try_wait` 的 shared-memory 可见性。

启动约束和成功条件如下：

- 固定启动为一个 CTA、32 个线程：`<<<1, 32>>>`。两个 mbarrier 的 expected arrival count 都是 32，
  改变 block size 会破坏该测试的协议。
- 每个线程向 `smem_values[tid]` 写入 `tid + 1`，因此正确总和必须为 `1 + … + 32 = 528`。
- host 端只在 `p_out[0] == 528` 时接受该 kernel；这同时证明 leader 在 acquire 成功后读取到了所有
  release-published shared 值。

执行流程是：

1. leader 初始化主 mbarrier `smem_bar` 和进度用 control-mbarrier `smem_control_bar`，随后 `bar.sync 0`
   发布初始化结果。
2. 所有线程写入自己的 `tid + 1`，然后对主 barrier 执行 `mbarrier.arrive.release`，并保存返回的
   phase token。
3. 所有线程再对 control barrier 执行 `mbarrier.arrive.relaxed`。由于这条指令在主 arrive 之后，control
   barrier 完成意味着 32 个主 arrive 都已经发出。
4. 非 leader 直接退出。leader 先用 `try_wait.relaxed` 等 control barrier 完成；它只验证进度，**不是**
   payload 的内存可见性边。
5. leader 再用主 barrier 的 `try_wait.acquire` 等自己在第 2 步保存的 token。这个 acquire 才与所有线程的
   release arrive 配对，允许安全读取 `smem_values[0..31]`。
6. leader 计算总和、写回 `p_out[0] = 528`，在确认其他线程不再使用 barrier 后依次 `inval` 两个
   mbarrier，并返回。

关键的同步链是：`st.shared → mbarrier.arrive.release → 主 mbarrier 完成 →
mbarrier.try_wait.acquire → ld.shared → sum = 528`。若把 L76 的 acquire wait 换成 relaxed，或把 L60
放到 shared store 之前，这个测试就不能再隔离并验证 mbarrier 的 release→acquire 数据可见性；反过来，L72
的 relaxed control wait 只解决“leader 何时开始检查主 barrier”的进度问题。

这段代码因此同时回答两个问题：语义上，mbarrier 是否实现了正确的 release→acquire 数据发布；映射上，
组成完整协议的每一条 PTX 在 O0/O3 下到底如何变成 SASS。它**不**把 `bar.sync`、地址计算、分支或循环
辅助代码错误归因给某一条 mbarrier PTX。

## 映射证据与阅读约定

与上一版“只列 mbarrier 核心 SASS”不同，下面的 O0/O3 列保留了该 PTX 实际关联的**全部 SASS**：地址
构造、寄存器搬移、predicate、分支、访存和核心 `SYNCS.*` 都在表内。

证据是 CUDA 12.8.93、sm_100a、B200 上编译并实际运行通过的最终产物：

- [O0 带 PTX line-info 的反汇编](../artifacts/b200_20260724T061600Z_final/mbarrier/sass/mbarrier_semantic_O0_gp.sass)
- [O3 带 PTX line-info 的反汇编](../artifacts/b200_20260724T061600Z_final/mbarrier/sass/mbarrier_semantic_O3_gp.sass)

表中 `0x` 是该 kernel 内的 SASS 偏移。O0 的 source-line attribution 基本连续；O3 会跨行调度、融合和
尾部复制，所以某些 SASS 的 debug line 看起来落在相邻行。此时表按**数据流和控制流语义**归属，同时在
第四列明确指出这种情况。函数入口的 `LDC R1, c[0x0][0x37c]`，以及结尾的自跳转/NOP padding，没有对应的
有效 PTX 行，故不冒充任何一行 PTX 的 mapping。

| PTX指令 | SASS O0 | SASS O3 | 这条PTX指令是怎么映射的SASS指令，O0到O3优化了什么 | 这条指令的解释 |
|---|---|---|---|---|
| L33：.reg .pred %p_tid0, %p_done, %p_control_done, %p_sum_end | 无直接 SASS | 无直接 SASS | `.reg` 只声明 PTX 的虚拟 predicate 名称，不产生可执行机器指令。ptxas 根据整个 kernel 的 live range 把它们分配/复用为物理 predicate：本例 O0 可见 P0/P1，O3 可见 P0 及 uniform predicate UP0/UP1；不能把某一个物理 predicate 永久等同于某一个 PTX 名字。 | 声明 leader、两个 wait 结果和求和结束条件使用的谓词变量。 |
| L34：.reg .u32 %r_tid, %r_count, %r_offset, %r_value, %r_index, %r_sum | 无直接 SASS | 无直接 SASS | 这行只是六个 32-bit 虚拟寄存器的类型声明。O0/O3 会在各个使用点将它们着色为 R 寄存器、复用寄存器，或把值常量折叠/删除；没有“声明 → 某一条 SASS”的一对一映射。 | 声明 thread id、arrival count、地址偏移、payload、循环索引和累加器。 |
| L35：.reg .u32 %r_smem_base, %r_smem_addr | 无直接 SASS | 无直接 SASS | 这两个是 shared 地址的 PTX 虚拟寄存器。O0 在 L53/L56 附近物化 R10/R4；O3 将整个地址表达式提升到 UR7/R7 并融合到 LEA/STS/LDS.128，因此声明本身不发射 SASS。 | 声明 shared array 的基址与当前元素地址。 |
| L36：.reg .b64 %rd_out, %rd_state, %rd_control_state | 无直接 SASS | 无直接 SASS | PTX 的 b64 虚拟值不意味着存在一个独立的 64-bit 通用 SASS 寄存器。O0 常用一对 32-bit R/UR 保存地址或 phase token；O3 可把它们直接留在地址/操作数位置并缩短 live range。具体机器寄存器要看 L38、L60、L68、L72、L76、L92 等使用点。 | 声明 64-bit 输出指针、主 barrier token 和 control barrier token。 |
| L38：ld.param.u64 %rd_out, [p_out] | 0x0020 MOV R2, RZ<br>0x0030 LDC.64 R2, c[0x0][R2+0x380]<br>0x0040 MOV R0, R2<br>0x0050 MOV R2, R3<br>0x0060 MOV R0, R0<br>0x0070 MOV R2, R2 | 0x0200 LDC.64 R2, c[0x0][0x380] | O0 先以零偏移读取 64-bit parameter，再做 ABI/寄存器对搬移。O3 保留一次直接 LDC.64；它被调度到后面的 global store 附近，_gp 的物理 line annotation 显示为 L92，但语义上仍是 L38 的参数读取。 | 从 kernel 参数区取得 host 输出指针 %rd_out。 |
| L39：mov.u32 %r_tid, %tid.x | 0x0080 S2R R3, SR_TID.X<br>0x0090 MOV R3, R3 | 0x0010 S2R R7, SR_TID.X | PTX 读取 special register。O0 留下恒等 MOV；O3 直接把 thread id 留在 R7。 | 取得 CTA 内 thread index，用来选 leader、计算 shared 地址和写入值。 |
| L40：setp.eq.u32 %p_tid0, %r_tid, 0 | 0x00a0 ISETP.EQ.U32.AND P0, PT, R3, RZ, PT | 0x00a0 ISETP.NE.U32.AND P0, PT, R7.reuse, RZ, PT | O0 保留“tid == 0”。O3 反转 predicate 为“tid != 0”，使后续 `@P0 EXIT` 可直接送走 worker lanes；PTX 语义未变。 | 产生 leader predicate：只有 lane/thread 0 为真。 |
| L43：@!%p_tid0 bra AW_INIT_DONE | 0x00b0 PLOP3.LUT P1, PT, P0, PT, PT, 0x8, 0x80<br>0x00c0 MOV R0, R0<br>0x00d0 MOV R2, R2<br>0x00e0 MOV R3, R3<br>0x00f0 PLOP3.LUT P0, PT, P0, PT, PT, 0x80, 0x8<br>0x0100 @P1 BRA .L_x_25 | 0x00d0 VOTEU.ALL UP0, P0（与 L45 共享）<br>0x0120 VOTEU.ALL UP0, P0（与 L45 共享）<br>无独立 BRA | O0 将 predicate 取反后显式跳过 init block。O3 if-converts 这个小分支：init 的 SASS 被 predicate 掩码保护，不再需要一条对应的独立 BRA。这里引用的 VOTEU/谓词指令与 L45 共享，不能在逐行相加时重复计数。 | 非 leader 跳过两个 barrier 的初始化，直接进入发布初始化的 CTA barrier。 |
| L44：mov.u32 %r_count, 32 | 0x0110 MOV R6, 0x20 | 0x0040 UMOV UR5, 0x20 | 常数 32 在 O0 进入普通 R；O3 将它放入 uniform register，因为所有线程值相同。物理 line-info 将该 UMOV 放在 L45 init group 前，但语义来源是本行。 | 设置 mbarrier 的 expected arrival count = 32。 |
| L45：mbarrier.init.shared::cta.b64 [smem_bar], %r_count | 0x0120 MOV R4, 0x400<br>0x0130 IADD3 R4, PT, PT, RZ, R4, RZ<br>0x0140 S2R R5, SR_CgaCtaId<br>0x0150 LEA R4, R5, R4, 0x18<br>0x0160 MOV R4, R4<br>0x0170 R2UR UR4, R6<br>0x0180 UIADD3 UR4, UPT, UPT, -UR4, 0x100000, URZ<br>0x0190 USHF.L.U32 UR5, UR4, 0xb, URZ<br>0x01a0 USHF.L.U32 UR4, UR4, 0x1, URZ<br>0x01b0 MOV R10, UR4<br>0x01c0 MOV R11, UR5<br>0x01d0 R2UR UR4, R10<br>0x01e0 R2UR UR5, R11<br>0x01f0 R2UR UR6, R4<br>0x0200 FENCE.VIEW.ASYNC.S<br>0x0210 SYNCS.EXCH.64 URZ, [UR6], UR4 | 0x0020 S2UR UR8, SR_CgaCtaId<br>0x0030 UMOV UR4, 0x400<br>0x0070 ULEA UR9, UR8, UR4, 0x18<br>0x00d0 VOTEU.ALL UP0, P0<br>0x00f0 @!UP0 UIADD3 UR4, UPT, UPT, -UR5, 0x100000, URZ<br>0x0100 @!UP0 USHF.L.U32 UR5, UR4, 0xb, URZ<br>0x0110 @!UP0 USHF.L.U32 UR4, UR4, 0x1, URZ<br>0x0120 VOTEU.ALL UP0, P0<br>0x0130 @!UP0 SYNCS.EXCH.64 URZ, [UR9], UR4 | 两级含义：前半段构造 CTA-relative shared 地址及 64-bit 初始 state，最后一条 SYNCS.EXCH.64 才是 mbarrier 的核心写入。O3 将 CTA id/base 放进 UR、删除 identity MOV，并将 L43 的分支改为 uniform predication。 | 初始化主 mbarrier。它驻留在 smem_bar，当前 phase 需要 32 次 arrive。 |
| L46：mbarrier.init.shared::cta.b64 [smem_control_bar], %r_count | 0x0220 MOV R4, 0x400<br>0x0230 IADD3 R4, PT, PT, R4, 0x8, RZ<br>0x0240 S2R R5, SR_CgaCtaId<br>0x0250 LEA R4, R5, R4, 0x18<br>0x0260 MOV R4, R4<br>0x0270 R2UR UR4, R6<br>0x0280 UIADD3 UR4, UPT, UPT, -UR4, 0x100000, URZ<br>0x0290 USHF.L.U32 UR5, UR4, 0xb, URZ<br>0x02a0 USHF.L.U32 UR4, UR4, 0x1, URZ<br>0x02b0 MOV R6, UR4<br>0x02c0 MOV R7, UR5<br>0x02d0 R2UR UR4, R6<br>0x02e0 R2UR UR5, R7<br>0x02f0 R2UR UR6, R4<br>0x0300 SYNCS.EXCH.64 URZ, [UR6], UR4 | 0x0050 UIADD3 UR6, UPT, UPT, UR4, 0x8, URZ<br>0x0080 ULEA UR6, UR8, UR6, 0x18<br>0x00e0 VOTEU.ALL UP1, P0<br>0x0140 @!UP1 SYNCS.EXCH.64 URZ, [UR6], UR4 | 与 L45 同一 lowering 形态，但地址是 smem_control_bar（+8）。O3 复用 L45 已计算的 UR 基址和初始 state。 | 初始化独立的 control mbarrier；它只证明 worker 已执行主 arrive，不承载 payload 的可见性。 |
| L49：bar.sync 0 | 0x0310 WARPSYNC.ALL<br>0x0320 NOP<br>0x0330 BAR.SYNC.DEFER_BLOCKING 0x0 | 0x0150 BAR.SYNC.DEFER_BLOCKING 0x0 | 这是显式 PTX CTA barrier，不是 mbarrier 的额外展开。O0 保留 warp-synchronization 和一个调度 NOP；O3 可直接发出 CTA barrier。 | 确保所有线程在任何 arrive 之前都能看见两个已初始化的 barrier。 |
| L53：mov.u32 %r_smem_base, smem_values | 0x0340 MOV R4, 0x400<br>0x0350 IADD3 R4, PT, PT, R4, 0x10, RZ<br>0x0360 S2R R5, SR_CgaCtaId<br>0x0370 LEA R4, R5, R4, 0x18<br>0x0380 MOV R10, R4 | 0x0060 UIADD3 UR7, UPT, UPT, UR4, 0x10, URZ<br>0x0090 ULEA UR7, UR8, UR7, 0x18 | 共享符号不是立即数绝对地址：两级都要以 CTA shared base + 0x10 物化。O3 将结果提升到 uniform UR7，供 L54/L56/L57 和后面的 vector load 共用。 | 取得 smem_values[0] 的 32-bit shared-memory 基址。 |
| L54：shl.b32 %r_offset, %r_tid, 2 | 0x0390 SHF.L.U32 R4, R3, 0x2, RZ | 与 L56 融合为 0x00c0 LEA R7, R7, UR7, 0x2 | O0 是独立左移。O3 把 `tid << 2` 和 base 相加合成一条 scaled LEA；同一物理 SASS 同时实现 L54 与 L56，不能重复计数。 | 将 thread id 乘以 4，得到每个 u32 元素的字节偏移。 |
| L55：add.u32 %r_value, %r_tid, 1 | 0x03a0 IADD3 R3, PT, PT, R3, 0x1, RZ | 0x00b0 VIADD R0, R7, 0x1 | 两级都是加 1；O3 使用 VIADD 并保留更紧凑的寄存器分配。 | 每个线程准备自己的 payload：tid + 1。 |
| L56：add.u32 %r_smem_addr, %r_smem_base, %r_offset | 0x03b0 IADD3 R4, PT, PT, R10, R4, RZ | 与 L54 融合为 0x00c0 LEA R7, R7, UR7, 0x2 | O0 独立相加。O3 使用一条 scaled LEA 同时完成左移和地址相加。 | 得到 smem_values[tid] 的最终 shared 地址。 |
| L57：st.shared.u32 [%r_smem_addr], %r_value | 0x03c0 MOV R4, R4<br>0x03d0 STS [R4], R3 | 0x0160 STS [R7], R0 | 两级的核心 store 都是一条 STS；O0 多一个恒等地址搬移，O3 直接使用融合后的地址和值。 | 将每个线程的 tid + 1 写入 shared memory，供 leader 在 acquire wait 后求和。 |
| L60：mbarrier.arrive.release.cta.shared::cta.b64 %rd_state, [smem_bar] | 0x03e0 MOV R3, 0x400<br>0x03f0 IADD3 R3, PT, PT, RZ, R3, RZ<br>0x0400 S2R R4, SR_CgaCtaId<br>0x0410 LEA R3, R4, R3, 0x18<br>0x0420 MOV R3, R3<br>0x0430 SYNCS.ARRIVE.TRANS64.A1T0 R4, [R3+URZ], RZ | 0x0170 SYNCS.ARRIVE.TRANS64.A1T0 R2, [UR9], RZ | O0 为 shared barrier 重建地址；O3 复用 L45 的 UR9。核心 arrival SASS 都是一条 SYNCS.ARRIVE.TRANS64.A1T0，返回 token 放进 R4/R2。 | 将本线程计入主 barrier，并以 release 语义发布此前的 shared store；返回的 state token 供 L76 等待。 |
| L68：mbarrier.arrive.relaxed.cta.shared::cta.b64 %rd_control_state, [smem_control_bar] | 0x0440 MOV R3, 0x400<br>0x0450 IADD3 R3, PT, PT, R3, 0x8, RZ<br>0x0460 S2R R6, SR_CgaCtaId<br>0x0470 LEA R3, R6, R3, 0x18<br>0x0480 MOV R3, R3<br>0x0490 SYNCS.ARRIVE.TRANS64.A1T0 R6, [R3+URZ], RZ | 0x0180 SYNCS.ARRIVE.TRANS64.A1T0 R4, [UR6], RZ | 同样是一条 arrival-class SYNCS；本例中 relaxed/release 的可见 SASS 助记符相同。O3 复用 control-barrier UR6。 | 所有线程到达 control barrier，只用于确认进度；该 relaxed arrive 不替代主 barrier 的 release→acquire 数据同步。 |
| L69：@!%p_tid0 bra AW_EXIT | 0x04a0 PLOP3.LUT P0, PT, P0, PT, PT, 0x8, 0x80<br>0x04b0 MOV R3, R10<br>0x04c0 MOV R4, R4<br>0x04d0 MOV R5, R5<br>0x04e0 MOV R6, R6<br>0x04f0 MOV R7, R7<br>0x0500 @P0 BRA .L_x_26<br>0x0510 YIELD | 0x0190 @P0 EXIT | O0 保留 predicate 变换、live-register 搬移、branch 和一条 YIELD。O3 已在 L40 把 P0 定义为 tid != 0，因此直接 predicated EXIT；这是将“worker 不参与两个 wait、sum 和 inval”压缩成一条指令。 | 只有 leader 留下继续轮询；其他 31 个线程退出 kernel。 |
| L72：mbarrier.try_wait.relaxed.cta.shared::cta.b64 %p_control_done, [smem_control_bar], %rd_control_state | 0x0520 MOV R10, 0x400<br>0x0530 IADD3 R10, PT, PT, R10, 0x8, RZ<br>0x0540 S2R R11, SR_CgaCtaId<br>0x0550 LEA R10, R11, R10, 0x18<br>0x0560 MOV R10, R10<br>0x0570 MOV R11, R6<br>0x0580 MOV R11, R7<br>0x0590 SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [R10+URZ], R11 | 0x01a0 SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR6], R5<br>0x03c0 SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR6], R5 | O0 重建地址并复制 64-bit token。O3 复用 UR6，并将 source 中同一个 loop test 静态地放在首次检查与 loop back-edge 两处<br>0x01a0 的 debug annotation 受重排影响显示为 L69，但数据/控制流上它就是本行的首次 try_wait。 | 非 acquire 的 control polling：检查所有线程是否已经执行主 arrive。返回 predicate 给 L73。 |
| L73：@!%p_control_done bra AW_CONTROL_WAIT_LOOP | 0x05a0 PLOP3.LUT P0, PT, P0, PT, PT, 0x8, 0x80<br>0x05b0 @P0 BRA .L_x_27<br>0x05c0 YIELD | 0x01c0 @!P0 BRA .L_x_16<br>0x03d0 @!P0 BRA .L_x_16<br>0x03e0 BRA .L_x_18 | O0 显式取反 predicate、回跳、yield。O3 的 0x01c0 是首次失败回跳，0x03d0 是尾部复制后的失败回跳<br>0x03e0 是成功后的 fall-through 跳到主 wait。 | control try_wait 为假时回到 L72，形成 polling loop。 |
| L76：mbarrier.try_wait.acquire.cta.shared::cta.b64 %p_done, [smem_bar], %rd_state | 0x05d0 MOV R6, 0x400<br>0x05e0 IADD3 R6, PT, PT, RZ, R6, RZ<br>0x05f0 S2R R7, SR_CgaCtaId<br>0x0600 LEA R6, R7, R6, 0x18<br>0x0610 MOV R6, R6<br>0x0620 MOV R7, R4<br>0x0630 MOV R7, R5<br>0x0640 SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [R6+URZ], R7 | 0x01d0 SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR9], R3<br>0x03f0 SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [UR9], R3 | 核心都为 TRYWAIT phase check；O3 复用主 barrier 的 UR9，并同样将单个 PTX loop test 尾部复制为首次检查和 back-edge 检查。`acquire` 不一定会在打印的 SASS mnemonic 中单独拼写出来，不能因此丢掉其 PTX memory-order contract。 | 轮询主 barrier，直到 L60 返回的 token 对应 phase 完成；成功的 acquire 是随后读取 smem_values 的可见性前提。 |
| L77：@!%p_done bra AW_WAIT_LOOP | 0x0650 PLOP3.LUT P0, PT, P0, PT, PT, 0x8, 0x80<br>0x0660 @P0 BRA .L_x_28 | 0x01e0 @!P0 BRA .L_x_17<br>0x0400 @!P0 BRA .L_x_17<br>0x0410 BRA .L_x_19 | 与 L73 相同的 loop-control lowering。O3 有一份首次检查分支和一份尾部复制的 back-edge<br>0x0410 进入 success path。 | 主 try_wait 为假时继续轮询；为真时进入求和代码。 |
| L80：mov.u32 %r_index, 0 | 0x0670 MOV R4, RZ | 已删除；初始化被并入 L87/L88 的固定 32-element vector reduction | O0 显式设 loop index=0。O3 完全展开循环，不再需要动态 index 寄存器。 | 初始化 shared-array 求和的索引。 |
| L81：mov.u32 %r_sum, 0 | 0x0680 MOV R5, RZ<br>0x0690 MOV R4, R4<br>0x06a0 MOV R5, R5 | 已删除；归约树直接从 LDS.128 结果计算 | O0 显式置零 accumulator 并留下两个 identity MOV。O3 将初始零吸收进归约表达式。 | 初始化累加器。 |
| L83：setp.ge.u32 %p_sum_end, %r_index, 32 | 0x06b0 ISETP.GE.U32.AND P0, PT, R4, 0x20, PT | 已删除；循环被全展开为 8 个 LDS.128 | O0 每轮检查 index 是否到达 32。O3 证明 trip count 为常数并消除了循环条件。 | 求和循环的结束条件。 |
| L84：@%p_sum_end bra AW_SUM_FINISH | 0x06c0 @P0 BRA .L_x_29 | 已删除；无动态 loop exit | O0 根据 L83 的 predicate 跳到写回。O3 的 fixed-size unroll 无须条件分支。 | 若已遍历 32 个元素，结束求和。 |
| L85：shl.b32 %r_offset, %r_index, 2 | 0x06d0 SHF.L.U32 R6, R4, 0x2, RZ | 已吸收进 L87 的立即数地址：0x01f0 [UR9+0x10] 至 0x02b0 [UR9+0x80] | O0 每轮计算 index×4。O3 知道每个访问的常数 index，直接把 byte offset 编进 LDS.128 地址。 | 计算当前 shared 元素的字节偏移。 |
| L86：add.u32 %r_smem_addr, %r_smem_base, %r_offset | 0x06e0 IADD3 R6, PT, PT, R3, R6, RZ | 已吸收进 L87 的 [UR9+immediate] 地址 | O0 将 base 与本轮偏移相加。O3 不保留单独地址寄存器，而将它折入每条 vector load。 | 计算当前元素的 shared 地址。 |
| L87：ld.shared.u32 %r_value, [%r_smem_addr] | 0x06f0 MOV R6, R6<br>0x0700 LDS R6, [R6] | 0x01f0 LDS.128 R8, [UR9+0x10]<br>0x0210 LDS.128 R24, [UR9+0x20]<br>0x0220 LDS.128 R4, [UR9+0x30]<br>0x0230 LDS.128 R20, [UR9+0x40]<br>0x0240 LDS.128 R16, [UR9+0x50]<br>0x0250 LDS.128 R12, [UR9+0x60]<br>0x0280 LDS.128 R8, [UR9+0x70]<br>0x02b0 LDS.128 R24, [UR9+0x80] | O0 每次加载一个 u32。O3 把 32 次逻辑迭代变为 8 条 LDS.128，每条加载 4 个 u32；总共仍读取 32 个值。SASS 顺序因调度与 L88 的加法交错。 | 从 smem_values 读取一个待累加值；O3 的 vectorized 形式完成同样的 32 个逻辑加载。 |
| L88：add.u32 %r_sum, %r_sum, %r_value | 0x0710 IADD3 R5, PT, PT, R5, R6, RZ | 0x0260 IADD3 R8, PT, PT, R10, R8, R9<br>0x0270 IADD3 R24, PT, PT, R24, R8, R11<br>0x0290 IADD3 R24, PT, PT, R26, R24, R25<br>0x02a0 IADD3 R4, PT, PT, R4, R24, R27<br>0x02d0 IADD3 R4, PT, PT, R6, R4, R5<br>0x02e0 IADD3 R4, PT, PT, R20, R4, R7<br>0x0300 IADD3 R4, PT, PT, R22, R4, R21<br>0x0310 IADD3 R4, PT, PT, R16, R4, R23<br>0x0320 IADD3 R4, PT, PT, R18, R4, R17<br>0x0330 IADD3 R4, PT, PT, R12, R4, R19<br>0x0340 IADD3 R4, PT, PT, R14, R4, R13<br>0x0350 IADD3 R4, PT, PT, R8, R4, R15<br>0x0360 IADD3 R4, PT, PT, R10, R4, R9<br>0x0370 IADD3 R4, PT, PT, R24, R4, R11<br>0x0380 IADD3 R4, PT, PT, R26, R4, R25<br>0x0390 IMAD.IADD R27, R4, 0x1, R27 | O0 是标量 loop accumulator。O3 将 32 元素循环展开、把 128-bit load 的四个 lane 值合并成归约树，因此一行 PTX 在优化后对应一串 IADD3/IMAD.IADD；这是合法的 loop/vectorization 展开，不是 mbarrier lowering。 | 将读取值累加到总和。运行时 oracle 期望最后结果为 1+…+32=528。 |
| L89：add.u32 %r_index, %r_index, 1 | 0x0720 IADD3 R4, PT, PT, R4, 0x1, RZ | 已删除；O3 已知所有访问的 8 个固定 vector offsets | O0 更新 loop counter。O3 没有动态循环，因而无需 index 增量。 | 令求和循环前进到下一个元素。 |
| L90：bra AW_SUM_LOOP | 0x0730 MOV R5, R5<br>0x0740 MOV R4, R4<br>0x0750 BRA .L_x_30 | 已删除；由 L87/L88 的直线 vectorized reduction 替代 | O0 有回边和两个调度/identity MOV。O3 把循环完全展开成 straight-line code。 | 无条件回到 L83，继续下一轮求和。 |
| L92：st.global.u32 [%rd_out], %r_sum | 0x0010 LDC.64 R8, c[0x0][0x358]（为该 global store 提前加载 descriptor）<br>0x0760 MOV R3, R2<br>0x0770 MOV R2, R0<br>0x0780 MOV R2, R2<br>0x0790 MOV R3, R3<br>0x07a0 R2UR UR4, R8<br>0x07b0 R2UR UR5, R9<br>0x07c0 STG.E desc[UR4][R2.64], R5 | 0x01b0 LDCU.64 UR4, c[0x0][0x358]（为该 global store 提前加载 descriptor）<br>0x0200 LDC.64 R2, c[0x0][0x380]（L38 的 p_out 被调度到这里）<br>0x03a0 STG.E desc[UR4][R2.64], R27 | O0 要把 64-bit pointer/descriptor 与累加结果搬到 store 约定的寄存器。O3 将 descriptor 和 p_out load 跨行提前/延后调度，只留下最终 STG；这解释了为什么 O3 物理 SASS 顺序不是 PTX 行号顺序。 | 将 leader 计算的 528 写回 host 可读的全局输出地址。 |
| L95：mbarrier.inval.shared::cta.b64 [smem_bar] | 0x07d0 MOV R0, 0x400<br>0x07e0 IADD3 R0, PT, PT, RZ, R0, RZ<br>0x07f0 S2R R2, SR_CgaCtaId<br>0x0800 LEA R0, R2, R0, 0x18<br>0x0810 MOV R0, R0<br>0x0820 SYNCS.CCTL.IV [R0+URZ] | 0x02c0 SYNCS.CCTL.IV [UR9] | 核心是一条 invalidation SASS。O3 复用主 barrier 的 UR9，并把该操作调度在部分求和加法之前；它与那些独立加法没有依赖关系。 | 在确保其他线程不会再使用主 barrier 后，使 smem_bar 失效。 |
| L96：mbarrier.inval.shared::cta.b64 [smem_control_bar] | 0x0830 MOV R0, 0x400<br>0x0840 IADD3 R0, PT, PT, R0, 0x8, RZ<br>0x0850 S2R R2, SR_CgaCtaId<br>0x0860 LEA R0, R2, R0, 0x18<br>0x0870 MOV R0, R0<br>0x0880 SYNCS.CCTL.IV [R0+URZ] | 0x02f0 SYNCS.CCTL.IV [UR6] | 与 L95 相同，但地址为 control barrier。O3 复用 UR6；同样可与后续无关的归约加法交错调度。 | 使 control mbarrier 失效。 |
| L98：ret | 0x0890 EXIT | 0x03b0 EXIT | PTX return 的有效执行部分就是 EXIT。O0 的 0x08a0 之后以及 O3 的 0x0420 之后出现的自跳转和 NOP 是函数尾部 trap/padding，不对应 ret，也不应错误算成 ret 的 1:N mapping。 | 结束当前线程的 kernel 执行。 |

## 读完这张表后应得到的结论

1. 这 34 条 PTX 并不都保持 1:1。O0 已经会为地址、64-bit 参数和 predicate 生成多条 SASS；O3 进一步
   进行 predicate conversion、常量/地址提升、循环展开、LDS.128 向量化和跨行调度。
2. 语义上有 8 个独立的 mbarrier 操作：两个 init 是 SYNCS.EXCH.64，两个 arrive 是
   SYNCS.ARRIVE.TRANS64.A1T0，两个 try_wait 是 SYNCS.PHASECHK.TRANS64.TRYWAIT，两个 inval 是
   SYNCS.CCTL.IV。O0 的 `EIATTR_MBARRIER_INSTR_OFFSETS` 记录 8 个静态位置；O3 因 L72/L76 的
   tail duplication 额外记录 0x03c0/0x03f0，故共有 10 个静态位置。它们都已在表中归属，没有未解释的
   第九类 mbarrier 操作。
3. 不能按 SASS 的文本邻近关系归因。尤其 O3 将 L95/L96 的 inval 移到归约加法中间，也把 p_out 的
   LDC.64 挪到最终 store 附近；应以 PTX 数据依赖、控制流和 _gp line-info 一起判断。
4. 同一个物理 O3 SASS 可以服务多条 PTX：例如 L54 与 L56 共用一条 LEA；而同一条循环 PTX 也可能因
   tail duplication 在静态 SASS 中出现两次，例如 L72 和 L76。表格逐行展示它们，但不能把这些行简单
   相加成“独立硬件操作数”。
