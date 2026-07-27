# PTX to SASS mapping

# 正例

首先看一个1：1的完整例子

```Assembly language
.version 8.7                                     // PTX ISA 8.7
.target sm_100a
.address_size 64                                 // 普通地址空间使用 64 位地址。
.file 1 "ptx_mapping_case.ptx"                   // 对调试文件编号，后面的 .loc 指令引用它

// T01: tcgen05.mma.cta_group::1.kind::tf32 (standard)
// Requires allocated TMEM and valid SMEM descriptors.
.visible .entry test_tcgen05_mma_cg1_tf32(
    .param .u32 p_taddr,          // 累加矩阵 D 在 TMEM 中的地址
    .param .u64 p_smem_desc_a,    // 矩阵 A 的 SMEM descriptor
    .param .u64 p_smem_desc_b,    // 矩阵 B 的 SMEM descriptor
    .param .u32 p_idesc           // MMA instruction descriptor
) {
    .reg .b32 %taddr;             // 寄存器声明
    .reg .b64 %desc_a, %desc_b;
    .reg .b32 %idesc;
    .reg .b32 %mask<4>;           // mask 包含四个 32 位元素
    .reg .pred %enable;

    ld.param.b32 %taddr, [p_taddr];
    ld.param.b64 %desc_a, [p_smem_desc_a];
    ld.param.b64 %desc_b, [p_smem_desc_b];
    ld.param.b32 %idesc, [p_idesc];
    mov.u32 %mask0, 0;
    mov.u32 %mask1, 0;
    mov.u32 %mask2, 0;
    mov.u32 %mask3, 0;
    setp.ne.u32 %enable, %idesc, 0;

    .loc 1 10 0
    // === target instruction ===
    .loc 1 100 0
    tcgen05.mma.cta_group::1.kind::tf32 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;
    // === end target instruction ===
    .loc 1 200 0
    .loc 1 300 0

    ret;
}

```

O1：

```Assembly language
//--------------------- .text.test_tcgen05_mma_cg1_tf32 --------------------------
        .section        .text.test_tcgen05_mma_cg1_tf32,"ax",@progbits
        .align        128
        .global         test_tcgen05_mma_cg1_tf32
        .type           test_tcgen05_mma_cg1_tf32,@function
        .size           test_tcgen05_mma_cg1_tf32,(.L_x_2 - test_tcgen05_mma_cg1_tf32)
        .other          test_tcgen05_mma_cg1_tf32,@"STO_CUDA_ENTRY STV_DEFAULT"
test_tcgen05_mma_cg1_tf32:
.text.test_tcgen05_mma_cg1_tf32:
        //## File "ptx_mapping_case.ptx", line 10
        /*0000*/                   LDC R1, c[0x0][0x37c] ;
        /*0010*/                   MOV R0, RZ ;
        /*0020*/                   LDC R0, c[0x0][R0+0x380] ;
        /*0030*/                   MOV R0, R0 ;
        /*0040*/                   MOV R2, 0x8 ;
        /*0050*/                   LDC.64 R2, c[0x0][R2+0x380] ;
        /*0060*/                   MOV R15, R2 ;
        /*0070*/                   MOV R16, R3 ;
        /*0080*/                   MOV R15, R15 ;
        /*0090*/                   MOV R16, R16 ;
        /*00a0*/                   MOV R2, 0x10 ;
        /*00b0*/                   LDC.64 R2, c[0x0][R2+0x380] ;
        /*00c0*/                   MOV R13, R2 ;
        /*00d0*/                   MOV R14, R3 ;
        /*00e0*/                   MOV R13, R13 ;
        /*00f0*/                   MOV R14, R14 ;
        /*0100*/                   MOV R2, 0x18 ;
        /*0110*/                   LDC R2, c[0x0][R2+0x380] ;
        /*0120*/                   MOV R2, R2 ;
        /*0130*/                   MOV R4, RZ ;
        /*0140*/                   MOV R5, RZ ;
        /*0150*/                   MOV R6, RZ ;
        /*0160*/                   MOV R7, RZ ;
        /*0170*/                   ISETP.NE.U32.AND P0, PT, R2, RZ, PT ;
        //## File "ptx_mapping_case.ptx", line 100
        /*0180*/                   IADD3 R0, PT, PT, R0, RZ, RZ ;
        /*0190*/                   MOV R3, R2 ;
        /*01a0*/                   MOV R2, RZ ;
        /*01b0*/                   SEL R8, RZ, 0x1, !P0 ;
        /*01c0*/                   MOV R9, R4 ;
        /*01d0*/                   MOV R10, R5 ;
        /*01e0*/                   MOV R11, R6 ;
        /*01f0*/                   MOV R12, R7 ;
        /*0200*/                   MOV R4, R15 ;
        /*0210*/                   MOV R5, R16 ;
        /*0220*/                   MOV R4, R4 ;
        /*0230*/                   MOV R5, R5 ;
        /*0240*/                   MOV R6, R13 ;
        /*0250*/                   MOV R7, R14 ;
        /*0260*/                   MOV R6, R6 ;
        /*0270*/                   MOV R7, R7 ;
        /*0280*/                   MOV R0, R0 ;
        /*0290*/                   MOV R2, R2 ;
        /*02a0*/                   MOV R3, R3 ;
        /*02b0*/                   MOV R8, R8 ;
        /*02c0*/                   MOV R9, R9 ;
        /*02d0*/                   MOV R10, R10 ;
        /*02e0*/                   MOV R11, R11 ;
        /*02f0*/                   MOV R12, R12 ;
        /*0300*/                   ISETP.NE.AND P0, PT, R8, RZ, PT ;
        /*0310*/                   R2UR UR4, R4 ;
        /*0320*/                   R2UR UR5, R5 ;
        /*0330*/                   R2UR UR6, R6 ;
        /*0340*/                   R2UR UR7, R7 ;
        /*0350*/                   R2UR UR8, R2 ;
        /*0360*/                   R2UR UR9, R3 ;
        /*0370*/                   R2UR UR12, R9 ;
        /*0380*/                   R2UR UR13, R10 ;
        /*0390*/                   R2UR UR14, R11 ;
        /*03a0*/                   R2UR UR15, R12 ;
        /*03b0*/                   VOTEU.ANY UP0, P0 ;
        /*03c0*/                   R2UR UR10, R0 ;
        /*03d0*/                   PLOP3.LUT P1, PT, PT, PT, PT, 0x80, 0x8 ;
.L_x_0:
        /*03e0*/               @P1 ELECT P0, URZ, PT ;
        /*03f0*/               @P0 PLOP3.LUT P1, PT, P0, PT, PT, 0x8, 0x80 ;
        /*0400*/                   UTCHMMA gdesc[UR4], gdesc[UR6], tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0 ;
        /*0410*/                   PLOP3.LUT P0, PT, PT, PT, PT, 0x8, 0x80 ;
        /*0420*/               @P1 BRA.U.ANY `(.L_x_0) ;
        //## File "ptx_mapping_case.ptx", line 300
        /*0430*/                   EXIT ;
.L_x_1:
        /*0440*/                   BRA `(.L_x_1);
        /*0450*/                   NOP;
        /*0460*/                   NOP;
        /*0470*/                   NOP;
        /*0480*/                   NOP;
        /*0490*/                   NOP;
        /*04a0*/                   NOP;
        /*04b0*/                   NOP;
        /*04c0*/                   NOP;
        /*04d0*/                   NOP;
        /*04e0*/                   NOP;
        /*04f0*/                   NOP;
.L_x_2:
```

O3：

```Assembly language
.section        .text.test_tcgen05_mma_cg1_tf32,"ax",@progbits
        .align        128
        .global         test_tcgen05_mma_cg1_tf32
        .type           test_tcgen05_mma_cg1_tf32,@function
        .size           test_tcgen05_mma_cg1_tf32,(.L_x_2 - test_tcgen05_mma_cg1_tf32)
        .other          test_tcgen05_mma_cg1_tf32,@"STO_CUDA_ENTRY STV_DEFAULT"
test_tcgen05_mma_cg1_tf32:
.text.test_tcgen05_mma_cg1_tf32:
        //## File "ptx_mapping_case.ptx", line 10
        /*0000*/                   LDC R1, c[0x0][0x37c] ;
        /*0010*/                   LDCU UR5, c[0x0][0x398] ;
        //## File "ptx_mapping_case.ptx", line 100
        /*0020*/                   PLOP3.LUT P0, PT, PT, PT, PT, 0x80, 0x8 ;
        /*0030*/                   LDCU UR6, c[0x0][0x380] ;
        /*0040*/                   LDCU.64 UR8, c[0x0][0x388] ;
        /*0050*/                   LDCU.64 UR10, c[0x0][0x390] ;
        /*0060*/                   UMOV UR4, URZ ;
        /*0070*/                   UISETP.NE.U32.AND UP0, UPT, UR5, URZ, UPT ;
.L_x_0:
        /*0080*/               @P0 ELECT P1, URZ, PT ;
        /*0090*/                   UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0 ;
        /*00a0*/               @P1 PLOP3.LUT P0, PT, P1, PT, PT, 0x8, 0x80 ;
        /*00b0*/                   PLOP3.LUT P1, PT, PT, PT, PT, 0x8, 0x80 ;
        /*00c0*/               @P0 BRA.U.ANY `(.L_x_0) ;
        //## File "ptx_mapping_case.ptx", line 300
        /*00d0*/                   EXIT ;
.L_x_1:
        /*00e0*/                   BRA `(.L_x_1);
        /*00f0*/                   NOP;
        /*0100*/                   NOP;
        /*0110*/                   NOP;
        /*0120*/                   NOP;
        /*0130*/                   NOP;
        /*0140*/                   NOP;
        /*0150*/                   NOP;
        /*0160*/                   NOP;
        /*0170*/                   NOP;
.L_x_2:
```

可以看到，一条 PTX `tcgen05.mma` 在 lowering 到 SASS 后，并不只对应一条 `UTCHMMA`，而是生成了一段完整的控制与操作数准备序列（代码内的红底部分），包括：

- `LDCU / UMOV`：加载或构造 uniform operand。例如，`UMOV UR4, URZ` 将零值写入 uniform register `UR4`；

- `UISETP / PLOP3.LUT`：生成并维护 uniform predicate，用于实现 PTX 中的 enable predicate，以及后续的选举与循环控制；

- `ELECT`：在线程集合中选出负责执行当前控制路径的线程；

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=NzVlMjU4ZTExNzAxMjlmZDgyNTVhOTM3MTc2NDZkN2NfZDUyMjZlODlmMzQxM2U5YWU3MDlmNTM0Njk5MTRkZjhfSUQ6NzY2NTUzMjUxNzM0ODc0MDA2OF8xNzg1MTM0MjEyOjE3ODUyMjA2MTJfVjM)

- `BRA.U.ANY`：根据选举结果和谓词状态维持控制循环；

- `UTCHMMA`：lowering 序列中唯一显式执行 Tensor Core MMA 运算的 SASS 指令。

因此，该 PTX 指令的 lowering 结果可以看作：`uniform operand 准备 + 谓词与选举控制 + UTCHMMA 指令本体`。

与整数除法等软件展开型指令不同，`tcgen05.mma` 的核心数值计算没有在 SASS 层面展开为多条算术指令，而是由单条 `UTCHMMA` 表达。不过，完整的 PTX 语义仍需要外围的 uniform operand 准备、谓词处理、线程选举和循环控制代码共同实现。

因此，更准确地说，`tcgen05.mma` 的核心 MMA 运算在 SASS opcode 层面呈现近似 `1:1` 映射，而整条 PTX 指令的完整 lowering 并不是严格的 `1:1` 映射。

根据上面的 `tcgen05.mma` 例子，可以明确：在统计一条 PTX 指令对应的 SASS 指令数量时，允许将为实现该 PTX 语义而生成的辅助控制指令计入完整 lowering 序列；但在判断核心计算语义是否发生软件展开时，应只考察实际执行数值计算的 SASS 指令。

类似指令：**tcgen05\.cp（UTCCP）、tcgen05\.ld（LDTM）、tcgen05\.st（STTM）（注意这三个不是 single thread issue 指令，因此展开 SASS 除了mma 的几个 SASS 指令还有 ****`WARPSYNC.ALL`****，因为要满足同 warp 内隐含的同步语义）**

# 反例

```Assembly language
.version 8.7
.target sm_100a
.address_size 64
.file 1 "ptx_mapping_case.ptx"

.visible .entry test_barrier_cluster_arrive() {
    .loc 1 10 0
    // === target instruction ===
    .loc 1 100 0
    barrier.cluster.arrive;
    // === end target instruction ===
    .loc 1 200 0
    .loc 1 300 0
    ret;
}
```

O0

```Assembly language
.text.test_barrier_cluster_arrive:
        //## File ".nv_debug_ptx_txt", line 6
        /*0000*/                   LDC R1, c[0x0][0x37c] ;
        //## File ".nv_debug_ptx_txt", line 10
        /*0010*/                   LDC R0, c[0x0][0x36c] ;
        /*0020*/                   ISETP.EQ.U32.AND P0, PT, R0, 0x1, PT ;
        /*0030*/              @!P0 BRA `(.L_x_0) ;
        /*0040*/                   MOV R0, 0xffffffff ;
        /*0050*/                    WARPSYNC.COLLECTIVE.ALL `(.L_x_1) ;
        /*0060*/                   MEMBAR.ALL.GPU ;
        /*0070*/                   ERRBAR ;
        /*0080*/                   CGAERRBAR ;
        /*0090*/                   UCGABAR_ARV ;
        /*00a0*/                   ENDCOLLECTIVE ;
.L_x_1:
        /*00b0*/                   BRA `(.L_x_2) ;
.L_x_0:
        /*00c0*/                   MOV R0, 0xffffffff ;
        /*00d0*/                   WARPSYNC.COLLECTIVE R0, `(.L_x_2) ;
        /*00e0*/                   NOP ;
        /*00f0*/                   ENDCOLLECTIVE ;
.L_x_2:
        //## File ".nv_debug_ptx_txt", line 14
        /*0100*/                   EXIT ;
.L_x_3:
        /*0110*/                   BRA `(.L_x_3);
        /*0120*/                   NOP;
        /*0130*/                   NOP;
        /*0140*/                   NOP;
        /*0150*/                   NOP;
        /*0160*/                   NOP;
        /*0170*/                   NOP;
        /*0180*/                   NOP;
        /*0190*/                   NOP;
        /*01a0*/                   NOP;
        /*01b0*/                   NOP;
        /*01c0*/                   NOP;
        /*01d0*/                   NOP;
        /*01e0*/                   NOP;
        /*01f0*/                   NOP;
.L_x_4:
```

O3

```Assembly language
.text.test_barrier_cluster_arrive:
        //## File ".nv_debug_ptx_txt", line 6
        /*0000*/                   LDC R1, c[0x0][0x37c] ;
        //## File ".nv_debug_ptx_txt", line 10
        /*0010*/                   LDC R0, c[0x0][0x36c] ;
        /*0020*/                   ISETP.EQ.U32.AND P0, PT, R0, 0x1, PT ;
        /*0030*/              @!P0 BRA `(.L_x_0) ;
        /*0040*/                   MEMBAR.ALL.GPU ;
        /*0050*/                   ERRBAR;
        /*0060*/                   CGAERRBAR ;
        /*0070*/                   UCGABAR_ARV ;
        /*0080*/                   BRA `(.L_x_1) ;
.L_x_0:
        /*0090*/                   NOP ;
.L_x_1:
        //## File ".nv_debug_ptx_txt", line 14
        /*00a0*/                   EXIT ;
.L_x_2:
        /*00b0*/                   BRA `(.L_x_2);
        /*00c0*/                   NOP;
        /*00d0*/                   NOP;
        /*00e0*/                   NOP;
        /*00f0*/                   NOP;
        /*0100*/                   NOP;
        /*0110*/                   NOP;
        /*0120*/                   NOP;
        /*0130*/                   NOP;
        /*0140*/                   NOP;
        /*0150*/                   NOP;
        /*0160*/                   NOP;
        /*0170*/                   NOP;
.L_x_3:
```

可以看到，一条 PTX `barrier.cluster.arrive` 在 lowering 到 SASS 后，并不只对应一条 `UCGABAR_ARV`，而是生成了一段完整的路径分派、warp 协同和到达前状态处理序列，包括：

- `LDC / ISETP.EQ / @!P0 BRA`：`LDC` 从 constant memory 中读取运行时的 cluster 相关配置，`ISETP` 根据该值设置谓词，随后 `BRA` 在 cluster 路径和兼容路径之间进行分派。

- `WARPSYNC.COLLECTIVE(.ALL) / ENDCOLLECTIVE`：在 O0 lowering 中包围 barrier 操作，保证 warp 内参与线程以 collective 方式执行；

- `MEMBAR.ALL.GPU`：对此前的内存访问建立顺序约束，使 arrive 之前产生的内存操作在 barrier 到达被发布前完成必要的排序。

- `ERRBAR + CGAERRBAR`：位于 `UCGABAR_ARV` 之前，完成到达操作所需的内存顺序及 cluster 相关状态处理；

- `UCGABAR_ARV`：lowering 序列中实际执行 cluster barrier arrive 的 SASS 指令；

- `MOV / BRA`：负责 collective mask 的构造及控制流汇合。

因此，`barrier.cluster.arrive` 的完整 lowering 可概括为：`配置分派 + collective 协同 + 到达前状态处理 + UCGABAR_ARV`。其中，核心同步动作由单条 `UCGABAR_ARV` 表达；其余指令用于实现 PTX 的作用域、顺序和执行协同语义。

对于 `barrier.cluster.wait`，lowering 同样不只包含一条无条件的 wait 指令，而是包含两类执行路径：

- `UCGABAR_WAIT`：cluster 路径中实际等待参与 CTA 到达 barrier 的 SASS 指令；其后的 `CCTL.IVALL` 用于完成 wait 后所需的缓存状态处理；

- `SHF / LOP3.LUT + BAR.SYNC.DEFER_BLOCKING`：兼容路径中先构造普通 barrier 的操作数，再执行可延后阻塞的 CTA barrier；（O3中被直接优化掉）

- `LDC / ISETP.EQ / BRA`：根据运行时 cluster 配置在上述两条路径之间分派；

- `WARPSYNC.COLLECTIVE(.ALL) / ENDCOLLECTIVE`、`MOV` 和 `BRA`：用于 warp 内 collective 协同、参数路由和控制流汇合。

所以，`barrier.cluster.wait` 的完整 lowering 是：`配置分派 + collective 协同 + UCGABAR_WAIT/CCTL.IVALL cluster 路径 + BAR.SYNC.DEFER_BLOCKING 兼容路径`。`UCGABAR_WAIT` 是 cluster 路径中的核心等待操作，但完整 PTX 语义仍依赖外围的配置判断、缓存状态处理和兼容路径代码。

与 `tcgen05.mma` 一样，这两条指令的核心硬件操作在 SASS opcode 层面均近似为 `1:1` 映射；不过，若按完整 lowering 统计，则它们都不是严格的 `1:1` 映射。不同之处在于，外围指令并非数值计算的软件展开，而是同步语义所需的控制、顺序和协同机制。

# 统计

1. 第一类：算术宽度拆分或软件算法展开 （20条）

|ID|PTX|O0SASS|O3SASS|解释|
|---|---|---|---|---|
|I02|~~add\.s64 %rd2, %rd0, %rd1;~~<br>|~~IADD3（低位加，产生进位加到高位） → IADD3\.X~~|~~—（编译器优化消除）~~|~~64\-bit 值由两个 32\-bit half 保存，而 IADD3 一次只覆盖一个 half；先计算低 32 位并产生 carry，再由 IADD3\.X 把 carry 加入高 32 位。~~|
|I03|~~sub\.s64 %rd2, %rd0, %rd1;~~|~~IADD3（低位减，产生进位减到高位） → IADD3\.X~~<br>|~~—（编译器优化消除）~~|~~原因同 64\-bit 加法：一条指令不能同时完成两个 half 的借位传播；先做低半减法，再用 IADD3\.X 完成带 borrow 的高半。~~|
|I07|~~mul\.lo\.s64 %rd2, %rd0, %rd1;~~<br>|~~MOV → MOV → IMAD\.WIDE\.U32 → MOV → MOV → IMAD\.WIDE\.U32 → MOV → MOV → MOV → MOV → IMAD\.WIDE\.U32 → MOV → MOV → IADD3 → IADD3\.X → IMAD\.WIDE\.U32\.X → MOV → MOV~~|~~—（编译器优化消除）~~<br>|~~64×64 乘法要拆为多个 32×32 partial product，单条 IMAD 无法覆盖；先排列寄存器对，再以 IMAD\.WIDE 计算部分积，用 IADD3/IADD3\.X 合并交叉项与进位，最后取低 64 位。~~|
|I09|~~mad\.wide\.u32 %rd0, %r0, %r1, %rd0;~~|~~IMAD\.U32 → IMAD\.HI\.U32 → MOV → IADD3 → IADD3\.X~~|~~—（编译器优化消除）~~|~~语义同时要求 32×32→64 乘法和 64\-bit 加法，先取得乘积低/高 half，随后将它们与累加器低/高 half 相加并传播 carry。~~|
|I10|~~div\.s32 %r2, %r0, %r1;~~<br>|~~IABS → I2F\.U32\.RP → MUFU\.RCP → IADD3 → F2I\.FTZ\.U32\.TRUNC\.NTZ → IMAD\.U32 → IADD3 → IMAD\.HI\.U32 → IADD3 → IABS → IMAD\.HI\.U32 → IMAD\.U32 → IADD3 → IADD3 → ISETP\.LE\.U32\.AND → SEL → IADD3 → IADD3 → SEL → ISETP\.GE\.U32\.AND → SEL → LOP3\.LUT → MOV → ISETP\.GE\.AND → @P0 BRA → IADD3 → MOV → ISETP\.NE\.AND → LOP3\.LUT → PLOP3\.LUT → SEL → MOV~~|~~I2F\.U32\.RP → HFMA2 → MOV → LDCU\.64 → MUFU\.RCP → IADD3 → F2I\.FTZ\.U32\.TRUNC\.NTZ → IMAD → IMAD\.HI\.U32 → IMAD\.HI\.U32 → IMAD → ISETP\.GE\.U32\.AND → @P0 VIADD → @P0 IADD3 → ISETP\.GE\.U32\.AND → @P1 VIADD~~|~~先取绝对值并用 MUFU\.RCP 求倒数估计，再用 IMAD 重建商/余数，接着 ISETP/SEL 做精确修正，最后恢复符号并处理除零等边界。~~|
|I11|~~div\.u32 %r2, %r0, %r1;~~<br>|~~I2F\.U32\.RP → MUFU\.RCP → IADD3 → F2I\.FTZ\.U32\.TRUNC\.NTZ → IMAD\.U32 → IADD3 → IMAD\.HI\.U32 → IADD3 → IMAD\.HI\.U32 → IMAD\.U32 → IADD3 → IADD3 → ISETP\.GE\.U32\.AND → SEL → IADD3 → IADD3 → SEL → ISETP\.GE\.U32\.AND → SEL → MOV → ISETP\.NE\.U32\.AND → LOP3\.LUT → PLOP3\.LUT → SEL~~|~~I2F\.U32\.RP → HFMA2 → MOV → LDCU\.64 → MUFU\.RCP → IADD3 → F2I\.FTZ\.U32\.TRUNC\.NTZ → IMAD → IMAD\.HI\.U32 → IMAD\.HI\.U32 → IMAD → ISETP\.GE\.U32\.AND → @P0 VIADD → @P0 IADD3 → ISETP\.GE\.U32\.AND → @P1 VIADD~~|~~没有符号恢复步骤，其他同上。~~<br>|
|I12|~~rem\.s32 %r2, %r0, %r1;~~<br>|~~IABS → I2F\.U32\.RP → MUFU\.RCP → IADD3 → F2I\.FTZ\.U32\.TRUNC\.NTZ → IMAD\.U32 → IADD3 → IMAD\.HI\.U32 → IADD3 → IABS → IMAD\.HI\.U32 → IMAD\.U32 → IADD3 → ISETP\.LE\.U32\.AND → IADD3 → SEL → IADD3 → ISETP\.LE\.U32\.AND → SEL → MOV → ISETP\.GE\.AND → @P0 BRA → IADD3 → MOV → ISETP\.NE\.AND → LOP3\.LUT → PLOP3\.LUT → SEL → MOV~~|~~I2F\.U32\.RP → HFMA2 → LDCU\.64 → MUFU\.RCP → IADD3 → F2I\.FTZ\.U32\.TRUNC\.NTZ → IMAD → IMAD\.HI\.U32 → MOV → IMAD\.HI\.U32 → IMAD → ISETP\.GE\.U32\.AND → @P0 IADD3 → ISETP\.GE\.U32\.AND → @P0 IADD3~~|~~计算两个有符号 32\-bit 整数相除后的余数。~~<br>|
|I13|~~rem\.u32 %r2, %r0, %r1;~~|~~I2F\.U32\.RP → MUFU\.RCP → IADD3 → F2I\.FTZ\.U32\.TRUNC\.NTZ → IMAD\.U32 → IADD3 → IMAD\.HI\.U32 → IADD3 → IMAD\.HI\.U32 → IMAD\.U32 → IADD3 → ISETP\.GE\.U32\.AND → IADD3 → SEL → IADD3 → ISETP\.GE\.U32\.AND → SEL → MOV → ISETP\.NE\.U32\.AND → LOP3\.LUT → PLOP3\.LUT → SEL → MOV~~|~~I2F\.U32\.RP → HFMA2 → LDCU\.64 → MUFU\.RCP → IADD3 → F2I\.FTZ\.U32\.TRUNC\.NTZ → IMAD → IMAD\.HI\.U32 → MOV → IMAD\.HI\.U32 → IMAD → ISETP\.GE\.U32\.AND → @P0 IADD3 → ISETP\.GE\.U32\.AND → @P0 IADD3~~|~~计算两个无符号 32\-bit 整数相除后的余数。~~<br>|
|I15|~~shl\.b64 %rd1, %rd0, 4;~~|~~SHF\.L\.U64\.HI → SHF\.L\.U32~~|~~—（编译器优化消除）~~|~~把一个 64\-bit 位串左移指定的位数。~~|
|I16|~~shr\.s64 %rd1, %rd0, 4;~~|~~SHF\.R\.S64 → SHF\.R\.S32\.HI~~|~~—（编译器优化消除）~~|~~对一个有符号 64\-bit 整数执行算术右移，左侧补符号位。~~|
|I18A|~~and\.b64 %rd2, %rd0, %rd1;~~|~~LOP3\.LUT → LOP3\.LUT~~|~~—（编译器优化消除）~~|~~对两个 64\-bit 位串逐位执行 AND。~~|
|I18B|~~or\.b64 %rd2, %rd0, %rd1;~~|~~LOP3\.LUT → LOP3\.LUT~~|~~—（编译器优化消除）~~|~~对两个 64\-bit 位串逐位执行 OR。~~|
|I21B|~~mov\.b64 %rd1, %rd0;~~|~~MOV → MOV~~|~~—（编译器优化消除）~~|~~64\-bit PTX 寄存器~~|
|C05|~~cvt\.s64\.s32 %rd0, %r0;~~|~~SHF\.R\.S32\.HI → MOV → MOV~~|~~—（编译器优化消除）~~|~~把一个有符号 32\-bit 整数符号扩展为有符号 64\-bit 整数。~~|
|FP13|~~rcp\.rn\.f64 %fd1, %fd0;~~<br>|~~MOV → IADD3 → MOV → MOV → MOV → MUFU\.RCP64H → LOP3\.LUT → MOV → MOV → DADD → MOV → MOV → DFMA → DFMA → DFMA → DFMA → DFMA → FADD → FSETP\.GEU\.AND → MOV → @P0 BRA → LOP3\.LUT → IADD3 → MOV → MOV → MOV → CALL\.REL\.NOINC~~|~~MUFU\.RCP64H → HFMA2 → MOV → HFMA2 → DFMA → DFMA → DFMA → DFMA → DFMA~~|~~按 round\-to\-nearest 模式计算双精度倒数 ~~~~`1/x`~~~~。~~<br>|
|FP14|~~sqrt\.rn\.f64 %fd1, %fd0;~~<br>|~~MOV → IADD3 → MOV → MOV → MOV → MUFU\.RSQ64H → LOP3\.LUT → DMUL → DADD → MOV → MOV → DFMA → MOV → MOV → MOV → MOV → DFMA → DMUL → DFMA → MOV → MOV → MOV → DMUL → MOV → IADD3 → DADD → DFMA → DFMA → ISETP\.LT\.U32\.AND → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → @P0 BRA → MOV → MOV → MOV → MOV → MOV → MOV → CALL\.REL\.NOINC~~|~~MUFU\.RSQ64H → HFMA2 → MOV → IMAD\.MOV\.U32 → DMUL → DFMA → MOV → DFMA → DMUL → DFMA → DMUL → VIADD → DFMA → DFMA~~|~~按 round\-to\-nearest 模式计算双精度平方根 ~~~~`sqrt(x)`~~~~。~~|
|BT08|~~clz\.b32 %r1, %r0;~~|~~FLO\.U32 → IADD3~~|~~—（编译器优化消除）~~|~~统计一个 32\-bit 值最高有效位之前的前导零数量。~~|
|BT10|~~fns\.b32 %r2, %r0, 0, %r1;~~<br>|~~ISETP\.EQ\.AND → MOV → PLOP3\.LUT → @P1 BRA → ISETP\.GT\.AND → @P1 BRA → BREV → SHF\.R\.U32\.HI → SGXT\.U32 → IADD3 → IADD3 → PLOP3\.LUT → BRA → MOV → SHF\.L\.U32 → LOP3\.LUT → MOV → MOV → SHF\.L\.U32 → LOP3\.LUT → POPC → ISETP\.LT\.AND → PRMT → POPC → ISETP\.LT\.U32\.AND → SHF\.R\.U32\.HI → IADD3 → IADD3 → SEL → SEL → SEL → PRMT → POPC → ISETP\.LT\.U32\.AND → SHF\.R\.U32\.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF\.R\.U32\.HI → SGXT\.U32 → POPC → ISETP\.LT\.U32\.AND → SHF\.R\.U32\.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF\.R\.U32\.HI → SGXT\.U32 → SHF\.R\.U32\.HI → SGXT\.U32 → IADD3 → ISETP\.LT\.U32\.AND → SHF\.R\.U32\.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF\.R\.U32\.HI → SGXT\.U32 → ISETP\.LT\.U32\.AND → IADD3 → SEL → IADD3 → SEL → SEL~~|~~—（编译器优化消除）~~|~~从给定起始 bit 位置和方向查找第 n 个置位 bit，并返回其位置。~~<br>|
|ACT02|~~tanh\.approx\.f16x2 %v1, %v0;~~|~~MUFU\.TANH\.F16 → MUFU\.TANH\.F16 → PRMT~~<br>|~~MUFU\.TANH\.F16 → LDCU\.64 → PRMT~~|~~分别对 packed ~~~~`f16x2`~~~~ 中的两个 FP16 元素计算近似双曲正切。~~|
|ACT04|~~tanh\.approx\.bf16x2 %v1, %v0;~~|~~MUFU\.TANH\.BF16 → MUFU\.TANH\.BF16 → PRMT~~|~~MUFU\.TANH\.BF16 → LDCU\.64 → PRMT~~|~~分别对 packed ~~~~`bf16x2`~~~~ 中的两个 BF16 元素计算近似双曲正切。~~|
|ACT06|~~ex2\.approx\.f16x2 %v1, %v0;~~|~~MUFU\.EX2\.F16 → MUFU\.EX2\.F16 → PRMT~~|~~MUFU\.EX2\.F16 → LDCU\.64 → PRMT~~|~~分别对 packed ~~~~`f16x2`~~~~ 中的两个 FP16 元素计算近似 ~~~~`2^x`~~~~。~~|

2. 第二类：一条 PTX 由多个不同硬件机制共同实现（16条）



|ID|PTX|O0SASS|O3SASS|解释|
|---|---|---|---|---|
|T08|~~tcgen05\.alloc\.cta\_group::1\.sync\.aligned\.shared::cta\.b32 \[smem\_result\], %ncols;~~|~~WARPSYNC\.ALL → MOV → S2R → LEA → LDS\.U8 → PRMT → PRMT → PRMT → ISETP\.EQ\.AND → PLOP3\.LUT → @P0 BRA → SHF\.R\.S32\.HI → MOV → WARPSYNC\.COLLECTIVE → ELECT → MOV → ENDCOLLECTIVE → PLOP3\.LUT → PLOP3\.LUT → @P0 BRA → R2UR → PLOP3\.LUT → @P1 ELECT → @P0 PLOP3\.LUT → DEPBAR\.LE → UTCATOMSWS\.FIND\_AND\_SET\.ALIGN → PLOP3\.LUT → @P1 BRA\.U\.ANY → MOV → PLOP3\.LUT → SEL → ISETP\.EQ\.AND → PLOP3\.LUT → @P0 BRA → NANOSLEEP → BRA → MOV → SHF\.L\.U32 → LOP3\.LUT → SHF\.L\.U32 → IADD3 → MOV → SHF\.L\.U32 → LOP3\.LUT → MOV → S2R → LEA → ATOMS\.OR → SHF\.L\.U32 → STS → BRA → MOV → STS → MOV → CALL\.REL\.NOINC → WARPSYNC\.ALL~~|~~S2UR → UMOV → ULEA → LDS\.U8 → UMOV → ULEA → ISETP\.NE\.AND → @P0 BRA → ELECT → @\!P0 BRA → LDC → IMAD\.MOV\.U32 → IMAD\.MOV\.U32 → SHF\.R\.S32\.HI → R2UR → DEPBAR\.LE → UTCATOMSWS\.FIND\_AND\_SET\.ALIGN → PLOP3\.LUT → SEL → ISETP\.NE\.AND → SHF\.L\.U32 → LOP3\.LUT → IMAD\.U32 → @P0 BRA → NANOSLEEP → R2UR → DEPBAR\.LE → UTCATOMSWS\.FIND\_AND\_SET\.ALIGN → PLOP3\.LUT → SEL → ISETP\.NE\.AND → IMAD\.U32 → @\!P0 BRA → VIADD → UMOV → SHF\.L\.U32 → ULEA → IMAD\.SHL\.U32 → SHF\.L\.U32 → LOP3\.LUT → ATOMS\.OR → STS → BRA → IMAD\.MOV\.U32 → MOV → STS → CALL\.REL\.NOINC → WARPSYNC\.ALL~~|~~为当前 CTA 分配指定列数的 TMEM，并把分配得到的 TMEM 地址写入 CTA shared memory。~~<br>|
|T09|~~tcgen05\.dealloc\.cta\_group::1\.sync\.aligned\.b32 %taddr, %ncols;~~|~~WARPSYNC\.ALL → SHF\.R\.S32\.HI → SHF\.R\.U32\.HI → MOV → SHF\.L\.U32 → LOP3\.LUT → SHF\.L\.U32 → IADD3 → MOV → SHF\.L\.U32 → LOP3\.LUT → LOP3\.LUT → SHF\.R\.U32\.HI → MOV → S2R → LEA → LDS → LOP3\.LUT → SHF\.R\.U32\.HI → LOP3\.LUT → ISETP\.NE\.AND → MOV → MOV → @P0 BRA → LOP3\.LUT → ISETP\.NE\.AND → @P0 BRA → LOP3\.LUT → MOV → WARPSYNC\.COLLECTIVE → ELECT → MOV → ENDCOLLECTIVE → PLOP3\.LUT → PLOP3\.LUT → BSSY\.RECONVERGENT → @P0 BRA → R2UR → DEPBAR\.LE → UTCATOMSWS\.AND → BSYNC\.RECONVERGENT → MOV → S2R → LEA → ATOMS\.AND → BRA → LOP3\.LUT → LOP3\.LUT → MOV → MOV → SHF\.L\.U32 → LOP3\.LUT → POPC → ISETP\.LT\.AND → PRMT → POPC → ISETP\.LT\.U32\.AND → SHF\.R\.U32\.HI → IADD3 → IADD3 → SEL → SEL → SEL → PRMT → POPC → ISETP\.LT\.U32\.AND → SHF\.R\.U32\.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF\.R\.U32\.HI → SGXT\.U32 → POPC → ISETP\.LT\.U32\.AND → SHF\.R\.U32\.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF\.R\.U32\.HI → SGXT\.U32 → SHF\.R\.U32\.HI → SGXT\.U32 → IADD3 → ISETP\.LT\.U32\.AND → SHF\.R\.U32\.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF\.R\.U32\.HI → SGXT\.U32 → ISETP\.LT\.U32\.AND → IADD3 → SEL → SEL → IMAD\.SHL\.U32 → VIMNMX\.U32 → MOV → MOV → CALL\.REL\.NOINC → BRA → MOV → CALL\.REL\.NOINC → BRA → WARPSYNC\.ALL~~|~~S2UR → UMOV → LDC → IMAD\.MOV\.U32 → LDCU\.64 → IMAD\.MOV\.U32 → LDC → ULEA → SHF\.R\.S32\.HI → LDS → SHF\.L\.U32 → LOP3\.LUT → LOP3\.LUT → SHF\.R\.U32\.HI → SHF\.L\.U32 → VIADD → SHF\.L\.U32 → LOP3\.LUT → LOP3\.LUT → LOP3\.LUT → ISETP\.NE\.AND → @P0 BRA → SHF\.R\.U32\.HI → SHF\.R\.U32\.HI → LOP3\.LUT → ISETP\.NE\.AND → @P0 BRA → R2UR → S2R → VOTEU\.ANY → UFLO\.U32 → ULOP3\.LUT → IMAD\.U32 → REDUX → UTCATOMSWS\.AND → ISETP\.EQ\.U32\.AND → IMAD\.U32 → @P0 ATOMS\.AND → BRA → MOV → CALL\.REL\.NOINC → BRA → MOV → CALL\.REL\.NOINC~~|~~释放当前 CTA 先前分配的一段 TMEM 列范围。~~<br>|
|F01|~~fence\.proxy\.async\.shared::cta;~~<br>|~~MEMBAR\.ALL\.CTA → FENCE\.VIEW\.ASYNC\.S~~<br>|~~MEMBAR\.ALL\.CTA → FENCE\.VIEW\.ASYNC\.S~~|~~在 CTA scope 建立 shared memory 的 generic proxy 与 async proxy 之间的访问顺序和可见性。~~|
|F02|~~fence\.proxy\.async\.shared::cluster;~~|~~MEMBAR\.ALL\.GPU → FENCE\.VIEW\.ASYNC\.S~~|~~MEMBAR\.ALL\.GPU → FENCE\.VIEW\.ASYNC\.S~~|~~在 cluster scope 建立 shared memory 的 generic proxy 与 async proxy 之间的访问顺序和可见性。~~|
|F03|~~fence\.proxy\.async;~~|~~MEMBAR\.ALL\.GPU → FENCE\.VIEW\.ASYNC\.S~~|~~MEMBAR\.ALL\.GPU → FENCE\.VIEW\.ASYNC\.S~~|~~在该指令默认作用域建立 generic proxy 与 async proxy 之间的访问顺序和可见性。~~|
|F04|~~fence\.proxy\.tensormap::generic\.release\.cta;~~|~~MEMBAR\.ALL\.GPU → ERRBAR → CGAERRBAR~~|~~MEMBAR\.ALL\.GPU → ERRBAR → CGAERRBAR~~|~~以 release 语义发布 generic 地址空间中的 tensor\-map 更新，使其对 tensormap proxy 可见。~~|
|F06|barrier\.cluster\.arrive;|LDC → ISETP\.EQ\.U32\.AND → @\!P0 BRA → MOV → WARPSYNC\.COLLECTIVE\.ALL → MEMBAR\.ALL\.GPU → ERRBAR → CGAERRBAR → UCGABAR\_ARV → ENDCOLLECTIVE → BRA → MOV → WARPSYNC\.COLLECTIVE → ENDCOLLECTIVE|LDC → ISETP\.EQ\.U32\.AND → @\!P0 BRA → MEMBAR\.ALL\.GPU → ERRBAR → CGAERRBAR → UCGABAR\_ARV → BRA|通知当前 CTA 已到达 cluster barrier；arrive 本身不等待其他 CTA。<br>|
|F07|barrier\.cluster\.wait;|LDC → ISETP\.EQ\.U32\.AND → @\!P0 BRA → MOV → WARPSYNC\.COLLECTIVE\.ALL → UCGABAR\_WAIT → CCTL\.IVALL → ENDCOLLECTIVE → BRA → MOV → MOV → MOV → WARPSYNC\.COLLECTIVE\.ALL → SHF\.L\.U32 → LOP3\.LUT → BAR\.SYNC\.DEFER\_BLOCKING → SHF\.R\.U32\.HI → ENDCOLLECTIVE|LDC → ISETP\.EQ\.U32\.AND → @\!P0 BRA → UCGABAR\_WAIT → CCTL\.IVALL → BRA → BAR\.SYNC\.DEFER\_BLOCKING<br>|等待 cluster 中参与的 CTA 全部到达 cluster barrier 后再继续执行。<br>|
|FP09|~~ex2\.approx\.f32 %f1, %f0;~~|~~MOV → FSETP\.LT\.AND → MOV → FMUL → FSEL → MUFU\.EX2 → FMUL → FSEL~~|~~—（编译器优化消除）~~<br>|~~计算单精度输入的近似 ~~~~`2^x`~~~~。~~|
|FP10|~~lg2\.approx\.f32 %f1, %f0;~~|~~FADD → MOV → FSETP\.LT\.AND → MOV → FMUL → FSEL → MUFU\.LG2 → MOV → FADD → FSEL~~|~~—（编译器优化消除）~~|~~计算单精度输入的近似 ~~~~`log2(x)`~~~~。~~|
|FP11|~~rcp\.approx\.f32 %f1, %f0;~~|~~FADD → FSETP\.LT\.AND → MOV → FSEL → FSETP\.GT\.AND → FSEL → FMUL → MUFU\.RCP → FMUL~~|~~—（编译器优化消除）~~|~~计算单精度输入的近似倒数 ~~~~`1/x`~~~~。~~|
|FP12|~~rsqrt\.approx\.f32 %f1, %f0;~~|~~FADD → MOV → FSETP\.LT\.AND → MOV → FMUL → FSEL → MUFU\.RSQ → MOV → FMUL → FSEL~~|~~—（编译器优化消除）~~|~~计算单精度输入的近似倒平方根 ~~~~`1/sqrt(x)`~~~~。~~|
|BT04|~~bfe\.u32 %r1, %r0, 8, 4;~~|~~MOV → SHF\.L\.U32 → MOV → LOP3\.LUT → PRMT → PRMT → SHF\.R\.U32\.HI → SGXT\.U32~~|~~—（编译器优化消除）~~|~~从 32\-bit 输入的指定起始位置提取指定宽度的无符号 bit\-field，并零扩展结果。~~|
|BT05|~~bfe\.s32 %r1, %r0, 8, 4;~~|~~MOV → SHF\.L\.U32 → MOV → LOP3\.LUT → PRMT → PRMT → SHF\.R\.S32\.HI → SGXT~~|~~—（编译器优化消除）~~|~~从 32\-bit 输入的指定起始位置提取指定宽度的有符号 bit\-field，并符号扩展结果。~~|
|BT06|~~bfi\.b32 %r2, %r0, %r1, 8, 4;~~|~~MOV → SHF\.L\.U32 → MOV → LOP3\.LUT → PRMT → PRMT → BMSK → SHF\.L\.U32 → LOP3\.LUT~~|~~—（编译器优化消除）~~|~~把一个指定宽度的 bit\-field 插入目标 32\-bit 值的指定位置，其余位保持原值。~~|
|CL03|~~cvta\.shared::cta\.u64 %gen\_addr, smem\_data;~~|~~MOV → MOV → S2R → MOV → MOV → MOV → MOV~~<br>|~~S2R → MOV → S2R → LEA → MOV → MOV~~<br>|~~把 CTA shared\-memory 数组的地址转换成可用于 generic addressing 的 64\-bit 地址。~~|

# 指令联合编译

这里把一段完整的 `mbarrier` 生命周期放进同一个 kernel，看 B200 生成的整段 SASS。

以 `mbarrier` 为例，一个完整生命周期可以包含：

```text
init → expect_tx / arrive.expect_tx → arrive → complete_tx
     → try_wait.acquire（循环等待）→ arrive_drop（可选，改变下一 phase 的参与者）→ inval
```

XP6 的 1:N 统计以 SIMD 执行组为单位。组内的 lane mask、谓词合成、重汇聚和 `WARPSYNC` 都归入一条 SIMD 指令，不单独计数。寄存器搬运只保留有效操作数搬运：`R2UR`、`S2R/S2UR` 或非 identity `MOV` 的结果直接供 barrier、TMEM 或 TMA 的地址、state、token 使用；死值搬运和只服务于 warp 控制流的搬运剔除。

跨执行组的同步计入 mapping：`mbarrier` 的到达和等待、`arrive_drop` 后的计数变化、事务完成、release/acquire 可见性，以及 CTA 级 `bar.sync`。

## XP6 口径下出现 1:N 的指令

下表只保留跨执行组状态、async proxy 或 TMEM 分配相关的 SASS。有效操作数搬运保留；lane mask、冗余搬运、warp 内重汇聚和 `WARPSYNC` 已剔除。某行只要 O0 或 O3 有 1:N 展开就列入表中。

|目录 / case|PTX（源行）|O0 SASS（计数）|O3 SASS（计数）|
|---|---|---|---|
|mbarrier / mbarrier_semantic|L45：mbarrier.init.shared::cta.b64 [smem_bar], %r_count;|R2UR（state/address）×3 → FENCE.VIEW.ASYNC.S → SYNCS.EXCH.64（5）|S2UR（CTA id）→ SYNCS.EXCH.64（2）|
|tcgen05 / tcgen05_mma_lifecycle_structural|L50：tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [smem_taddr], %r3;|R2UR（allocation operand）→ DEPBAR.LE → UTCATOMSWS.FIND_AND_SET.ALIGN（retry）→ ATOMS.OR → STS（5+）|DEPBAR.LE → UTCATOMSWS.FIND_AND_SET.ALIGN（retry）→ ATOMS.OR → STS（4+）|
|tcgen05 / tcgen05_mma_lifecycle_structural|L57：fence.proxy.async.shared::cta;|MEMBAR.ALL.CTA → FENCE.VIEW.ASYNC.S（2）|MEMBAR.ALL.CTA → FENCE.VIEW.ASYNC.S（2）|
|tcgen05 / tcgen05_mma_lifecycle_structural|L66–67：tcgen05.mma.cta_group::1.kind::tf32 ...;|R2UR（MMA operands）×11 → UTCHMMA（12）|UMOV（TMEM offset）→ UTCHMMA（2）|
|tcgen05 / tcgen05_mma_lifecycle_structural|L68：tcgen05.commit.cta_group::1.mbarrier::arrive::one.shared::cluster.b64 [smem_mbar];|R2UR（mbarrier address）→ UTCBAR（2）|UTCBAR（1）|
|tcgen05 / tcgen05_mma_lifecycle_structural|L80：tcgen05.ld.sync.aligned.16x64b.x1.b32 {%r9}, [%r4];|R2UR（TMEM address）→ LDTM.16dp64bit（2）|LDTM.16dp64bit（1）|
|tcgen05 / tcgen05_mma_lifecycle_structural|L88：tcgen05.dealloc.cta_group::1.sync.aligned.b32 %r4, %r3;|R2UR（allocation mask）→ DEPBAR.LE → UTCATOMSWS.AND → ATOMS.AND（4）|R2UR（allocation mask）→ UTCATOMSWS.AND → ATOMS.AND（3）|
|tcgen05 / tcgen05_mma_lifecycle_structural|L89：tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;|S2R（CTA id）→ UVIRTCOUNT.DEALLOC.SMPOOL → STS.U8（3）|S2UR（CTA id）→ UVIRTCOUNT.DEALLOC.SMPOOL → STS.U8（3）|
|tma / cp_async_group|L31：cp.async.ca.shared.global [smem_words], [%rd0], 16;|R2UR（global descriptor）×2 → LDGSTS.E.128（3）|LDGSTS.E.128（1）|
|tma / cp_async_group|L32：cp.async.cg.shared.global [smem_words+16], [%rd3], 16;|R2UR（global descriptor）×2 → LDGSTS.E.BYPASS.128（3）|LDGSTS.E.BYPASS.128（1）|
|tma / tma_mbarrier_load_2d、tma_bulk_store_2d|L41 / L45：fence.proxy.tensormap::generic.acquire.sys [%rd0], 128;|R2UR（descriptor operand）×2 → DEPBAR {5,4,3,2,1,0} → CCTL.E.C.LDCU.IV.DEEP → UTMACCTL.IV（5）|DEPBAR {5,4,3,2,1,0} → CCTL.E.C.LDCU.IV.DEEP → UTMACCTL.IV（3）|
|tma / tma_mbarrier_load_2d、tma_bulk_store_2d|L44 / L42：fence.proxy.async.shared::cta;|MEMBAR.ALL.CTA → FENCE.VIEW.ASYNC.S（2）|MEMBAR.ALL.CTA → FENCE.VIEW.ASYNC.S（2）|
|tma / tma_mbarrier_load_2d|L48–49：cp.async.bulk.tensor.2d.shared::cta.global.tile.mbarrier::complete_tx::bytes ...;|R2UR（TMA descriptor、coordinates、shared/barrier address）×6 → UTMALDG.2D（7）|UTMALDG.2D（1）|
|tma / tma_bulk_store_2d|L47–48：cp.async.bulk.tensor.2d.global.shared::cta.tile.bulk_group ...;|R2UR（TMA descriptor、coordinates、shared address）×5 → UTMASTG.2D（6）|UTMASTG.2D（1）|
|tma / tma_bulk_store_2d|L50：cp.async.bulk.wait_group 0;|DEPBAR.LE SB0, 0x0 → CCTL.IVALL（2）|DEPBAR.LE SB0, 0x0 → CCTL.IVALL（2）|

未列出的 `mbarrier.arrive`、`mbarrier.try_wait`、`mbarrier.inval`、`tcgen05.wait::ld`、`cp.async.*.commit_group` 和 classic `cp.async.wait_group`，在去掉无效搬运后只剩一条核心操作。
