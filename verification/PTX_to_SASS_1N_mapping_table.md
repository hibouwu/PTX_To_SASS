# B200 PTX→SASS 1:N 对应表

本表从旧 75 条 `1:N` 候选中排除 36 条 P 类协议/路由映射和 2 条经动态 A/B 证明为
核心 1:1 的记录，并分别列出 A、C、R 三类。A 类表示已经确认存在算术宽度拆分或软件
算法展开；C 类表示存在多个硬件机制但语义边界仍需复核；R 类表示现有证据不足，暂不
判定为严格 1:N。

序列来源：O0 使用 `audited_sass_sequence_O0`，O3 使用 `sass_core_sequence_O3`。
SASS 单元格只显示 mnemonic 顺序，完整谓词、寄存器、立即数和地址操作数见
[`mapping_report.csv`](results/mapping_report.csv) 以及 `sass_dumps/`。

“解释”列不重复 PTX 的功能定义，而是说明：为何后端不能（或没有）用一条 SASS
完成该语义，以及这些 SASS 按什么大致顺序协作。SASS 中的 MOV、R2UR 等仅在它们参与
该流程时提及；它们不自动等同于核心语义展开。

> O0 是映射主证据。O3 会常量折叠、死代码消除并产生源行交错；O3 显示“优化消除/无独立归因”不表示架构不存在该映射。

## A 类：算术宽度拆分或软件算法展开（20 条）

| ID | PTX | O0SASS | O3SASS | 解释 |
|----|-----|---------|---------|------|
| I02 | add.s64 %rd2, %rd0, %rd1; | IADD3 → IADD3.X | —（编译器优化消除） | 64-bit 值由两个 32-bit half 保存，而 IADD3 一次只覆盖一个 half；先计算低 32 位并产生 carry，再由 IADD3.X 把 carry 加入高 32 位。 |
| I03 | sub.s64 %rd2, %rd0, %rd1; | IADD3 → IADD3.X | —（编译器优化消除） | 原因同 64-bit 加法：一条指令不能同时完成两个 half 的借位传播；先做低半减法，再用 IADD3.X 完成带 borrow 的高半。 |
| I07 | mul.lo.s64 %rd2, %rd0, %rd1; | MOV → MOV → IMAD.WIDE.U32 → MOV → MOV → IMAD.WIDE.U32 → MOV → MOV → MOV → MOV → IMAD.WIDE.U32 → MOV → MOV → IADD3 → IADD3.X → IMAD.WIDE.U32.X → MOV → MOV | —（编译器优化消除） | 64×64 乘法要拆为多个 32×32 partial product，单条 IMAD 无法覆盖；先排列寄存器对，再以 IMAD.WIDE 计算部分积，用 IADD3/IADD3.X 合并交叉项与进位，最后取低 64 位。MOV 多数是部分积路由。 |
| I09 | mad.wide.u32 %rd0, %r0, %r1, %rd0; | IMAD.U32 → IMAD.HI.U32 → MOV → IADD3 → IADD3.X | —（编译器优化消除） | 语义同时要求 32×32→64 乘法和 64-bit 加法，不能由一条 32-bit SASS 包办；先取得乘积低/高 half，随后将它们与累加器低/高 half 相加并传播 carry。 |
| I10 | div.s32 %r2, %r0, %r1; | IABS → I2F.U32.RP → MUFU.RCP → IADD3 → F2I.FTZ.U32.TRUNC.NTZ → IMAD.U32 → IADD3 → IMAD.HI.U32 → IADD3 → IABS → IMAD.HI.U32 → IMAD.U32 → IADD3 → IADD3 → ISETP.LE.U32.AND → SEL → IADD3 → IADD3 → SEL → ISETP.GE.U32.AND → SEL → LOP3.LUT → MOV → ISETP.GE.AND → @P0 BRA → IADD3 → MOV → ISETP.NE.AND → LOP3.LUT → PLOP3.LUT → SEL → MOV | I2F.U32.RP → HFMA2 → MOV → LDCU.64 → MUFU.RCP → IADD3 → F2I.FTZ.U32.TRUNC.NTZ → IMAD → IMAD.HI.U32 → IMAD.HI.U32 → IMAD → ISETP.GE.U32.AND → @P0 VIADD → @P0 IADD3 → ISETP.GE.U32.AND → @P1 VIADD | 后端以软件除法实现：先取绝对值并用 MUFU.RCP 求倒数估计，再用 IMAD 重建商/余数，接着 ISETP/SEL 做精确修正，最后恢复符号并处理除零等边界。 |
| I11 | div.u32 %r2, %r0, %r1; | I2F.U32.RP → MUFU.RCP → IADD3 → F2I.FTZ.U32.TRUNC.NTZ → IMAD.U32 → IADD3 → IMAD.HI.U32 → IADD3 → IMAD.HI.U32 → IMAD.U32 → IADD3 → IADD3 → ISETP.GE.U32.AND → SEL → IADD3 → IADD3 → SEL → ISETP.GE.U32.AND → SEL → MOV → ISETP.NE.U32.AND → LOP3.LUT → PLOP3.LUT → SEL | I2F.U32.RP → HFMA2 → MOV → LDCU.64 → MUFU.RCP → IADD3 → F2I.FTZ.U32.TRUNC.NTZ → IMAD → IMAD.HI.U32 → IMAD.HI.U32 → IMAD → ISETP.GE.U32.AND → @P0 VIADD → @P0 IADD3 → ISETP.GE.U32.AND → @P1 VIADD | 没有符号恢复步骤，但仍需倒数估计而非单条整数除法；流程为 I2F/MUFU.RCP/F2I 得到近似商，IMAD 重建乘积，比较和 SEL/IADD3 修正到精确无符号商，并选择边界结果。 |
| I12 | rem.s32 %r2, %r0, %r1; | IABS → I2F.U32.RP → MUFU.RCP → IADD3 → F2I.FTZ.U32.TRUNC.NTZ → IMAD.U32 → IADD3 → IMAD.HI.U32 → IADD3 → IABS → IMAD.HI.U32 → IMAD.U32 → IADD3 → ISETP.LE.U32.AND → IADD3 → SEL → IADD3 → ISETP.LE.U32.AND → SEL → MOV → ISETP.GE.AND → @P0 BRA → IADD3 → MOV → ISETP.NE.AND → LOP3.LUT → PLOP3.LUT → SEL → MOV | I2F.U32.RP → HFMA2 → LDCU.64 → MUFU.RCP → IADD3 → F2I.FTZ.U32.TRUNC.NTZ → IMAD → IMAD.HI.U32 → MOV → IMAD.HI.U32 → IMAD → ISETP.GE.U32.AND → @P0 IADD3 → ISETP.GE.U32.AND → @P0 IADD3 | 余数复用软件除法的倒数估计和 IMAD 商积，但最后保留 a−q×b；随后用比较/选择做两轮范围修正，并按被除数恢复余数符号和处理特殊输入。 |
| I13 | rem.u32 %r2, %r0, %r1; | I2F.U32.RP → MUFU.RCP → IADD3 → F2I.FTZ.U32.TRUNC.NTZ → IMAD.U32 → IADD3 → IMAD.HI.U32 → IADD3 → IMAD.HI.U32 → IMAD.U32 → IADD3 → ISETP.GE.U32.AND → IADD3 → SEL → IADD3 → ISETP.GE.U32.AND → SEL → MOV → ISETP.NE.U32.AND → LOP3.LUT → PLOP3.LUT → SEL → MOV | I2F.U32.RP → HFMA2 → LDCU.64 → MUFU.RCP → IADD3 → F2I.FTZ.U32.TRUNC.NTZ → IMAD → IMAD.HI.U32 → MOV → IMAD.HI.U32 → IMAD → ISETP.GE.U32.AND → @P0 IADD3 → ISETP.GE.U32.AND → @P0 IADD3 | 与有符号余数相同地先近似 q、计算 a−q×b、再修正余数范围；无符号版本省去绝对值和符号恢复，故序列较短。 |
| I15 | shl.b64 %rd1, %rd0, 4; | SHF.L.U64.HI → SHF.L.U32 | —（编译器优化消除） | 64-bit 左移需同时产生两个 32-bit 输出 half：SHF.L.U64.HI 生成高半并接收低半溢出的位，SHF.L.U32 生成低半。 |
| I16 | shr.s64 %rd1, %rd0, 4; | SHF.R.S64 → SHF.R.S32.HI | —（编译器优化消除） | 算术右移同样要分别写两个 half：SHF.R.S64 把高半的位送入低半，SHF.R.S32.HI 生成符号扩展后的高半。 |
| I18A | and.b64 %rd2, %rd0, %rd1; | LOP3.LUT → LOP3.LUT | —（编译器优化消除） | 逻辑运算的 PTX 宽度为 64 bit、SASS 数据通路为 32 bit；两条 LOP3.LUT 依次处理低 half 和高 half。 |
| I18B | or.b64 %rd2, %rd0, %rd1; | LOP3.LUT → LOP3.LUT | —（编译器优化消除） | 原因与 AND 相同：先对低 32 位做 OR，再对高 32 位做 OR，二者共同构成 64-bit 结果。 |
| C05 | cvt.s64.s32 %rd0, %r0; | SHF.R.S32.HI → MOV → MOV | —（编译器优化消除） | O0 的三条来自“生成符号高 half + 组装 64-bit 寄存器对”：SHF 由符号位生成全 0/全 1，高低 half 再由 MOV 落位。严格核心是否只算一条 SHF 仍待 A/B 复核。 |
| FP13 | rcp.rn.f64 %fd1, %fd0; | MOV → IADD3 → MOV → MOV → MOV → MUFU.RCP64H → LOP3.LUT → MOV → MOV → DADD → MOV → MOV → DFMA → DFMA → DFMA → DFMA → DFMA → FADD → FSETP.GEU.AND → MOV → @P0 BRA → LOP3.LUT → IADD3 → MOV → MOV → MOV → CALL.REL.NOINC | MUFU.RCP64H → HFMA2 → MOV → HFMA2 → DFMA → DFMA → DFMA → DFMA → DFMA | 精确 RN 双精度倒数不是单条特殊函数的结果：先由 MUFU.RCP64H 取初值，再以 DADD/DFMA 做残差或 Newton 精化，最后检查异常范围并调整指数/尾数或进入 slow path。 |
| FP14 | sqrt.rn.f64 %fd1, %fd0; | MOV → IADD3 → MOV → MOV → MOV → MUFU.RSQ64H → LOP3.LUT → DMUL → DADD → MOV → MOV → DFMA → MOV → MOV → MOV → MOV → DFMA → DMUL → DFMA → MOV → MOV → MOV → DMUL → MOV → IADD3 → DADD → DFMA → DFMA → ISETP.LT.U32.AND → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → MOV → @P0 BRA → MOV → MOV → MOV → MOV → MOV → MOV → CALL.REL.NOINC | MUFU.RSQ64H → HFMA2 → MOV → IMAD.MOV.U32 → DMUL → DFMA → MOV → DFMA → DMUL → DFMA → DMUL → VIADD → DFMA → DFMA | 精确 RN 双精度平方根先由 MUFU.RSQ64H 得到倒平方根初值，再以 DMUL/DADD/DFMA 细化并乘回输入；范围检查、寄存器对路由和异常 slow path 使完整 O0 序列继续增长。 |
| BT08 | clz.b32 %r1, %r0; | FLO.U32 → IADD3 | —（编译器优化消除） | 硬件给出的是最高置位位的位置而非 CLZ 计数；先用 FLO.U32 找 leading one，再以 IADD3 计算 31−position。 |
| BT10 | fns.b32 %r2, %r0, 0, %r1; | ISETP.EQ.AND → MOV → PLOP3.LUT → @P1 BRA → ISETP.GT.AND → @P1 BRA → BREV → SHF.R.U32.HI → SGXT.U32 → IADD3 → IADD3 → PLOP3.LUT → BRA → MOV → SHF.L.U32 → LOP3.LUT → MOV → MOV → SHF.L.U32 → LOP3.LUT → POPC → ISETP.LT.AND → PRMT → POPC → ISETP.LT.U32.AND → SHF.R.U32.HI → IADD3 → IADD3 → SEL → SEL → SEL → PRMT → POPC → ISETP.LT.U32.AND → SHF.R.U32.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF.R.U32.HI → SGXT.U32 → POPC → ISETP.LT.U32.AND → SHF.R.U32.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF.R.U32.HI → SGXT.U32 → SHF.R.U32.HI → SGXT.U32 → IADD3 → ISETP.LT.U32.AND → SHF.R.U32.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF.R.U32.HI → SGXT.U32 → ISETP.LT.U32.AND → IADD3 → SEL → IADD3 → SEL → SEL | —（编译器优化消除） | 没有单条 FNS SASS；先检查 n、方向和边界，必要时用 BREV 统一方向，然后分层 POPC 统计 32/16/8/4-bit 子块，以 SHF/PRMT 提取候选块、ISETP/SEL 缩小范围，最后组合位置或返回未找到值。 |
| ACT02 | tanh.approx.f16x2 %v1, %v0; | MUFU.TANH.F16 → MUFU.TANH.F16 → PRMT | MUFU.TANH.F16 → LDCU.64 → PRMT | packed f16x2 没有对应的一条 packed MUFU；后端分别计算低、高清 lane 的 tanh，再用 PRMT 重新打包。 |
| ACT04 | tanh.approx.bf16x2 %v1, %v0; | MUFU.TANH.BF16 → MUFU.TANH.BF16 → PRMT | MUFU.TANH.BF16 → LDCU.64 → PRMT | 原因同 f16x2：两个 BF16 lane 要分别送入标量 MUFU.TANH.BF16，最后 PRMT 合并为 packed 结果。 |
| ACT06 | ex2.approx.f16x2 %v1, %v0; | MUFU.EX2.F16 → MUFU.EX2.F16 → PRMT | MUFU.EX2.F16 → LDCU.64 → PRMT | packed f16x2 未直接映射为一条 EX2；流程是分别执行两个 MUFU.EX2.F16，再由 PRMT 重组两个 half。 |

## C 类：复合 1:N 候选（16 条）

| ID | PTX | O0SASS | O3SASS | 解释 |
|----|-----|---------|---------|------|
| T08 | tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [smem_result], %ncols; | WARPSYNC.ALL → MOV → S2R → LEA → LDS.U8 → PRMT → PRMT → PRMT → ISETP.EQ.AND → PLOP3.LUT → @P0 BRA → SHF.R.S32.HI → MOV → WARPSYNC.COLLECTIVE → ELECT → MOV → ENDCOLLECTIVE → PLOP3.LUT → PLOP3.LUT → @P0 BRA → R2UR → PLOP3.LUT → @P1 ELECT → @P0 PLOP3.LUT → DEPBAR.LE → UTCATOMSWS.FIND_AND_SET.ALIGN → PLOP3.LUT → @P1 BRA.U.ANY → MOV → PLOP3.LUT → SEL → ISETP.EQ.AND → PLOP3.LUT → @P0 BRA → NANOSLEEP → BRA → MOV → SHF.L.U32 → LOP3.LUT → SHF.L.U32 → IADD3 → MOV → SHF.L.U32 → LOP3.LUT → MOV → S2R → LEA → ATOMS.OR → SHF.L.U32 → STS → BRA → MOV → STS → MOV → CALL.REL.NOINC → WARPSYNC.ALL | S2UR → UMOV → ULEA → LDS.U8 → UMOV → ULEA → ISETP.NE.AND → @P0 BRA → ELECT → @!P0 BRA → LDC → IMAD.MOV.U32 → IMAD.MOV.U32 → SHF.R.S32.HI → R2UR → DEPBAR.LE → UTCATOMSWS.FIND_AND_SET.ALIGN → PLOP3.LUT → SEL → ISETP.NE.AND → SHF.L.U32 → LOP3.LUT → IMAD.U32 → @P0 BRA → NANOSLEEP → R2UR → DEPBAR.LE → UTCATOMSWS.FIND_AND_SET.ALIGN → PLOP3.LUT → SEL → ISETP.NE.AND → IMAD.U32 → @!P0 BRA → VIADD → UMOV → SHF.L.U32 → ULEA → IMAD.SHL.U32 → SHF.L.U32 → LOP3.LUT → ATOMS.OR → STS → BRA → IMAD.MOV.U32 → MOV → STS → CALL.REL.NOINC → WARPSYNC.ALL | TMEM alloc 是 CTA 协同的位图资源分配，而非一条独立 alloc opcode；流程为读取 CTA/guard 状态并构造对齐 mask，选出 issuer，以 UTCATOMSWS.FIND_AND_SET.ALIGN 原子 find-and-set，检查依赖与结果，失败时 NANOSLEEP 重试，再用 ATOMS/STS 发布地址。WARPSYNC、ELECT、PLOP3、BRA 是协同与控制包络。 |
| T09 | tcgen05.dealloc.cta_group::1.sync.aligned.b32 %taddr, %ncols; | WARPSYNC.ALL → SHF.R.S32.HI → SHF.R.U32.HI → MOV → SHF.L.U32 → LOP3.LUT → SHF.L.U32 → IADD3 → MOV → SHF.L.U32 → LOP3.LUT → LOP3.LUT → SHF.R.U32.HI → MOV → S2R → LEA → LDS → LOP3.LUT → SHF.R.U32.HI → LOP3.LUT → ISETP.NE.AND → MOV → MOV → @P0 BRA → LOP3.LUT → ISETP.NE.AND → @P0 BRA → LOP3.LUT → MOV → WARPSYNC.COLLECTIVE → ELECT → MOV → ENDCOLLECTIVE → PLOP3.LUT → PLOP3.LUT → BSSY.RECONVERGENT → @P0 BRA → R2UR → DEPBAR.LE → UTCATOMSWS.AND → BSYNC.RECONVERGENT → MOV → S2R → LEA → ATOMS.AND → BRA → LOP3.LUT → LOP3.LUT → MOV → MOV → SHF.L.U32 → LOP3.LUT → POPC → ISETP.LT.AND → PRMT → POPC → ISETP.LT.U32.AND → SHF.R.U32.HI → IADD3 → IADD3 → SEL → SEL → SEL → PRMT → POPC → ISETP.LT.U32.AND → SHF.R.U32.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF.R.U32.HI → SGXT.U32 → POPC → ISETP.LT.U32.AND → SHF.R.U32.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF.R.U32.HI → SGXT.U32 → SHF.R.U32.HI → SGXT.U32 → IADD3 → ISETP.LT.U32.AND → SHF.R.U32.HI → IADD3 → IADD3 → SEL → SEL → SEL → SHF.R.U32.HI → SGXT.U32 → ISETP.LT.AND → IADD3 → SEL → SEL → IMAD.SHL.U32 → VIMNMX.U32 → MOV → MOV → CALL.REL.NOINC → BRA → MOV → CALL.REL.NOINC → BRA → WARPSYNC.ALL | S2UR → UMOV → LDC → IMAD.MOV.U32 → LDCU.64 → IMAD.MOV.U32 → LDC → ULEA → SHF.R.S32.HI → LDS → SHF.L.U32 → LOP3.LUT → LOP3.LUT → SHF.R.U32.HI → SHF.L.U32 → VIADD → SHF.L.U32 → LOP3.LUT → LOP3.LUT → LOP3.LUT → ISETP.NE.AND → @P0 BRA → SHF.R.U32.HI → SHF.R.U32.HI → LOP3.LUT → ISETP.NE.AND → @P0 BRA → R2UR → S2R → VOTEU.ANY → UFLO.U32 → ULOP3.LUT → IMAD.U32 → REDUX → UTCATOMSWS.AND → ISETP.EQ.U32.AND → IMAD.U32 → @P0 ATOMS.AND → BRA → MOV → CALL.REL.NOINC → BRA → MOV → CALL.REL.NOINC | 释放必须构造范围 mask、验证范围/所有权并原子清位，不能简化为一次 store；先以 SHF/LOP3/POPC 搜索和构造 mask，进行 collective/重汇合，然后 UTCATOMSWS.AND 与 ATOMS.AND 清位，最后写回或进入错误路径。110 条是相关 O0 完整 lowering，不是 110 次释放动作。 |
| F01 | fence.proxy.async.shared::cta; | MEMBAR.ALL.CTA → FENCE.VIEW.ASYNC.S | MEMBAR.ALL.CTA → FENCE.VIEW.ASYNC.S | proxy fence 同时需要普通内存顺序和 async proxy 的 view 可见性，故不能只留一个 opcode；先由 MEMBAR.ALL.CTA 建立 CTA 顺序，再由 FENCE.VIEW.ASYNC.S 完成 proxy-view 转换。 |
| F02 | fence.proxy.async.shared::cluster; | MEMBAR.ALL.GPU → FENCE.VIEW.ASYNC.S | MEMBAR.ALL.GPU → FENCE.VIEW.ASYNC.S | 展开原因同 F01，但 cluster 所需顺序在该目标上提升为 GPU scope；流程为 MEMBAR.ALL.GPU 后接 FENCE.VIEW.ASYNC.S。 |
| F03 | fence.proxy.async; | MEMBAR.ALL.GPU → FENCE.VIEW.ASYNC.S | MEMBAR.ALL.GPU → FENCE.VIEW.ASYNC.S | generic/async proxy 语义仍分为“内存顺序 + view 转换”两个机制；该形式在 B200 上降为 MEMBAR.ALL.GPU 再接 FENCE.VIEW.ASYNC.S。 |
| F04 | fence.proxy.tensormap::generic.release.cta; | MEMBAR.ALL.GPU → ERRBAR → CGAERRBAR | MEMBAR.ALL.GPU → ERRBAR → CGAERRBAR | release tensormap fence 除了发布内存顺序，还要处理相关 error/cluster error 状态；流程是 MEMBAR 发布写入，再经 ERRBAR 与 CGAERRBAR 完成该状态屏障。 |
| F06 | barrier.cluster.arrive; | LDC → ISETP.EQ.U32.AND → @!P0 BRA → MOV → WARPSYNC.COLLECTIVE.ALL → MEMBAR.ALL.GPU → ERRBAR → CGAERRBAR → UCGABAR_ARV → ENDCOLLECTIVE → BRA → MOV → WARPSYNC.COLLECTIVE → ENDCOLLECTIVE | LDC → ISETP.EQ.U32.AND → @!P0 BRA → MEMBAR.ALL.GPU → ERRBAR → CGAERRBAR → UCGABAR_ARV → BRA | 到达操作要适配 cluster 配置并保证到达前的内存/错误顺序；先读取配置并分派路径，再进入 collective 包络，执行 MEMBAR/ERRBAR/CGAERRBAR，最后由 UCGABAR_ARV 记账。其余是同步和控制流程。 |
| F07 | barrier.cluster.wait; | LDC → ISETP.EQ.U32.AND → @!P0 BRA → MOV → WARPSYNC.COLLECTIVE.ALL → UCGABAR_WAIT → CCTL.IVALL → ENDCOLLECTIVE → BRA → MOV → MOV → MOV → WARPSYNC.COLLECTIVE.ALL → SHF.L.U32 → LOP3.LUT → BAR.SYNC.DEFER_BLOCKING → SHF.R.U32.HI → ENDCOLLECTIVE | LDC → ISETP.EQ.U32.AND → @!P0 BRA → UCGABAR_WAIT → CCTL.IVALL → BRA → BAR.SYNC.DEFER_BLOCKING | wait 要选择 cluster 或回退 barrier 路径并在完成后处理缓存可见性；先按配置分派，主路径执行 UCGABAR_WAIT→CCTL.IVALL，必要时构造参数后走 BAR.SYNC.DEFER_BLOCKING，周围再由 collective 协议包络。 |
| FP09 | ex2.approx.f32 %f1, %f0; | MOV → FSETP.LT.AND → MOV → FMUL → FSEL → MUFU.EX2 → FMUL → FSEL | —（编译器优化消除） | MUFU.EX2 覆盖普通范围，但 PTX 仍需处理极小或非正规输入；流程为比较阈值、选择并缩放输入，调用 MUFU.EX2，再缩放补偿并选择最终结果。 |
| FP10 | lg2.approx.f32 %f1, %f0; | FADD → MOV → FSETP.LT.AND → MOV → FMUL → FSEL → MUFU.LG2 → MOV → FADD → FSEL | —（编译器优化消除） | 单条 MUFU.LG2 对 subnormal 范围不足以直接满足 PTX 行为；先规范化/比较输入并缩放，执行 MUFU.LG2，随后施加指数补偿并选择结果。 |
| FP11 | rcp.approx.f32 %f1, %f0; | FADD → FSETP.LT.AND → MOV → FSEL → FSETP.GT.AND → FSEL → FMUL → MUFU.RCP → FMUL | —（编译器优化消除） | MUFU.RCP 是核心，但极小/极大幅值可能下溢或溢出；先检测范围并选择缩放因子，缩放后求倒数，再做反向缩放得到符合范围的结果。 |
| FP12 | rsqrt.approx.f32 %f1, %f0; | FADD → MOV → FSETP.LT.AND → MOV → FMUL → FSEL → MUFU.RSQ → MOV → FMUL → FSEL | —（编译器优化消除） | MUFU.RSQ 处理普通输入，额外序列维持 subnormal 行为；比较/选择常量后缩放输入，执行 MUFU.RSQ，最后补偿输出并选择结果。 |
| BT04 | bfe.u32 %r1, %r0, 8, 4; | MOV → SHF.L.U32 → MOV → LOP3.LUT → PRMT → PRMT → SHF.R.U32.HI → SGXT.U32 | —（编译器优化消除） | 无直接 BFE SASS；先用 MOV/SHF/LOP3/PRMT 把 position 和 width 编码为控制量，再右移提取字段，最后以 SGXT.U32 截断并零扩展。 |
| BT05 | bfe.s32 %r1, %r0, 8, 4; | MOV → SHF.L.U32 → MOV → LOP3.LUT → PRMT → PRMT → SHF.R.S32.HI → SGXT | —（编译器优化消除） | 与无符号 BFE 一样需先构造提取控制、再移位；末尾改用有符号 SHF.R.S32.HI 与 SGXT，使字段按最高位符号扩展。 |
| BT06 | bfi.b32 %r2, %r0, %r1, 8, 4; | MOV → SHF.L.U32 → MOV → LOP3.LUT → PRMT → PRMT → BMSK → SHF.L.U32 → LOP3.LUT | —（编译器优化消除） | 没有单条 bit-field insert；先构造 position/width 控制，BMSK 生成字段 mask，SHF.L 定位插入值，最后 LOP3 把原值、插入值和 mask 合并。 |
| CL03 | cvta.shared::cta.u64 %gen_addr, smem_data; | MOV → MOV → S2R → MOV → MOV → MOV → MOV | S2R → MOV → S2R → LEA → MOV → MOV | generic 地址并不只是 shared offset：还需当前 CTA shared-memory window 的高位；先 S2R 读取 SR_SWINHI，再以 MOV 组装 64-bit 地址对。多数 O0 条目是路由，严格核心边界仍待验证。 |

## R 类：存疑，暂不计入严格 1:N（1 条）

| ID | PTX | O0SASS | O3SASS | 解释 |
|----|-----|---------|---------|------|
| I21B | mov.b64 %rd1, %rd0; | MOV → MOV | —（编译器优化消除） | 完整 O0 出现两条是因为 PTX 的 64-bit 值占两个物理 half；但实际为 R2→R2、R3→R3 的恒等自拷贝，没有可观察语义流程。它很可能是寄存器别名而非核心 1:2，须以不同源/目的寄存器的动态 A/B 验证。 |

## B200 动态 A/B 后排除的旧 R 类（2 条）

| ID | PTX | O0SASS | O3SASS | 解释 |
|----|-----|---------|---------|------|
| BT07 | popc.b32 %r1, %r0; | LOP3.LUT → LOP3.LUT → POPC | POPC | O0 先用两条 LOP3 做输入/掩码规范化，再执行真正的 POPC；动态 A/B 与 O3 证明规范化可折叠，核心流程只剩 POPC，故不构成严格 1:3。 |
| BT09 | brev.b32 %r1, %r0; | BREV → SHF.R.U32.HI → SGXT.U32 | BREV | O0 在 BREV 后追加结果宽度/寄存器规范化；动态 A/B 与 O3 显示 BREV 可直接产生并写回所需结果，故 SHF/SGXT 不是 bit-reverse 的第二、第三步。 |

## 不进入本表的旧候选

- P 类共 36 条：核心 opcode 通常为 1:1；`R2UR/WARPSYNC/ELECT/PLOP3/BRA` 等另存为
  操作数布置或编译器协议。
- BT07、BT09：动态 A/B 已确认核心 1:1；证据见
  [`experiments/BT07_BT09/README.md`](experiments/BT07_BT09/README.md)。

注意：C05 `cvt.s64.s32` 虽在当前报告中标为 A，但其 O0 三条包含两条结果寄存器布置；是否应在最严格的“只数核心变换”口径下降为 1:1，仍需单独 A/B 验证。C 类也不能在复核前直接写入最终展开规则。
