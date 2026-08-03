# 发射线程：lane、CTA thread 与直接谓词 issuer 如何改变 SASS

## 先说结论

发射线程（issuer）描述由哪个线程执行目标 `tcgen05.mma`。已完成的 Thor 基线比较当前线程与 lane-0 branch；新增矩阵进一步加入 lane 31、参数选择 lane、CTA thread 0 和复合直接谓词：

- 当前执行到目标位置的线程直接发射
- 仅 lane 0 通过分支到达目标位置
- 仅 lane 31 通过分支到达目标位置
- kernel 参数指定的 lane 通过分支到达目标位置
- 仅 `%tid.x==0` 的 CTA thread 通过分支到达目标位置
- lane-0 条件与参数 guard 合取后直接谓词化目标

限制 lane 0 为发射线程不改变核心 MMA 的助记符、修饰符或规范操作数结构，但会增加 lane ID 读取、谓词比较和控制流，并系统性改变核心位置与整个 kernel 的寄存器活跃状态。

```text
current_thread
    → 线程直接到达 UTC*MMA

lane0_issuer
    → 读取 SR_LANEID
    → 判断 lane != 0
    → 非 lane 0 绕过或退出
    → lane 0 执行同一 UTC*MMA
```

发射线程是目标指令的外围执行上下文，不是 `tcgen05.mma` 操作码限定符。只比较 `UTCHMMA` 等核心文本会漏掉它的主要影响。

## PTX 形态

`runtime_zero` 基线直接执行 MMA：

```ptx
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
```

`lane0_issuer` case `THOR_MMA_000006` 在目标之前增加：

```ptx
mov.u32 %lane, %laneid;
setp.eq.u32 %issuer, %lane, 0;
@!%issuer bra CASE_END_000006;
tcgen05.mma.cta_group::1.kind::f16
    [%d_tmem], %desc_a, %desc_b, %idesc,
    {%mask0, %mask1, %mask2, %mask3}, %enable;
CASE_END_000006:
```

这段代码选择 lane 0，而不是给 MMA 增加一个新的数据谓词。它与 guard 的区别是：guard 是 PTX 目标指令自身的条件前缀，发射线程配置是围绕目标建立的外围控制流。

## O0：完整显示 lane 选择

O0 中可直接看到 lane ID 和谓词形成：

```sass
S2R R2, SR_LANEID;
MOV R2, R2;
ISETP.EQ.U32.AND P1, PT, R2, RZ, PT;
PLOP3.LUT P1, PT, P1, PT, PT, 0x8, 0x80;
...
@P1 BRA ...;
...
UTCHMMA gdesc[UR4], gdesc[UR6], tmem[UR10], tmem[UR8], idesc[UR9], UR12, UP0;
```

O0 保留了参数装载、lane 比较、分支和 `MOV`/`R2UR` 准备过程。核心操作与无发射线程限制的基线相同。

## O3：收缩为早期退出

O3 将 lane-0 控制收缩为：

```sass
S2R R0, SR_LANEID;
ISETP.NE.U32.AND P0, PT, R0, RZ, PT;
@P0 EXIT;
LDCU UR6, c[0x0][0x380];
LDCU.64 UR8, c[0x0][0x388];
LDCU.64 UR10, c[0x0][0x390];
...
UTCHMMA gdesc[UR8], gdesc[UR10], tmem[UR6], tmem[UR4], idesc[UR5], UP0;
```

`ISETP.NE` 检查 lane ID 是否非零，`@P0 EXIT` 让非 lane 0 线程退出，lane 0 执行后续 MMA。`UTCHMMA` 没有 `.LANE0` 一类修饰符。发射线程信息存在于外围控制流中。

## 为什么活跃寄存器会全面变化

lane-0 分支改变了控制流边界、哪些线程继续执行以及参数准备可以移动到哪里。即使核心 MMA 的规范操作不变，`nvdisasm --life-range-mode count` 看到的核心位置活跃集合仍可能不同。

在普通 FP16 SS 例子中，O3 基线核心位置的活跃数为 GPR 1、PRED 2、UGPR 7、UPRED 1；lane-0 issuer 为 GPR 1、PRED 0、UGPR 7、UPRED 1。谓词已经在早期退出处消费，因此到核心位置不再活跃。活跃数是位置相关的数据流属性，不是核心操作码的固定属性。

## 单因素统计

`lane0_issuer` 与 `runtime_zero` 按相同 semantic form、源码变体和优化级配对，每个优化级 1,152 组：

| 优化级 | 核心助记符变化 | 核心规范操作变化 | 完整 kernel 序列变化 | kernel 指令数变化 | 核心寄存器布局变化 | 核心处活跃数变化 | kernel 峰值活跃数变化 |
|---|---|---|---|---|---|---|---|
| O0 | 0/1,152 | 0/1,152 | 1,152/1,152 | 1,024/1,152 | 0/1,152 | 0/1,152 | 700/1,152 |
| O1 | 0/1,152 | 0/1,152 | 1,152/1,152 | 592/1,152 | 168/1,152 | 1,152/1,152 | 1,152/1,152 |
| O2 | 0/1,152 | 0/1,152 | 1,152/1,152 | 592/1,152 | 168/1,152 | 1,152/1,152 | 1,152/1,152 |
| O3 | 0/1,152 | 0/1,152 | 1,152/1,152 | 592/1,152 | 168/1,152 | 1,152/1,152 | 1,152/1,152 |

O1–O3 的 168 组核心寄存器布局变化全部是纯重编号。没有寄存器类别或别名关系变化。与此同时，1,152/1,152 组核心活跃数、kernel 峰值活跃数和 kernel 引用集合都变化。最准确的表述是：lane-0 issuer 不改变指令选择，但强烈改变控制流和资源状态。

## O1–O3 的精确重编号条件

168 组并不是“所有稀疏形态”，而是可以由 `variant + kind + a_form + zero_column_mask` 精确预测的两个子集：

```text
renumber_only =
    a_form == tmem_address
    and (
        (variant == mma.sp and kind in {mxf4, mxf4nvf4, mxf8f6f4})
        or (variant == mma.ws.sp and zero_column_mask == true)
    )

其余合法形态 = stable_layout
```

| 子集 | 数量 | 必要条件 |
|---|---:|---|
| 稀疏分块缩放 TS | 100 | `mma.sp`；A=`tmem`；kind 为 `mxf4/mxf4nvf4/mxf8f6f4` |
| 稀疏 WS + zero-column-mask TS | 68 | `mma.ws.sp`；A=`tmem`；zero-column-mask=true |
| 其余合法设计 | 984 | 核心寄存器布局稳定 |

这个规则预测的是相对 `runtime_zero` 基线是否出现纯物理寄存器重编号，不预测具体编号。具体编号仍受参数装载融合、活跃区间和工具链版本影响。

O0 的核心位置活跃数没有变化，但完整 kernel 序列全部变化、1,024 组指令数变化、700 组峰值活跃数变化。这反映 O0 的冗长编译降级使新增发射线程计算尚未以 O1–O3 的方式重排到核心附近。

## 扩展 issuer 矩阵

新增 profile 对全部 1,152 个设计生成单因素配对：

| profile | issuer producer | 目标保护方式 | 本地 CUDA 13 O3 预验证 |
|---|---|---|---|
| `lane31_issuer` | `%laneid == 31` | 外围 branch | 核心助记符/规范操作 0 变化；168 纯重编号、984 稳定 |
| `dynamic_lane_issuer` | `%laneid == p_issuer_lane` | 外围 branch | 核心助记符/规范操作 0 变化；168 纯重编号、984 稳定 |
| `thread0_issuer` | `%tid.x == 0` | 外围 branch | 核心助记符/规范操作 0 变化；168 纯重编号、984 稳定 |
| `compound_predicated_issuer` | `(%laneid==0) && (p_guard!=0)` | 目标 `@predicate` 或编译器生成的外围控制流 | 双 occurrence 的 496 个设计只谓词化第一条；单 occurrence 的 656 个设计走外围控制流 |

前三种 branch issuer 与 lane 0 的 168/984 精确分类逐设计一致，跨 profile mismatch=0。compound 形态的零反例规则是 `step_count==2 → (true,false)`，否则核心 predicate 形状为 `(false)`。这些 O3 预验证已经通过全部 270 个 expanded shard 的编译和 24,720 条 occurrence 归属；Thor 上的 O0/O1/O2/O3 完整回归尚待执行，最终结果会由 `analyze_mapping_rules.py` 自动写入 [`reverse_mapping_rules.md`](reverse_mapping_rules.md)。

## 与 guard、CTA group 和 completion 的边界

- 发射线程决定谁到达并发射目标；guard 决定到达目标后的这条指令是否执行。两者都能生成分支，但语义来源不同。
- `.cta_group::1/2` 决定一次 tcgen05 操作触及一个还是两个 CTA 的 TMEM，不等于"由几个 lane 发射"。
- completion 决定已发出的异步工作如何提交和等待，不决定发射者身份。

## 代表性覆盖口径

已完成 Thor 四优化级证据覆盖当前线程与 lane-0 branch；新增生成矩阵覆盖 lane 31、参数选择 lane、CTA thread 0 和复合直接谓词，并已完成全矩阵 O3 预验证。尚未枚举的是动态 leader election、多个候选 issuer、嵌套 issuer/guard 和多 warp/warpgroup 控制流，因此不声明总体百分比。

## 证据

- 上下文统计：[`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)
- PTX case 与上下文清单：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)
- 核心 SASS 与活跃寄存器归属：[`../../results/expanded/sass/sass_attribution.jsonl`](../../results/expanded/sass/sass_attribution.jsonl)
- 综合解释：[`../tcgen05_mma_PTX到SASS映射规则报告.md`](../tcgen05_mma_PTX到SASS映射规则报告.md)
- 自动挖掘的决策规则与逆向可恢复率：[`reverse_mapping_rules.md`](reverse_mapping_rules.md)
