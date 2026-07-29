# PTX to SASS mapping

## 分析口径

本文为比较 B200 反汇编，采用以下分类：核心 opcode 是直接表达目标 PTX primitive 的 SASS
opcode；辅助指令负责 operand routing、谓词、issuer selection、控制流、同步包络或内存顺序；
完整 lowering 是核心 opcode 加上实现完整 PTX 语义所需的辅助序列。该分类只服务本文统计，
不是唯一的 ISA 分类方式。

反汇编可直接支持 opcode 及其相对位置。具体用途若只可由 mnemonic 或位置判断，本文使用
“表明”“可能”或“本文将其视为”等表述，不将其写成已由这段 SASS 严格证明的硬件事实。

# 正例

先看一个 1:1 例子。

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

反汇编显示，O0 在 `UTCHMMA` 前以 `R2UR` 写入 `UR4`–`UR15`，随后出现 `VOTEU`、
`ELECT`、`PLOP3.LUT` 和回跳 `BRA.U.ANY`。O3 将部分准备改为 `LDCU`、`UMOV`、`UISETP`，
仍保留 `ELECT`、`PLOP3.LUT` 及回跳。`UTCHMMA` 在两版序列中各出现一次，是其中直接表达
MMA primitive 的 opcode；其余指令位于操作数准备或控制链上。`UMOV UR4, URZ` 直接显示
零值被写入 `UR4`；`ELECT`、谓词和回跳的具体分工则只能由位置和 mnemonic 推断。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=NzVlMjU4ZTExNzAxMjlmZDgyNTVhOTM3MTc2NDZkN2NfZDUyMjZlODlmMzQxM2U5YWU3MDlmNTM0Njk5MTRkZjhfSUQ6NzY2NTUzMjUxNzM0ODc0MDA2OF8xNzg1MTM0MjEyOjE3ODUyMjA2MTJfVjM)

按本文口径，`UTCHMMA` 是核心 opcode，uniform operand 准备和 predicate/控制序列属于完整
lowering 的辅助部分；该样例的核心 opcode 映射为 1:1，完整 lowering 不是 1:1。反汇编
没有显示 MMA 被拆成多条数值算术 SASS；能否在其他目标上融合，仍须看该目标的后端产物。

`tcgen05.cp`（`UTCCP`）、`tcgen05.ld`（`LDTM`）和 `tcgen05.st`（`STTM`）的样例还出现
`WARPSYNC.ALL`。反汇编可确认它位于相关序列中；按后文 XP6 统计口径，纯 warp 内包络不计入
1:N。

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

反汇编显示，`barrier.cluster.arrive` 的 O0 路径为
`LDC → ISETP.EQ → @!P0 BRA → MOV → WARPSYNC.COLLECTIVE.ALL → MEMBAR.ALL.GPU → ERRBAR → CGAERRBAR → UCGABAR_ARV → ENDCOLLECTIVE`；
另一分支只保留 `MOV/WARPSYNC/ENDCOLLECTIVE`。O3 保留 `LDC/ISETP/BRA` 和
`MEMBAR.ALL.GPU → ERRBAR → CGAERRBAR → UCGABAR_ARV`，去掉了 O0 的 warp collective
包络。`LDC` 的结果参与比较和分支，表明这里按该值选择路径；仅从该段 SASS 不能确定该值或
`ERRBAR/CGAERRBAR` 的全部硬件含义。

按本文分类，`UCGABAR_ARV` 是直接表达 arrive primitive 的核心 opcode。路径选择、O0 的
collective 包络，以及位于它前面的顺序相关指令属于完整 lowering 的辅助序列；核心 opcode
层面为 1:1，完整 lowering 不为 1:1。

反汇编显示，`barrier.cluster.wait` 的 O0 含 `UCGABAR_WAIT → CCTL.IVALL` 的路径，另一条
路径含 `SHF → LOP3.LUT → BAR.SYNC.DEFER_BLOCKING → SHF`；两条路径前均有
`LDC → ISETP.EQ → @!P0 BRA`，O0 还在两侧放置 `WARPSYNC.COLLECTIVE(.ALL)` 和
`ENDCOLLECTIVE`。O3 将前一路径压缩为 `UCGABAR_WAIT → CCTL.IVALL`，另一条压缩为
`BAR.SYNC.DEFER_BLOCKING 0x0`；兼容路径没有被删除。`CCTL.IVALL` 紧随
`UCGABAR_WAIT`，本文只据其位置将其记为 wait 后的辅助操作，不从 mnemonic 推定更细的
硬件效果。

按本文分类，`UCGABAR_WAIT` 是 cluster wait 路径中直接表达目标 primitive 的核心 opcode；
分支、O0 的 collective 包络、兼容路径和紧随其后的 `CCTL.IVALL` 计入完整 lowering。两种
计数不能混用。

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

本节把一段完整的 `mbarrier` 生命周期放进同一个 kernel，记录 B200 生成的整段 SASS。

以 `mbarrier` 为例，一个完整生命周期可以包含：

```text
init → expect_tx / arrive.expect_tx → arrive → complete_tx
     → try_wait.acquire（循环等待）→ arrive_drop（可选，改变下一 phase 的参与者）→ inval
```

## 每个 case 在做什么

下表列出完整协议；`1:N 源行`只标出后表统计的 PTX。未标出的 arrive、wait、commit、
`bar.sync` 或 `inval` 仍属于该协议，只是按本节 XP6 口径不构成 1:N。

|目录 / case|参与者与数据|完整 PTX 协议（源行）|完成条件 / B200 状态|1:N 源行|
|---|---|---|---|---|
|mbarrier / `test_mbarrier_arrive_wait`|`mbarrier_semantic.ptx`，`<<<1,32>>>`；每个 lane 写 `tid+1` 到 shared。`smem_bar` 承担可见性，`smem_control_bar` 只确认 32 次主 arrive 已发出。|L45–46 初始化两个 barrier → L49 发布初始化 → L60 `arrive.release` ×32 → L68 control `arrive.relaxed` ×32 → L72 control `try_wait.relaxed` → L76 main `try_wait.acquire` → L87–92 读取并求和 → L95–96 关闭。|lane 0 的和必须为 `528`。O0、O3 已在 B200 runtime 通过。|L45 main init。|
|mbarrier / `test_mbarrier_expect_tx_complete_tx`|`mbarrier_semantic.ptx`，`<<<1,32>>>`；lane 0 在任意 arrival 前额外打开一个 transaction。|L125–126 初始化 → L128 发布 → L133 `expect_tx(1)` → L135 保证它先于 arrival → L138 arrive ×32 → L141 control arrive ×32 → L148 `test_wait` → L154 `complete_tx(1)` → L157 acquire wait → L164–165 关闭。|arrival count 已归零时，L148 仍必须为 false；L154 后 wait 才成功。输出为 `1` 和 `0xC0DEC0DE`。O0、O3 已 runtime 通过。|L125 main init。|
|mbarrier / `test_mbarrier_arrive_expect_tx_complete_tx`|`mbarrier_semantic.ptx`，`<<<1,32>>>`；lane 0 将自己的 arrival 与一个 transaction 合并，其他 31 个 lane 普通 arrival。|L194–195 初始化 → L198 发布 → L201 leader `arrive.expect_tx(1)`，L202 其余 31 个 `arrive.release` → L206 control arrive → L214 `test_wait` → L218 `complete_tx(1)` → L221 acquire wait → L226–227 关闭。|验证合并的 arrive/expect_tx 与分开的 expect_tx 使用同一完成计数。输出为 `1` 和 `0xB03B03B0`。O0、O3 已 runtime 通过。|L194 main init。|
|mbarrier / `test_mbarrier_arrive_drop_next_phase`|`mbarrier_semantic.ptx`，`<<<1,32>>>`；lane 31 在 phase 0 退出，phase 1 只剩 31 个参与者。|L255 初始化 → L257 `bar.sync 0` 发布 → L262 lane 31 `arrive_drop`，L263 其余 31 个 arrive → L268 `bar.sync 1` → L271 phase-0 acquire wait → L274 `bar.sync 2` → L279 仅 31 个 lane phase-1 arrive → L282 phase-1 acquire wait → L287 关闭。|phase 1 只在 expected-arrival count 已由 32 变为 31 时完成。输出为 `0x0A441D04`。O0、O3 已 runtime 通过。|L255 init。|
|tcgen05 / `tcgen05_mma_lifecycle_structural`|`tcgen05_mma_lifecycle_structural.ptx`，`.reqntid 32`；所有 lane 做 TMEM alloc/ld/dealloc，只有 lane 0 issue MMA 与 commit。A/B descriptor 和 `idesc` 是 raw 参数。|L45 init(1) → L47 `bar.sync 0` → L50 alloc 32 columns → L51 `bar.sync 1` → L57 async-proxy fence → L66–67 MMA → L68 commit/arrive::one → L71 wait → L76 `bar.sync 2` → L77 post-thread fence → L80 ld、L81 wait::ld → L88 dealloc → L89 归还 permit → L93 `bar.sync 3` → L94 inval。|只验证这条生命周期能以 `sm_100a` 编译、反汇编且 marker 齐全；没有 launch，不能声称 MMA 数值正确。|L45、L50、L57、L88–89。|
|tma / `semantic_cp_async_group`|`cp_async_group.ptx`，`<<<1,1>>>`；两个 16-byte classic `cp.async` 将 8 个 `u32` 搬到 shared。|L31 `cp.async.ca` → L32 `cp.async.cg` → L33 `commit_group` → L34 `wait_group 0` → L37–52 shared→global copy。|host 逐项比较 8 个 `u32`。O0、O3 已在 B200 runtime 通过。|—（XP6 过滤后均为 1:1）。|
|tma / `semantic_tma_mbarrier_load_2d`|`tma_mbarrier_load_2d.ptx`，`<<<1,32>>>`；thread 0 发起 TMA load。host 构造无 swizzle 的 16×16 `u32` tensor map，TMA 向 shared 写 1024 B。|L31 init(1) → L32 CTA 发布 → L41 tensormap acquire fence → L44 async-proxy fence → L48–49 TMA load（`complete_tx::bytes`）→ L52 `arrive.expect_tx(1024)` → L55 acquire wait → L61–72 逐元素拷出 → L79 inval。|host 比较完整 16×16 tile，而非 checksum。O0、O3 已 runtime 通过。|L31、L41、L44。|
|tma / `semantic_tma_bulk_store_2d`|`tma_bulk_store_2d.ptx`，`<<<1,1>>>`；先在 shared 填满 16×16 `u32`，值为 `0xA5000000 | index`，再由 TMA 写 global。|L27–38 填 shared tile → L42 async-proxy fence → L45 tensormap acquire fence → L47–48 TMA bulk-group store → L49 bulk commit → L50 bulk wait。|host 比较全部 256 个 global 元素。O0、O3 已在 B200 runtime 通过。|L42、L45、L50。|

## XP6 统计口径

按本文对 B200 operand path 的解读，`R2UR` 把组内一致的值从普通寄存器 `R` 写入
warp-SIMT 的统一寄存器 `UR`。XP6 以 SIMD 执行组发射，不设 `UR`，也不采用这条
`R→UR` 通路。按本文 XP6 统计口径，`R2UR`、`S2UR` 以及 def-use 链只为写入 `UR/UP` 而
存在的 `LDCU`、`UMOV`、`ULEA`、`UIADD3`、`USHF`、`UIMAD`、`UPRMT`、`UISETP`、`ULOP3`、
`UFLO` 不计入 1:N。

这只改变计数，不删除数据依赖。descriptor、坐标、地址、barrier state、token 和
CTA/cluster context 若为运行时值，仍须由 XP6 的 operand 或地址表达承接。`S2R`、`MOV`、
`LEA`、`IMAD` 不能按 mnemonic 一概删除；只有纯 UR staging、死值、identity move 或纯
warp 控制流链路才剔除。以 `U` 开头的 SASS 也不能一概删除；按本文分类，`UTCHMMA`、
`UTMALDG`、`UTMASTG`、`UTCBAR`、`UTCATOMSWS` 和 `UCGABAR_*` 属于核心 opcode 或跨执行组
状态，不是 `UR` 搬运。

下表是本文的 XP6 过滤规则，不是对 B200 指令微架构作用的逐条证明。

|B200 中的类别|XP6 处理|边界|
|---|---|---|
|`R2UR`、`S2UR` 与仅为 `UR/UP` 准备的 uniform 链|不计入；按 XP6 operand/地址输入重写|运行时 descriptor、地址、坐标和 CTA/cluster context 仍要有|
|`S2R SR_CgaCtaId`、`SR_SWINHI` 等 cluster/remote context|不将 B200 的 special-register→UR 路由计数|保留 CTA rank、shared-window base 和 remote 地址这一输入依赖|
|`ELECT`、`VOTEU`，以及只服务于 single-thread issue 的 `PLOP3/ISETP/BRA.U.ANY`|不计入|显式 PTX `vote`/`elect`，或真正的程序谓词/分支，仍须 lower 成 SIMD mask、reduction 或分支|
|`WARPSYNC.*`、`ENDCOLLECTIVE`、只为重汇聚的 `BSSY/BSYNC`|不计入|仅限 warp 内包络；跨 SIMD 执行组的同步不在此列|
|`SR_LANEID`、`SR_TID.X`、lane mask|仅在它们只用于 lane-0 issuer 或 NVIDIA lane ownership 时不计入|若上层语义需要 element shuffle、vote、match 或 reduction，必须保留等价 SIMD 操作|
|`SHFL`、`VOTE`、`MATCH`、`REDUX/CREDUX`|不继承 NVIDIA warp 指令形式|若 PTX 本身要求跨 element 的置换、投票、匹配或归约，须 lower 成 XP6 SIMD permute/reduce，不能静默删除|
|`mbarrier`、`bar.sync`、cluster barrier、release/acquire、async completion|计入|它们表达跨 SIMD 执行组的状态和同步|
|`MEMBAR`、`FENCE`、`DEPBAR`、`CCTL`、`ERRBAR`、`CGAERRBAR`|保留对应的内存模型、async 或 scoreboard 语义|XP6 可融合编码，但不能因 SIMD 直接删除|
|TMEM allocator 的 `UTCATOMSWS`、`ATOMS`、retry、`NANOSLEEP`|保留资源分配/释放语义|只有 XP6 另行采用静态分配时才可用另一套实现替换|

本文按 PTX 的参与者范围判断同步是否计入，不按这次 B200 测试恰好启动了多少线程判断。
`WARPSYNC` 是单个 NVIDIA warp 内的包络，不计入；`mbarrier.shared::cta`、`bar.sync` 和
cluster/remote barrier 在 producer/consumer 可落到不同 XP6 SIMD 执行组时计入。后端若能
证明参与者始终在同一执行组，才可改成 local 形式并从 1:N 中去掉。

## XP6 口径下仍为 1:N 的指令

B200 SASS 只作为 XP6 lowering 的参考证据，不能直接等同于 XP6 最终指令数。下表从 B200
O0/O3 源行证据中剔除 UR 路由和 warp-SIMT 包络后得到。括号里的 N 是仍须完成的独立语义
动作数，不是已经确定的 XP6 二进制指令数；若 XP6 ISA 能把这些动作融合，必须以 XP6 后端
产物重新确认。CTA/cluster context 作为输入依赖单列，不把 B200 的 `S2R/S2UR/R2UR` 逐条
搬运计数。表按 PTX opcode 去重；同一 opcode 在多个 case 的源行合并到一行。某行只要 O0 或
O3 仍有 1:N 才列入。

完整 B200 SASS 以
`verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final/*/sass/*_gp.sass`
为准；该反汇编保留 PTX 源行标记。

|目录 / case|PTX（源行）|B200 O0（按 XP6 过滤）|B200 O3（按 XP6 过滤）|
|---|---|---|---|
|mbarrier / test_mbarrier_arrive_wait、test_mbarrier_expect_tx_complete_tx、test_mbarrier_arrive_expect_tx_complete_tx、test_mbarrier_arrive_drop_next_phase；tcgen05 / tcgen05_mma_lifecycle_structural；tma / semantic_tma_mbarrier_load_2d|mbarrier.init.shared::cta.b64；mbarrier_semantic.ptx L45/L125/L194/L255：[smem_bar], %r_count；tcgen05_mma_lifecycle_structural.ptx L45：[smem_mbar], %r2；tma_mbarrier_load_2d.ptx L31：[smem_bar], 1|FENCE.VIEW.ASYNC.S → SYNCS.EXCH.64（2）|SYNCS.EXCH.64（1）|
|tcgen05 / tcgen05_mma_lifecycle_structural|tcgen05_mma_lifecycle_structural.ptx L50：tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [smem_taddr], %r3;|DEPBAR.LE → UTCATOMSWS.FIND_AND_SET.ALIGN（retry）→ ATOMS.OR → STS（4+）|DEPBAR.LE → UTCATOMSWS.FIND_AND_SET.ALIGN（retry）→ ATOMS.OR → STS（4+）|
|tcgen05 / tcgen05_mma_lifecycle_structural；tma / semantic_tma_mbarrier_load_2d、semantic_tma_bulk_store_2d|tcgen05_mma_lifecycle_structural.ptx L57；tma_mbarrier_load_2d.ptx L44；tma_bulk_store_2d.ptx L42：fence.proxy.async.shared::cta;|MEMBAR.ALL.CTA → FENCE.VIEW.ASYNC.S（2）|MEMBAR.ALL.CTA → FENCE.VIEW.ASYNC.S（2）|
|tcgen05 / tcgen05_mma_lifecycle_structural|tcgen05_mma_lifecycle_structural.ptx L88：tcgen05.dealloc.cta_group::1.sync.aligned.b32 %r4, %r3;|DEPBAR.LE → UTCATOMSWS.AND → ATOMS.AND（3）|UTCATOMSWS.AND → ATOMS.AND（2）|
|tcgen05 / tcgen05_mma_lifecycle_structural|tcgen05_mma_lifecycle_structural.ptx L89：tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;|UVIRTCOUNT.DEALLOC.SMPOOL → STS.U8（2；CTA context 为输入依赖）|UVIRTCOUNT.DEALLOC.SMPOOL → STS.U8（2；CTA context 为输入依赖）|
|tma / semantic_tma_mbarrier_load_2d、semantic_tma_bulk_store_2d|tma_mbarrier_load_2d.ptx L41；tma_bulk_store_2d.ptx L45：fence.proxy.tensormap::generic.acquire.sys [%rd0], 128;|DEPBAR {5,4,3,2,1,0} → CCTL.E.C.LDCU.IV.DEEP → UTMACCTL.IV（3）|DEPBAR {5,4,3,2,1,0} → CCTL.E.C.LDCU.IV.DEEP → UTMACCTL.IV（3）|
|tma / semantic_tma_bulk_store_2d|tma_bulk_store_2d.ptx L50：cp.async.bulk.wait_group 0;|DEPBAR.LE SB0, 0x0 → CCTL.IVALL（2）|DEPBAR.LE SB0, 0x0 → CCTL.IVALL（2）|
