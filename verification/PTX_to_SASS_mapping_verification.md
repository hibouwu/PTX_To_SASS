# Blackwell PTX→SASS 1:1 映射系统性验证

## 1. 背景与动机

### 1.1 问题起源

L0 层的结构翻译服务（PTX→SASS 伪指令映射）在设计中保留了"1→N 展开"能力——即允许一条 PTX 指令翻译为多条 SASS 指令，且可能引入源 PTX 中不存在的临时通用寄存器。这一能力直接影响 L0 的实现复杂度和 L1 RegManager 的资源分配范围：

- **若存在必须展开的 PTX 指令**：L0 必须实现展开逻辑，且展开引入的临时寄存器必须纳入 L1 分配范围，L0 的"零语义感知"特性将受到挑战
- **若所有目标指令均为 1:1 映射**：L0 结构翻译可退化为纯格式映射（操作码转换 + 操作数槽位重组），无需临时寄存器管理，L0 实现大幅简化

项目早期假设（基于对 tcgen05/TMA/mbarrier 等核心指令族的初步分析）认为 Blackwell 下 PTX→SASS 均为 1:1 或仅操作数槽位格式变换。但该假设未经系统性实证验证。

### 1.2 目标负载

本验证面向以下推理加速算子开发场景，融合深度到 Megakernel 级别：

| 负载 | 关键指令通路 |
|------|-------------|
| Attention (FlashAttn 等) | tcgen05.mma + redux.sync (online softmax) + ex2/tanh (softmax/GELU) + f16x2 算术 |
| MoE (Mixture of Experts) | elect.sync (leader) + match.sync (routing) + shfl (dispatch) + fns/lop3 (expert mask) |
| GEMM | tcgen05.mma + TMA + mbarrier + f16/bf16 epilogue cvt |
| Conv | dp4a (INT8) + 地址计算 (bfe/bfi/lop3) + GEMM 链路 |
| Linear Attention | redux.sync.add.f32 + f16x2 element-wise + shfl |
| Megakernel 融合 | DSMEM (mapa/ld-st::cluster) + griddepcontrol + nanosleep + bar.warp.sync |

### 1.3 验证的核心问题

**在 Blackwell (sm_100a) 架构下，是否存在必须在 SASS 层面展开为多条且引入临时通用寄存器的 PTX 指令？**

如果答案为"否"（或仅存在少数可排除的例外），则框架可以：
1. 将"不支持需展开指令"作为设计约束（白名单机制）
2. 彻底移除 L0 的 1→N 展开逻辑
3. 消除临时寄存器管理的复杂度

## 2. 验证方法论

### 2.1 验证对象

- **目标架构**: NVIDIA Blackwell (sm_100a)
- **PTX ISA 版本**: 9.3（最新版，覆盖 sm_100a 全部指令）
- **编译工具链**: CUDA Toolkit ≥ 12.8（ptxas 支持 sm_100a）
- **反汇编工具**: cuobjdump -sass

### 2.2 方法论原则

| 原则 | 定义 | 目的 |
|------|------|------|
| 最小化原则 | 每个 PTX kernel 仅含 1 条待测指令 + 必要的前置声明与参数加载 | 排除 ptxas 优化干扰，精确隔离目标指令 |
| 双优化等级对比 | 每条指令分别以 `-O0` 和 `-O3` 编译 | 区分"架构强制展开"与"编译器优化展开" |
| 精确寄存器计数 | PTX 侧按位宽计算预期 SASS GP slot 数（64-bit×2, 32-bit×1, pred×0），SASS 侧提取实际使用的 GP 寄存器编号集合 | 判定是否引入了源 PTX 中不存在的临时 GP 寄存器 |
| 逐变体验证 | 对有多种操作数变体的指令（不同位宽/类型/地址空间/数据类型），逐变体生成独立测试用例 | 确保映射结论覆盖全部使用场景 |

### 2.3 执行流程

```
generate_ptx.py          compile_all.sh           disasm_all.sh           analyze.py
  (生成 199 个          (ptxas -O0/-O3         (cuobjdump -sass       (解析对比,
   最小 PTX kernel)  →   编译为 cubin)      →    反汇编为 SASS 文本)  →   生成判定报告)
```

1. **生成**: `scripts/generate_ptx.py` 按 18 个批次生成 199 个最小 PTX kernel，每个 kernel 仅含 1 条待测指令
2. **编译**: `scripts/compile_all.sh` 对每个 .ptx 分别以 `-O0` 和 `-O3` 调用 `ptxas -arch=sm_100a`，产出 cubin
3. **反汇编**: `scripts/disasm_all.sh` 对每个 cubin 执行 `cuobjdump -sass`，产出 SASS 文本
4. **分析**: `scripts/analyze.py` 自动对比 PTX 源与 SASS 输出，按判定标准分类并生成 `results/mapping_report.csv`

### 2.4 判定标准

| verdict | 含义 | 判定条件 |
|---------|------|---------|
| `1:1` | 确认 1:1 映射 | -O0 下 SASS 有效指令数 ≤ 预期值+2，且无额外 GP 寄存器 |
| `1:1_FORMAT` | 1:1 但操作数格式有变换 | -O0 下指令数正常，但有 1 个额外寄存器（格式转换引入） |
| `EXPAND_ARCH` | 架构强制展开 | -O0 和 -O3 下均明显展开（指令数 > 预期+5） |
| `EXPAND_OPT` | 仅编译器优化展开 | -O0 下 1:1，-O3 下展开（不影响设计结论） |
| `NEEDS_REVIEW` | 需人工审查 | 数据不足以自动判定 |
| `COMPILE_FAIL` | PTX 编译失败 | 需检查 PTX 语法或 sm_100a 兼容性 |

**预期 SASS 指令数的计算**：`预期值 = PTX setup 指令数（ld.param + mov）+ 待测指令数`。容忍 +2 的余量是因为 ptxas 可能插入 IMAD 地址计算或常数搬移。

**额外寄存器的计算**：`额外寄存器 = SASS 实际 GP slot 数 - PTX 预期 GP slot 数 - 1（R1 栈指针）`。其中 PTX 预期 GP slot 数按位宽精确计算（64-bit 类型×2, 32-bit×1, predicate×0）。

### 2.5 特殊处理说明

| 情况 | 处理方式 |
|------|---------|
| **mbarrier.try_wait** | PTX 语义上为阻塞等待，ptxas 可能生成含循环的 SASS 序列。这属于**语义等价展开**（PTX 语义本身要求循环），不属于"1→N 引入临时寄存器"。判定时单独标注 |
| **64-bit 操作** | Blackwell GP 寄存器为 32-bit，64-bit 操作天然使用寄存器对（如 R4R5）。这属于**操作数编码层面的宽寄存器对**，不是"引入临时寄存器"。判定标准：使用寄存器对但不引入额外中间寄存器 → 仍为 1:1 |
| **tcgen05/TMA 特殊上下文** | 这些指令需要 TMEM 已分配或 descriptor 已配置。测试 kernel 中包含必要的前置声明，ptxas 编译时会自动处理上下文要求 |
| **NOP 填充** | SASS 中 ptxas 插入的 NOP 对齐填充不计入有效指令数 |

## 3. 测试用例清单

共 **199 条**测试用例，按 18 个批次组织：

| 批次 | 目录 | 数量 | 覆盖范围 | 目标场景 |
|------|------|------|---------|---------|
| 01 | `01_tcgen05` | 15 | tcgen05.mma (5 kind: tf32/f16/bf16/f8f6f4/i8, 4 variant: standard/sparse/ws/ws+sp, cg1/cg2) / cp / ld / st / alloc / dealloc / commit / fence / wait / shift / relinquish | GEMM/Attn 核心计算 |
| 02 | `02_tma` | 10 | cp.async.bulk.tensor (2D/3D load/store/reduce/prefetch, multicast) / commit_group / cp.async.ca / cp.async.cg / cp.async.wait_group | 数据搬运通路 |
| 03 | `03_mbarrier` | 9 | init / arrive / arrive_expect_tx / arrive_drop / expect_tx / complete_tx / try_wait / test_wait / inval | 流水线同步 |
| 04 | `04_fence` | 10 | fence.proxy.async (cta/cluster/generic) / fence.proxy.tensormap / fence.mbarrier_init / barrier.cluster / fence.acq_rel / bar.arrive / bar.sync | 可见性保证 |
| 05 | `05_cuda_core_int` | 21 | add/sub (32/64-bit) / mul (lo/hi/wide) / mad / div/rem (HIGH RISK) / shl/shr (32/64-bit) / and/or/xor (32/64-bit) / setp / selp / mov | 地址计算与标量运算 |
| 06 | `06_cuda_core_fp` | 28 | add/mul/fma (f32/f64) / max/min / abs/neg / ex2/lg2/rcp/rsqrt (approx f32) / rcp.rn.f64 / sqrt.rn.f64 (HIGH RISK) / ex2.ftz / cvt (f32↔f64, f32↔s32, s32↔s64, u32↔u64, f32↔f16, f32↔bf16, f16x2↔f32, bf16x2↔f32) | 通用浮点计算与精度转换 |
| 07 | `07_lsu` | 17 | ld/st.shared (b32/b64/v2b32/v2b64/v4b32) / ld/st.global (b32/b64/v4b32) / ld.global.nc / ld.param | 访存通路 |
| 08 | `08_control_flow` | 6 | mov (tid/ctaid/laneid) / bra (uncond/cond) / ret | 基础控制流 |
| 10 | `10_atomic` | 6 | atom.global.add (u32/u64) / atom.global.cas (b32/b64) / atom.shared.add / red.global.add | 原子操作与归约 |
| 11 | `11_half_precision` | 15 | add/sub/mul/fma (f16, f16x2) / max/min (f16, f16x2) / neg/abs (f16x2) / setp.f16 | F16 Epilogue/Softmax |
| 12 | `12_bf16` | 10 | add/sub/mul/fma (bf16, bf16x2) / max (bf16x2) / neg (bf16x2) | BF16 数据通路 |
| 13 | `13_warp_comm` | 14 | shfl.sync (bfly/up/down/idx) / redux.sync (add/max s32, add/max f32, xor b32) / vote.sync (all/any/ballot) / match.sync / elect.sync | Warp Reduction/Routing |
| 14 | `14_bit_ops` | 11 | lop3 / prmt (b32, f4e) / bfe (u32/s32) / bfi / popc / clz / brev / fns / bmsk | Descriptor 编码与位域操作 |
| 15 | `15_cluster_dsmem` | 6 | mapa / getctarank / cvta.shared::cta / isspacep / ld.shared::cluster / st.shared::cluster | Megakernel 跨 CTA 通信 |
| 16 | `16_megakernel_ctrl` | 5 | bar.warp.sync / nanosleep / griddepcontrol (launch/wait) / prefetch.global.L2 | Megakernel 流水线控制 |
| 17 | `17_quantization` | 8 | dp4a (u32/s32) / dp2a (lo/hi) / cvt.pack (sat.s8/u8) / cvt.rn.satfinite (e4m3x2/e5m2x2) | INT8/FP8 量化推理 |
| 18 | `18_activation` | 8 | tanh.approx (f16/f16x2/bf16/bf16x2/f32) / ex2.approx (f16/f16x2/bf16) | GELU/Softmax 激活 |

**总计: 199 条测试用例**

### 3.1 高风险指令标记

以下指令基于历史架构经验被标记为高风险（可能展开），需要重点关注验证结果：

| 指令 | 风险原因 | 所属批次 |
|------|---------|---------|
| `div.s32` / `div.u32` / `rem.s32` / `rem.u32` | GPU 无硬件除法器，历史上一贯展开为乘逆元+修正序列 | 05 |
| `rcp.rn.f64` / `sqrt.rn.f64` | 双精度精确模式可能需 Newton-Raphson 多步迭代 | 06 |
| `cvt.rn.f16x2.f32` / `cvt.rn.bf16x2.f32` | Packed 转换可能展开为 2 条独立 cvt + 1 条 pack | 06 |
| `mul.wide.s32` / `mad.wide.u32` | 32x32→64 可能需要多条 IMAD 组合 | 05 |
| `atom.global.add.u64` / `atom.global.cas.b64` | 64-bit 原子操作可能拆分为多条 32-bit 操作 | 10 |
| `cp.async.ca` / `cp.async.cg` | 非 bulk 经典异步拷贝在 Blackwell 上可能已变更 | 02 |
| `ld.shared.v4.b32` / `ld.global.v4.b32` | 128-bit 向量 load 可能拆分 | 07 |

## 4. 工具链与使用方式

### 4.1 目录结构

```
verification/
├── ptx_sources/           # 199 个最小 PTX kernel（18 个批次子目录）
├── scripts/
│   ├── generate_ptx.py    # 测试用例生成器
│   ├── compile_all.sh     # 批量编译 (O0 + O3)
│   ├── disasm_all.sh      # 批量反汇编
│   ├── analyze.py         # 自动化分析 + 报告生成
│   └── run_all.sh         # 一键全流程
├── cubins/                # 编译产物 (.cubin + .err)
├── sass_dumps/            # 反汇编输出 (.sass)
└── results/               # 最终报告 (mapping_report.csv)
```

### 4.2 使用方式

```bash
cd verification

# 一键全流程（需 CUDA Toolkit ≥ 12.8 且支持 sm_100a）
bash scripts/run_all.sh --arch sm_100a

# 或分步执行
python3 scripts/generate_ptx.py                                    # 1. 生成 PTX
bash scripts/compile_all.sh --arch sm_100a --continue-on-error -v  # 2. 编译
bash scripts/disasm_all.sh                                         # 3. 反汇编
python3 scripts/analyze.py                                         # 4. 分析

# 仅解析 PTX（验证生成正确性，不依赖 CUDA）
python3 scripts/analyze.py --ptx-only
```

## 5. 预期结论

基于对 Blackwell 架构指令集的理解，预期验证结果将呈现以下分布：

### 5.1 预期判定分布

| verdict | 预期占比 | 预期覆盖的指令族 |
|---------|---------|----------------|
| `1:1` | ~85-90% | tcgen05 全族 / TMA 全族 / mbarrier 全族 / fence 全族 / 大部分整数算术 / f16/bf16 算术 / shfl/redux/vote/match / lop3/prmt/bfe/bfi / cluster/DSMEM / megakernel 控制 / 激活函数 |
| `1:1_FORMAT` | ~5% | 部分 cvt 变体 / 64-bit 操作（使用寄存器对但无额外临时寄存器） |
| `EXPAND_ARCH` | ~3-5% | div/rem 系列 / rcp.rn.f64 / sqrt.rn.f64 / 部分 packed cvt / 可能的 64-bit 原子操作 |
| `NEEDS_REVIEW` | ~2-3% | mbarrier.try_wait（语义循环）/ 边界 case |

### 5.2 预期最终结论（结论 B）

> 目标负载所需的绝大多数 PTX 指令（~95%）在 Blackwell 下均为 1:1 SASS 映射。少数例外（div/rem、双精度精确倒数/平方根、部分 packed 类型转换）可通过以下策略排除：
>
> 1. **白名单机制**：框架仅支持验证通过的 1:1 指令集子集
> 2. **开发者替代**：不在白名单内的 PTX 语义，开发者应以 SASS 粒度等效表达（如 div 用乘逆元序列）
> 3. **PTX 后端兜底**：确实需要"便利语义"的场景走 PTX 后端由 ptxas 处理
>
> 在此结论下，L0 可彻底移除 1→N 展开逻辑，结构翻译服务退化为纯格式映射。

## 6. 实际结论

> 本节在实际执行验证后填写。

### 6.1 执行环境

| 项目 | 值 |
|------|---|
| ptxas 版本 | （待填） |
| cuobjdump 版本 | （待填） |
| 目标架构 | sm_100a |
| PTX ISA 版本 | 9.3 |
| 执行日期 | （待填） |

### 6.2 编译结果

| 指标 | O0 | O3 |
|------|----|----|
| 总数 | | |
| 成功 | | |
| 失败 | | |
| 失败原因分布 | | |

### 6.3 判定分布

| verdict | 数量 | 占比 | 涉及指令 |
|---------|------|------|---------|
| `1:1` | | | |
| `1:1_FORMAT` | | | |
| `EXPAND_ARCH` | | | |
| `EXPAND_OPT` | | | |
| `NEEDS_REVIEW` | | | |
| `COMPILE_FAIL` | | | |

### 6.4 EXPAND_ARCH 指令详细分析

| 指令 | SASS 指令数 (O0) | 额外寄存器数 | 展开模式分析 | 排除策略 |
|------|-----------------|-------------|-------------|---------|
| （待填） | | | | |

### 6.5 NEEDS_REVIEW 指令人工审查记录

| 指令 | 自动分析数据 | 人工审查结论 | 最终判定 |
|------|-------------|-------------|---------|
| （待填） | | | |

### 6.6 COMPILE_FAIL 指令分析

| 指令 | 编译错误 | 原因分析 | 修正方案 |
|------|---------|---------|---------|
| （待填） | | | |

### 6.7 最终结论

> 基于以上数据，最终结论为：

（待填：结论 A / B / C，以及对 L0 设计的具体影响）

### 6.8 支持指令白名单

> 验证通过后，确定框架支持的 1:1 指令白名单：

（待填：按批次列出所有 verdict 为 1:1 或 1:1_FORMAT 的指令）

### 6.9 排除指令清单

> 以下指令因 EXPAND_ARCH 判定被排除在白名单之外：

| 指令 | 排除原因 | 替代方案 |
|------|---------|---------|
| （待填） | | |

## 7. 后续行动

验证完成后，根据最终结论执行以下行动：

- [ ] 根据白名单更新 L0 设计文档中指令覆盖范围描述
- [ ] 若结论支持移除 1→N 展开：简化 L0 结构翻译服务为纯格式映射
- [ ] 更新 L0 元数据库 Schema：移除 1→N 展开规则相关字段
- [ ] 更新 memory 中 "Blackwell PTX→SASS映射为1:1" 结论（从假设升级为已验证事实，注明排除项）
- [ ] 更新 L2 文档：明确不在白名单内的 PTX 语义的处理方式
- [ ] 更新 memory 中 "L0双阶段模型与1→N伪寄存器语义规则"：简化或移除 1→N 展开规则
