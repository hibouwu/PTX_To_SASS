# PTX To SASS：B200 指令映射验证

本仓库在 NVIDIA B200（`sm_100a`）上用最小 PTX kernel、`ptxas` 和 `nvdisasm`，验证
单条目标 PTX 指令对应的 SASS 核心 opcode。项目的目标不是复刻 `ptxas` 生成的所有
寄存器搬运和控制流，而是建立可审计的 **PTX 核心动作 → SASS 核心动作** 映射。

## 当前口径

同一条 PTX 的反汇编结果分成三层，不能混为一个 1:N 数字：

| 层 | 内容 | 是否计入核心映射 |
|----|------|------------------|
| 核心 opcode | 真正执行目标计算、访存或同步动作的 SASS | 是 |
| 操作数布置 | `R2UR`、寄存器移动、descriptor/地址准备 | 否，单独记录 |
| 编译器协议 | `ELECT`、`PLOP3`、协议分支和 collective 包络 | 否，单独记录 |

例如，T01 的完整 O0 lowering 有 18 条审计后 SASS，但核心映射是：

```text
tcgen05.mma.cta_group::1.kind::tf32  ->  UTCHMMA
```

因此 T01 的核心映射是 **1:1**，不是 1:18。`R2UR/VOTEU` 属于操作数布置，
`ELECT/PLOP3/BRA` 属于编译器为 single-thread issue 插入的发射协议。

`ELECT` 也不表示“一个 kernel 只给第一个 MMA 选举一次”。每次动态 MMA 发射都必须
满足 single-thread issue；编译器可以按上下文插入、提取或复用协议，但这种优化不是
固定的 PTX→SASS 核心映射。参见 NVIDIA 的
[PTX ISA 8.7](https://docs.nvidia.com/cuda/archive/12.8.0/parallel-thread-execution/index.html)
和 [CUTLASS tcgen05 execution model](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/cute_dsl_api/cute_nvgpu_tcgen05.html)。

## XP6 统计口径

B200 的 `R2UR` 是把组内一致的值从普通寄存器 `R` 送到 warp-SIMT 的统一寄存器 `UR`。
XP6 是 SIMD，不设 `UR`，也不需要这条 `R→UR` 发送通路。因此 `R2UR`、`S2UR` 和仅为
`UR/UP` 服务的 B200 搬运不计入 XP6 的 1:N。

这不删除数据依赖：descriptor、地址、barrier state、token 和 CTA/cluster context 若为
运行时值，仍须由 XP6 的普通 SIMD 操作数或目标自己的地址计算提供。跨执行组同步、
fence、async 完成与资源状态仍计入；只服务于 NVIDIA warp-SIMT 的选举、重汇聚和
warp 内同步不计入。

## 实验数据

当前采集环境为 CUDA 12.8 / PTX ISA 8.7 / B200 `sm_100a`：

- 206 个 PTX 用例，其中 205 个合法用例、1 个规范负向用例；
- 合法用例均采集 O0/O3 cubin；
- 每个 cubin 同时保存 `nvdisasm -g` 和 `nvdisasm -gp` 输出；
- 产物完整性与 SHA-256 记录在 `verification/results/artifact_manifest.json`。

`mapping_report.csv` 当前的 `127` 条 1:1、`75` 条 1:N 是旧审计口径，仍把部分完整
lowering 协议算进映射，**不是按上述核心口径重算后的最终分布**。75 条旧 1:N 候选
现分为 36 条协议/路由类、20 条确定算术展开、16 条复合 lowering、1 条待重审，以及
2 条经 B200 动态 A/B 确认为核心 1:1 的记录；详见
[逐条分析](verification/PTX_to_SASS_1N_detailed_analysis.md)。

## 目录

```text
verification/
├── ptx_sources/       # 最小 PTX 测试用例
├── cubins/            # ptxas O0/O3 编译产物
├── sass_dumps/        # nvdisasm -g 输出
├── sass_ptx_dumps/    # nvdisasm -gp 原生 PTX 行号证据
├── results/           # CSV 报告与产物清单
└── scripts/           # 生成、编译、反汇编、分析和校验脚本
```

## 在 B200 上复现实验

需要 CUDA 12.8，并且 `ptxas`、`nvdisasm` 可在 `PATH` 中找到：

```bash
cd verification
bash scripts/run_all.sh --arch sm_100a
```

流水线依次生成 PTX、以 O0/O3 编译、用 `-g/-gp` 双路反汇编、生成 CSV，并校验输入与
所有产物的集合和哈希。O0 是语义归因的主证据，O3 只用于观察优化差异。

## 文档

- [完整验证记录](verification/PTX_to_SASS_mapping_verification.md)
- [旧 1:N 候选逐条重新归因](verification/PTX_to_SASS_1N_detailed_analysis.md)
- [1:N PTX→SASS 对应表](verification/PTX_to_SASS_1N_mapping_table.md)
- [BT07/BT09 动态 A/B 复核](verification/experiments/BT07_BT09/README.md)
- [composed semantic suite](verification/semantic_suite/README.md)：独立验证 mbarrier 的
  cluster/remote 与连续 phase、TMA 的 3D/multicast/reduce/layout/swizzle/prefetch，以及
  CuTe 真实 descriptor 的 tcgen05 数值路径；不会改写静态映射证据。

下一步是把分析器改为分别输出核心 opcode、操作数布置和编译器协议，然后在 B200 上
重跑并更新最终 1:1 / 1:N 分布。
